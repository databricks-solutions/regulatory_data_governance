"""Leitura das definições de regra da DQX Studio (`dq_quality_rules`).

A tabela vive em Lakebase Postgres desde a DQX 0.15/0.16 (`dqx_lakebase.py`);
aqui só montamos o predicado e indexamos o resultado.

A Studio é compartilhada por todos os deployments que apontam para ela — antes
metastore-wide em UC, agora um schema Postgres único —, o que exige duas defesas:

1. `scope_clause()` — predicado que restringe as regras às tabelas DESTE
   deployment (catálogo próprio ∪ tabelas registradas em `cadoc_tabelas`).
   Sem ele, a tela de Críticas lista regras de outro projeto.
2. `RuleIndex` — índice por `(table_fqn, check_name)`. `check_name` NÃO é único
   em `dq_quality_rules` (o grão real é tabela+regra), então indexar só pelo
   nome faz duas regras homônimas colidirem e o metadado da última lida vencer
   — silenciosamente, trocando a dimensão R.18 exibida.

Também centraliza o parse da coluna `check`, antes duplicado em quatro
routers — a divergência entre eles foi o que permitiu o problema aparecer.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from db import CATALOG
from rc18_links import load_cadoc_tables


async def scope_clause(
    column: str = "table_fqn",
    param_prefix: str = "rscope",
    paramstyle: str = "named",
) -> tuple[str, dict]:
    """Predicado que limita as regras DQX às tabelas deste deployment.

    Escopo = qualquer tabela do catálogo do deployment (`<catalog>.%`, cobrindo
    silver, gold e o que mais vier) UNIÃO as tabelas ativas em `cadoc_tabelas`
    — estas últimas porque o cliente pode registrar uma tabela de OUTRO
    catálogo como alvo de um CADOC, e a regra dela deve continuar contando.

    Retorna (sql_predicate, params); nunca interpola FQN direto no SQL.

    `paramstyle`: o predicado serve duas engines — `named` (`:nome`, Databricks
    SQL) e `pyformat` (`%(nome)s`, psycopg). Só o marcador muda; os nomes não.

    ⚠️ Efeito colateral por desenho: regras cuja `table_fqn` não é uma tabela
    (a Studio usa `__sql_check__/<name>` para checks de SQL puro) ficam FORA —
    não há catálogo a que atribuí-las. Registre a tabela em `cadoc_tabelas` se
    precisar que uma regra dessas apareça.
    """
    tables_by_doc, _doc_by_table = await load_cadoc_tables()
    registered = sorted({t for tables in tables_by_doc.values() for t in tables})

    marker = _param_marker(paramstyle)
    like_param = f"{param_prefix}_prefix"
    params: dict[str, Any] = {like_param: f"{CATALOG}.%"}
    predicate = f"{column} LIKE {marker(like_param)}"
    if registered:
        keys = [f"{param_prefix}{i}" for i in range(len(registered))]
        params.update(dict(zip(keys, registered)))
        placeholders = ",".join(marker(k) for k in keys)
        predicate = f"({predicate} OR {column} IN ({placeholders}))"
    return predicate, params


def _param_marker(paramstyle: str):
    """Devolve a função que formata um nome de parâmetro para a engine alvo."""
    if paramstyle == "named":       # Databricks SQL
        return lambda name: f":{name}"
    if paramstyle == "pyformat":    # psycopg / Lakebase
        return lambda name: f"%({name})s"
    raise ValueError(f"paramstyle não suportado: {paramstyle!r}")


def parse_check_defs(raw: Any) -> list[dict]:
    """Normaliza a coluna `check` numa lista de definições.

    Aceita dict (JSONB via psycopg), str (JSON cru) e list (formato legado).
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
    O fallback existe porque `dq_validation_runs.source_table_fqn` e
    `dq_quality_rules.table_fqn` são preenchidos por caminhos diferentes da
    Studio e podem divergir — sem ele, uma divergência de formatação zeraria a
    tela em vez de degradar. Com o `scope_clause()` aplicado na consulta, o
    fallback só pode casar dentro do próprio catálogo, então deixa de ser a
    porta de colisão entre projetos que era antes.
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
    """Monta um `RuleIndex` a partir das linhas de `dq_quality_rules`.

    Espera `table_fqn` e `checks` (a coluna `check` aliasada). `value_of` decide
    o que guardar; default é o `user_metadata`.
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
