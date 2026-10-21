"""Definições das regras da DQX Studio, lidas dos RUNS (`dq_validation_runs.checks_json`).

A Studio grava em cada run o conjunto completo de checks executados, carimbado
com `run_mode` (`published`|`draft`) e `binding_version`. "Regra em vigor" aqui
é a que rodou na última versão aprovada da tabela — não a linha de
`dq_resolved_rules` no Lakebase, que o materializer da Studio apaga ao publicar
outro vínculo (bug DQX #1575). Regra aprovada que ainda não rodou não aparece.

A Studio é compartilhada por todos os deployments que apontam para ela, o que
exige duas defesas:

1. `scope_clause()` — predicado que restringe as regras às tabelas DESTE
   deployment (catálogo próprio ∪ tabelas registradas em `cadoc_tabelas`).
   Sem ele, a tela de Críticas lista regras de outro projeto.
2. `RuleIndex` — índice por `(table_fqn, check_name)`. `check_name` NÃO é único
   entre tabelas, então indexar só pelo nome faz duas regras homônimas
   colidirem e o metadado da última lida vencer — silenciosamente, trocando a
   dimensão R.18 exibida.

Também centraliza o parse do check, antes duplicado em quatro routers — a
divergência entre eles foi o que permitiu o problema aparecer.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from db import CATALOG, DQX_VALIDATION_RUNS_TABLE, execute_query_or_empty
from rc18_links import load_cadoc_tables

# Run que vale como execução da versão APROVADA: terminou, não é preview ad-hoc
# (a Studio também os esconde do histórico) e não é teste de rascunho. O
# `run_mode` é o mesmo em todo check do run; run anterior ao carimbo conta.
PUBLISHED_RUN_FILTER = (
    "status = 'SUCCESS' AND checks_json IS NOT NULL "
    "AND COALESCE(run_type, 'dryrun') <> 'preview' "
    "AND COALESCE(get_json_object(checks_json, '$[0].user_metadata.run_mode'), 'published') = 'published'"
)


async def scope_clause(column: str = "table_fqn", param_prefix: str = "rscope") -> tuple[str, dict]:
    """Predicado que limita as regras DQX às tabelas deste deployment.

    Escopo = qualquer tabela do catálogo do deployment (`<catalog>.%`, cobrindo
    silver, gold e o que mais vier) UNIÃO as tabelas ativas em `cadoc_tabelas`
    — estas últimas porque o cliente pode registrar uma tabela de OUTRO
    catálogo como alvo de um CADOC, e a regra dela deve continuar contando.

    Retorna (sql_predicate, params) no paramstyle do Databricks SQL (`:nome`);
    nunca interpola FQN direto no SQL.

    ⚠️ Efeito colateral por desenho: regras cuja tabela não é uma tabela (a
    Studio usa `__sql_check__/<name>` para checks de SQL puro) ficam FORA — não
    há catálogo a que atribuí-las. Registre a tabela em `cadoc_tabelas` se
    precisar que uma regra dessas apareça.
    """
    tables_by_doc, _doc_by_table = await load_cadoc_tables()
    registered = sorted({t for tables in tables_by_doc.values() for t in tables})

    like_param = f"{param_prefix}_prefix"
    params: dict[str, Any] = {like_param: f"{CATALOG}.%"}
    predicate = f"{column} LIKE :{like_param}"
    if registered:
        keys = [f"{param_prefix}{i}" for i in range(len(registered))]
        params.update(dict(zip(keys, registered)))
        placeholders = ",".join(f":{k}" for k in keys)
        predicate = f"({predicate} OR {column} IN ({placeholders}))"
    return predicate, params


async def load_executed_rules(table_fqns: list[str] | None = None) -> list[dict]:
    """Regras em vigor por tabela: `[{table_fqn, checks}]`, um check por linha.

    Une os checks de TODOS os runs aprovados da última `binding_version` de
    cada tabela — o "Run" manual pode escolher só algumas regras, então o
    último run sozinho mostraria um subconjunto. Run sem `binding_version`
    (anterior ao carimbo) vale só o mais recente. Regra removida some na
    primeira execução da versão nova.

    Sem `table_fqns`, escopa por `scope_clause()`; com lista vazia, `[]`.
    """
    if table_fqns is None:
        pred, params = await scope_clause(column="source_table_fqn")
    elif not table_fqns:
        return []
    else:
        keys = [f"et{i}" for i in range(len(table_fqns))]
        params = dict(zip(keys, table_fqns))
        pred = f"source_table_fqn IN ({','.join(f':{k}' for k in keys)})"

    rows = await execute_query_or_empty(
        "WITH runs AS ("
        "  SELECT source_table_fqn, created_at, checks_json,"
        "         try_cast(get_json_object(checks_json, '$[0].user_metadata.binding_version') AS INT)"
        "           AS binding_version"
        f"  FROM {DQX_VALIDATION_RUNS_TABLE}"
        f"  WHERE {PUBLISHED_RUN_FILTER} AND {pred}"
        "), ranked AS ("
        "  SELECT *,"
        "         MAX(binding_version) OVER (PARTITION BY source_table_fqn) AS latest_version,"
        "         ROW_NUMBER() OVER (PARTITION BY source_table_fqn ORDER BY created_at DESC) AS rn"
        "  FROM runs"
        ") SELECT source_table_fqn AS table_fqn, chk AS checks, created_at"
        "  FROM ranked LATERAL VIEW explode(from_json(checks_json, 'array<string>')) AS chk"
        "  WHERE binding_version = latest_version OR (latest_version IS NULL AND rn = 1)"
        "  ORDER BY created_at DESC",
        params,
        cache_ns="dqx",
    )
    # Um check por (tabela, nome), do run mais recente: runs da mesma versão
    # podem diferir em valor resolvido na hora (ex. pass_threshold default).
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in rows:
        table_fqn = row.get("table_fqn") or ""
        for chk in parse_check_defs(row.get("checks")):
            key = (table_fqn, check_name_of(chk) or json.dumps(chk, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            out.append({"table_fqn": table_fqn, "checks": chk})
    out.sort(key=lambda r: (r["table_fqn"], check_name_of(r["checks"]) or ""))
    return out


def parse_check_defs(raw: Any) -> list[dict]:
    """Normaliza um check numa lista de definições.

    Aceita str (JSON cru, como sai do `checks_json`), dict e list.
    JSON inválido devolve `[]` — uma linha corrompida não derruba a tela.
    """
    if raw is None:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [c for c in parsed if isinstance(c, dict)]
    return [parsed] if isinstance(parsed, dict) else []


def check_name_of(chk: Any) -> str | None:
    """Nome do check: `name` no topo, ou dentro de `check.arguments`.

    Regras criadas pela UI da Studio podem omitir o `name` — nesse caso o nome
    efetivo só aparece em runtime, no `check_metrics` do run.
    """
    if not isinstance(chk, dict):
        return None
    args = (chk.get("check") or {}).get("arguments") or {}
    return chk.get("name") or (args.get("name") if isinstance(args, dict) else None)


class RuleIndex:
    """Regras DQX indexadas por `(table_fqn, check_name)`.

    `get()` tenta o par primeiro e cai para o nome apenas se o par não casar.
    O fallback é para o `check_name` resolvido em runtime (`check_metrics`),
    que pode diferir do `name` declarado — sem ele, uma divergência de
    formatação zeraria a tela em vez de degradar. Com o `scope_clause()`
    aplicado na consulta, o fallback só casa dentro do próprio catálogo.
    """

    __slots__ = ("_by_pair", "_by_name")

    def __init__(self) -> None:
        self._by_pair: dict[tuple[str, str], dict] = {}
        self._by_name: dict[str, dict] = {}

    def add(self, table_fqn: str, check_name: str, value: dict) -> None:
        self._by_pair[(table_fqn or "", check_name)] = value
        # Primeira ocorrência vence: o fallback por nome é ambíguo por
        # definição, então não faz sentido deixar a última sobrescrever.
        self._by_name.setdefault(check_name, value)

    def get(self, table_fqn: str, check_name: str) -> dict | None:
        hit = self._by_pair.get((table_fqn or "", check_name))
        return hit if hit is not None else self._by_name.get(check_name)

    def has(self, table_fqn: str, check_name: str) -> bool:
        return self.get(table_fqn, check_name) is not None

    def __len__(self) -> int:
        return len(self._by_pair)

    def __iter__(self) -> Iterator[tuple[tuple[str, str], dict]]:
        return iter(self._by_pair.items())


def build_index(rows: list[dict], value_of=None) -> RuleIndex:
    """Monta um `RuleIndex` a partir das linhas de `load_executed_rules()`.

    Espera `table_fqn` e `checks`. `value_of` decide o que guardar; default é o
    `user_metadata`.
    """
    if value_of is None:
        def value_of(_row, chk):  # noqa: ANN001
            return chk.get("user_metadata") or {}

    index = RuleIndex()
    for row in rows:
        table_fqn = row.get("table_fqn") or ""
        for chk in parse_check_defs(row.get("checks")):
            name = check_name_of(chk)
            if name:
                index.add(table_fqn, name, value_of(row, chk))
    return index
