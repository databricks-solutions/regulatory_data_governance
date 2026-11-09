"""Verificação de acesso a uma tabela associada a um CADOC.

Uma tabela de OUTRO catálogo pode entrar em `cadoc_tabelas` (as regras dela já
rodam na DQX Studio), mas o bundle só concede acesso ao próprio catálogo. Aqui
se verifica, como o SP do app, o que dá para verificar — e o resultado é AVISO,
nunca bloqueio: o cadastro segue, e a tela explica o que falta.

Mesmo vocabulário e regra de ouro do `diagnostics.py`: GRANT só é prescrito
quando o erro é de acesso UC; outro erro vira `failed` sem comando.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from db import CATALOG, DQX_VALIDATION_RUNS_TABLE, USE_MOCK, execute_query
from dqx_rules import PUBLISHED_RUN_FILTER

PASSED = "passed"
ACTION_REQUIRED = "action_required"
FAILED = "failed"
SKIPPED = "skipped"

# Ids estáveis = chaves i18n (`linking.access.checks.<id>`).
TABLE_NOT_FOUND = "table_not_found"   # não existe OU o SP não enxerga (o UC não distingue)
TABLE_SELECT = "table_select"         # enxerga, mas sem SELECT
TABLE_READABLE = "table_readable"
DATA_BASE_COLUMN = "data_base_column"
STUDIO_RUNS = "studio_runs"

# Mesmas assinaturas do diagnostics._UC_ACCESS_ERRORS, separadas pela causa.
_NOT_FOUND = ("TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_NOT_FOUND", "CATALOG_NOT_FOUND", "does not exist")
_DENIED = ("INSUFFICIENT_PERMISSIONS", "PERMISSION_DENIED")
UC_ACCESS_ERRORS = _NOT_FOUND + _DENIED

_DATA_BASE_COLUMNS = ("dt_base", "data_base_month")


class AccessCheck(BaseModel):
    id: str
    state: str
    params: dict[str, str] = Field(default_factory=dict)
    remediation: str | None = None
    remediation_kind: str | None = None
    detail: str | None = None


class TableAccessReport(BaseModel):
    table_fqn: str
    external: bool                # fora do catálogo do deployment
    state: str                    # PASSED quando nada pede ação
    checks: list[AccessCheck]


def is_external(table_fqn: str) -> bool:
    return table_fqn.split(".", 1)[0].lower() != CATALOG.lower()


def quote_fqn(table_fqn: str) -> str:
    return ".".join(f"`{p}`" for p in table_fqn.split("."))


def grant_statements(table_fqn: str, role: str) -> str:
    """Os 3 GRANTs mínimos para o SP ler uma tabela (copiáveis como estão)."""
    cat, schema, _table = table_fqn.split(".")
    return "\n".join([
        f"GRANT USE CATALOG ON CATALOG `{cat}` TO `{role}`;",
        f"GRANT USE SCHEMA  ON SCHEMA  `{cat}`.`{schema}` TO `{role}`;",
        f"GRANT SELECT      ON TABLE   {quote_fqn(table_fqn)} TO `{role}`;",
    ])


def _first_line(exc: Exception) -> str:
    raw = str(exc).strip()
    return raw.splitlines()[0] if raw else ""


async def check_readable(table_fqn: str, role: str) -> AccessCheck:
    """O SP do app lê a tabela? `LIMIT 0` checa o privilégio sem ler linha."""
    params = {"table": table_fqn}
    try:
        await execute_query(f"SELECT 1 FROM {quote_fqn(table_fqn)} LIMIT 0", {})
        return AccessCheck(id=TABLE_READABLE, state=PASSED, params=params)
    except Exception as exc:  # noqa: BLE001
        raw = str(exc)
        if any(sig in raw for sig in _DENIED):
            check_id = TABLE_SELECT
        elif any(sig in raw for sig in _NOT_FOUND):
            check_id = TABLE_NOT_FOUND
        else:
            # Warehouse parado, rede…: prescrever GRANT mandaria para o lugar errado.
            return AccessCheck(id=TABLE_READABLE, state=FAILED, params=params, detail=_first_line(exc))
        return AccessCheck(
            id=check_id, state=ACTION_REQUIRED, params=params,
            remediation=grant_statements(table_fqn, role), remediation_kind="sql",
            detail=_first_line(exc),
        )


async def _check_data_base_column(table_fqn: str) -> AccessCheck:
    """Sem `dt_base`/`data_base_month`, o histórico de data-base ignora a tabela."""
    rows = await execute_query(f"DESCRIBE TABLE {quote_fqn(table_fqn)}", {})
    cols = {str(r.get("col_name") or "").lower() for r in rows}
    found = next((c for c in _DATA_BASE_COLUMNS if c in cols), None)
    if found:
        return AccessCheck(id=DATA_BASE_COLUMN, state=PASSED, params={"column": found})
    return AccessCheck(id=DATA_BASE_COLUMN, state=ACTION_REQUIRED)


async def _check_studio_runs(table_fqn: str) -> AccessCheck:
    """A Studio que o RC18 lê tem run publicado desta tabela?"""
    rows = await execute_query(
        f"SELECT count(*) AS n FROM {DQX_VALIDATION_RUNS_TABLE} "
        f"WHERE {PUBLISHED_RUN_FILTER} AND source_table_fqn = :t",
        {"t": table_fqn},
    )
    n = int((rows[0].get("n") if rows else 0) or 0)
    params = {"count": str(n), "runs_table": DQX_VALIDATION_RUNS_TABLE}
    return AccessCheck(id=STUDIO_RUNS, state=PASSED if n else ACTION_REQUIRED, params=params)


def _mock_report(table_fqn: str, role: str) -> TableAccessReport:
    """Devloop: tabela do próprio catálogo passa; externa mostra o alerta."""
    external = is_external(table_fqn)
    if not external:
        checks = [
            AccessCheck(id=TABLE_READABLE, state=PASSED, params={"table": table_fqn}),
            AccessCheck(id=DATA_BASE_COLUMN, state=PASSED, params={"column": "dt_base"}),
            AccessCheck(id=STUDIO_RUNS, state=PASSED, params={"count": "3"}),
        ]
    else:
        checks = [
            AccessCheck(id=TABLE_SELECT, state=ACTION_REQUIRED, params={"table": table_fqn},
                        remediation=grant_statements(table_fqn, role), remediation_kind="sql",
                        detail="[INSUFFICIENT_PERMISSIONS] (mock)"),
            AccessCheck(id=DATA_BASE_COLUMN, state=SKIPPED),
            AccessCheck(id=STUDIO_RUNS, state=PASSED, params={"count": "1"}),
        ]
    return _report(table_fqn, external, checks)


def _report(table_fqn: str, external: bool, checks: list[AccessCheck]) -> TableAccessReport:
    state = PASSED if all(c.state in (PASSED, SKIPPED) for c in checks) else ACTION_REQUIRED
    return TableAccessReport(table_fqn=table_fqn, external=external, state=state, checks=checks)


async def check_table_access(table_fqn: str, role: str) -> TableAccessReport:
    """Leitura → coluna de data-base → run na Studio. Nada aqui bloqueia o cadastro."""
    if USE_MOCK:
        return _mock_report(table_fqn, role)

    readable = await check_readable(table_fqn, role)
    checks = [readable]
    if readable.state == PASSED:
        try:
            checks.append(await _check_data_base_column(table_fqn))
        except Exception as exc:  # noqa: BLE001
            checks.append(AccessCheck(id=DATA_BASE_COLUMN, state=FAILED, detail=_first_line(exc)))
    else:
        # Sem ler a tabela não se sabe as colunas; acusar as duas confunde.
        checks.append(AccessCheck(id=DATA_BASE_COLUMN, state=SKIPPED))

    # Independe da leitura da tabela: os runs vêm da tabela da Studio.
    try:
        checks.append(await _check_studio_runs(table_fqn))
    except Exception as exc:  # noqa: BLE001
        checks.append(AccessCheck(id=STUDIO_RUNS, state=FAILED, detail=_first_line(exc)))
    return _report(table_fqn, is_external(table_fqn), checks)
