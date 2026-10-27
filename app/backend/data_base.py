"""Data-base avaliada pelos runs da DQX, e a escolha do run por mês de referência.

O `filter` dos checks avalia `max(dt_base)` na hora do run, e nada registra o
resultado. O job gold grava `governance.data_base_ledger` — o conteúdo de cada
mês por tabela, com o intervalo em que valeu e o maior `dt_base`
(notebooks/governance/data_base_ledger.py). A data-base do run é o `dt_base_max`
do maior mês vigente no início dele: o que o filtro do check viu.

Run anterior ao início do histórico tem data-base `desconhecida` — nunca se
chuta. Sem histórico para a tabela (`sem_historico`), idem: a tela mostra o run
normalmente, só sem a data-base.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from db import CATALOG, DQX_VALIDATION_RUNS_TABLE, SCHEMA_GOLD
from db import execute_query_or_empty as execute_query
from dqx_rules import PUBLISHED_RUN_FILTER
from models import TableDataBase
from rc18_links import load_cadoc_documents, load_cadoc_tables

LEDGER_TABLE = f"{CATALOG}.governance.data_base_ledger"

logger = logging.getLogger(__name__)

ORIGEM_HISTORICO = "historico"
ORIGEM_DESCONHECIDA = "desconhecida"
SEM_HISTORICO = "sem_historico"

PERIODICIDADES = ("diaria", "semanal", "mensal", "trimestral", "semestral", "anual", "eventual")
# A data-base desses é uma posição de fim de mês (balancete, balanço, estoque).
_FIM_DE_MES = {"mensal", "trimestral", "semestral", "anual"}
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

# Operações do DESCRIBE HISTORY que não mudam dado — mesma lista do notebook.
NON_DATA_OPERATIONS = frozenset({
    "OPTIMIZE", "VACUUM START", "VACUUM END", "SET TBLPROPERTIES", "UNSET TBLPROPERTIES",
    "ADD CONSTRAINT", "DROP CONSTRAINT", "CHANGE COLUMN", "UPGRADE PROTOCOL",
    "COMPUTE STATS", "ANALYZE STATS", "ROW TRACKING BACKFILL",
})


def period_end(value: Any, periodicidade: str | None) -> str | None:
    """Data-base em ISO `AAAA-MM-DD`, no fim do período.

    `AAAA-MM` vira o último dia do mês; `AAAA-MM-DD` também, nos documentos de
    posição de fim de mês (o 4010 grava o dia 1º). Diário/semanal ficam como vêm.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    s = value.isoformat() if isinstance(value, date) else str(value)
    m = re.match(r"^(\d{4})-?(\d{2})(?:-?(\d{2}))?", s)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    day = int(m.group(3)) if m.group(3) else None
    if day is None or periodicidade in _FIM_DE_MES:
        day = calendar.monthrange(year, month)[1]
    return date(year, month, day).isoformat()


def _utc(value: Any) -> datetime | None:
    """Datetime com fuso (UTC se vier sem); aceita ISO string. O connector varia."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def iso(value: Any) -> str | None:
    dt = _utc(value)
    return dt.isoformat() if dt else None


def evaluate_run(started_at: Any, ledger_rows: list[dict]) -> tuple[str | None, str]:
    """(data-base bruta, origem) do run: o `dt_base_max` do maior mês vigente no início dele."""
    if not ledger_rows:
        return None, SEM_HISTORICO
    start = _utc(started_at)
    froms = [f for f in (_utc(r.get("valid_from")) for r in ledger_rows) if f is not None]
    if start is None or not froms or start < min(froms):
        return None, ORIGEM_DESCONHECIDA
    vigentes = [
        r for r in ledger_rows
        if _utc(r.get("valid_from")) <= start
        and (r.get("valid_to") is None or start < _utc(r.get("valid_to")))
    ]
    if not vigentes:
        return None, ORIGEM_DESCONHECIDA
    row = max(vigentes, key=lambda r: r["data_base_month"])
    return row.get("dt_base_max") or row["data_base_month"], ORIGEM_HISTORICO


async def load_ledger(table_fqns: list[str], *, strict: bool = False) -> dict[str, list[dict]]:
    """Linhas do histórico por tabela. Tabela de histórico ausente → `{}`.

    Qualquer outro erro (ex.: o SP do app sem SELECT — o GRANT só vem com o
    rc18_end_to_end) também vira `{}`: o histórico só acrescenta a data-base, e
    sem ele as telas ficam como antes, com a data-base "não identificada", em vez
    de responder 500. `strict=True` (diagnóstico) deixa o erro subir.
    """
    if not table_fqns:
        return {}
    keys = [f"lt{i}" for i in range(len(table_fqns))]
    try:
        rows = await execute_query(
            "SELECT table_fqn, data_base_month, dt_base_max, valid_from, valid_to, last_seen_version "
            f"FROM {LEDGER_TABLE} WHERE table_fqn IN ({','.join(f':{k}' for k in keys)})",
            dict(zip(keys, table_fqns)),
            cache_ns="pipeline",
        )
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise
        logger.warning("Histórico de data-base ilegível; data-bases ficam não identificadas: %s",
                       str(exc).splitlines()[0][:200])
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["table_fqn"], []).append(r)
    return out


def reference_month(value: str | None) -> str | None:
    """`AAAA-MM` válido, ou None = último processamento de cada documento."""
    return value if value and _MONTH_RE.match(value) else None


async def periodicidade_of_table():
    """table_fqn → periodicidade do CADOC dela (para o fim do período)."""
    _tables_by_doc, doc_by_table = await load_cadoc_tables()
    docs = await load_cadoc_documents()
    return lambda table_fqn: (docs.get(doc_by_table.get(table_fqn)) or {}).get("periodicidade")


async def _published_runs(scope_pred: str, scope_params: dict) -> dict[str, list[dict]]:
    """Runs aprovados do escopo por tabela, do mais recente ao mais antigo.

    O início do run é a linha RUNNING do mesmo run_id — quando a tabela foi lida.
    """
    rows = await execute_query(
        "SELECT p.run_id, p.source_table_fqn, p.total_rows, p.invalid_rows, p.created_at, s.started_at "
        f"FROM {DQX_VALIDATION_RUNS_TABLE} p LEFT JOIN ("
        "  SELECT run_id, MIN(created_at) AS started_at"
        f"  FROM {DQX_VALIDATION_RUNS_TABLE} WHERE {scope_pred} GROUP BY run_id"
        ") s ON s.run_id = p.run_id "
        f"WHERE {PUBLISHED_RUN_FILTER} AND {scope_pred}",
        scope_params,
        cache_ns="dqx",
    )
    by_table: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_table.setdefault(r.get("source_table_fqn") or "", {}).setdefault(r["run_id"], r)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return {
        t: sorted(runs.values(), key=lambda r: _utc(r.get("created_at")) or epoch, reverse=True)
        for t, runs in by_table.items()
    }


def _table_data_base(run: dict, ledger_rows: list[dict], periodicidade: str | None) -> TableDataBase:
    started = run.get("started_at") or run.get("created_at")
    raw, origin = evaluate_run(started, ledger_rows)
    return TableDataBase(
        table_fqn=run.get("source_table_fqn") or "",
        data_base=period_end(raw, periodicidade),
        origin=origin,
        run_id=run.get("run_id"),
        run_started_at=iso(started),
    )


@dataclass
class RunSelection:
    runs: list[dict]                   # o run escolhido de cada tabela
    tables: dict[str, TableDataBase]   # data-base avaliada por esse run
    ever: set[str] = field(default_factory=set)  # tabelas com algum run aprovado


async def select_runs(scope_pred: str, scope_params: dict, month: str | None) -> RunSelection:
    """Um run aprovado por tabela do escopo (`scope_pred` filtra `source_table_fqn`).

    Sem `month`: o último de cada tabela. Com `month` (`AAAA-MM`): o último cuja
    data-base avaliada cai no mês — tabela sem run nele fica de fora (e o
    documento aparece como "sem execução no mês"). Run de data-base não
    identificada só entra no "último processamento".
    """
    by_table = await _published_runs(scope_pred, scope_params)
    ledger = await load_ledger(sorted(by_table))
    periodicidade = await periodicidade_of_table()
    chosen: list[dict] = []
    tables: dict[str, TableDataBase] = {}
    for table_fqn, runs in by_table.items():
        rows = ledger.get(table_fqn, [])
        per = periodicidade(table_fqn)
        for run in runs:
            info = _table_data_base(run, rows, per)
            if month is None or (info.data_base or "")[:7] == month:
                chosen.append(run)
                tables[table_fqn] = info
                break
    return RunSelection(runs=chosen, tables=tables, ever=set(by_table))


async def available_months(scope_pred: str, scope_params: dict) -> list[str]:
    """Meses (`AAAA-MM`) com algum run de data-base identificada, do mais recente ao mais antigo."""
    by_table = await _published_runs(scope_pred, scope_params)
    ledger = await load_ledger(sorted(by_table))
    periodicidade = await periodicidade_of_table()
    months = {
        info.data_base[:7]
        for table_fqn, runs in by_table.items()
        for info in (_table_data_base(r, ledger.get(table_fqn, []), periodicidade(table_fqn)) for r in runs)
        if info.data_base
    }
    return sorted(months, reverse=True)


async def current_month() -> str:
    """Mês (`AAAA-MM`) do `gold.processing_state` — fallback de quem precisa de um mês."""
    rows = await execute_query(
        f"SELECT data_base_month FROM {CATALOG}.{SCHEMA_GOLD}.processing_state "
        "ORDER BY updated_at DESC LIMIT 1",
        {},
        cache_ns="pipeline",
    )
    return (rows[0].get("data_base_month") or "") if rows else ""
