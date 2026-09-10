"""Diagnóstico dos acessos externos (DQX Studio / Lakebase / UC).

Como as leituras degradam para vazio, "falta permissão" e "não há regra" dão a
MESMA tela. Este módulo classifica a causa e devolve o comando de correção já
preenchido com a identidade real do app. Formato espelha o `SetupStep` da Studio.

Regra de ouro: prescrição só quando a causa é conhecida (Postgres por SQLSTATE,
UC por assinatura de mensagem). Erro não diagnosticado vira `failed` SEM comando.

Texto fica no frontend (i18n por `id`); daqui só sai o que é neutro de idioma.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field

import dqx_lakebase
from db import (
    DQX_METRICS_TABLE,
    DQX_VALIDATION_RUNS_TABLE,
    USE_MOCK,
    execute_query,
)
from dqx_config import dqx_studio_base_url
from dqx_rules import scope_clause as rule_scope_clause

logger = logging.getLogger(__name__)

# Vocabulário do `StepState` da Studio.
PASSED = "passed"
ACTION_REQUIRED = "action_required"  # falta ação humana
FAILED = "failed"                    # inesperado — não sabemos prescrever
SKIPPED = "skipped"                  # dependência anterior falhou

# Ids estáveis = chaves i18n no frontend.
STUDIO_URL = "studio_url"
LAKEBASE_ENDPOINT = "lakebase_endpoint"
LAKEBASE_CONNECTION = "lakebase_connection"
LAKEBASE_RULES_SELECT = "lakebase_rules_select"
DELTA_RUNS_SELECT = "delta_runs_select"
RULES_MATERIALIZED = "rules_materialized"


class PrereqCheck(BaseModel):
    """Uma verificação. `remediation` é copiável como está."""

    id: str
    state: str
    params: dict[str, str] = Field(default_factory=dict)  # interpolações do i18n
    remediation: str | None = None
    remediation_kind: str | None = None  # psql | sql | shell | yaml
    detail: str | None = None            # mensagem crua do Postgres/UC


class PrereqReport(BaseModel):
    state: str          # PASSED quando nada exige ação
    checks: list[PrereqCheck]
    checked_at: str


def _grant_command(client_id: str) -> str:
    """GRANT pronto para copiar. Aspas duplas obrigatórias: o role é um UUID."""
    schema = dqx_lakebase.LAKEBASE_SCHEMA
    table = dqx_lakebase.RULES_TABLE
    role = client_id or "<client-id-do-sp-do-app>"
    return (
        f'GRANT USAGE ON SCHEMA {schema} TO "{role}";\n'
        f'GRANT SELECT ON TABLE {schema}.{table} TO "{role}";'
    )


def _psql_command() -> str:
    """Como abrir o psql no projeto/branch certos."""
    endpoint = dqx_lakebase.LAKEBASE_ENDPOINT
    project, branch = "<projeto>", "<branch>"
    parts = endpoint.split("/")
    # Extrai por segmento nomeado, não por índice: endpoint fora do formato
    # deve gerar placeholder, não comando errado.
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            project = parts[i + 1]
        if part == "branches" and i + 1 < len(parts):
            branch = parts[i + 1]
    return (
        f"databricks psql --project {project} --branch {branch} "
        f"-- -d {dqx_lakebase.LAKEBASE_DATABASE} -f notebooks/setup/grant_dqx_lakebase_access.sql"
    )


async def _check_studio_url() -> PrereqCheck:
    base = dqx_studio_base_url()
    if base:
        return PrereqCheck(id=STUDIO_URL, state=PASSED, params={"url": base})
    return PrereqCheck(
        id=STUDIO_URL,
        state=ACTION_REQUIRED,
        remediation="dqx_studio_url: https://<host-da-dqx-studio>",
        remediation_kind="yaml",
    )


async def _check_lakebase_endpoint() -> PrereqCheck:
    if dqx_lakebase.is_configured():
        return PrereqCheck(
            id=LAKEBASE_ENDPOINT,
            state=PASSED,
            params={"endpoint": dqx_lakebase.LAKEBASE_ENDPOINT},
        )
    return PrereqCheck(
        id=LAKEBASE_ENDPOINT,
        state=ACTION_REQUIRED,
        remediation="dqx_lakebase_endpoint: projects/<projeto>/branches/<branch>/endpoints/primary",
        remediation_kind="yaml",
    )


# Único caso em que prescrever GRANT no UC é correto. Sem esse recorte, qualquer
# falha (warehouse parado, rede) viraria "rode este GRANT". Casamos por substring
# porque o connector não expõe código — o lado Postgres usa SQLSTATE.
_UC_ACCESS_ERRORS = (
    "INSUFFICIENT_PERMISSIONS",
    "PERMISSION_DENIED",
    "TABLE_OR_VIEW_NOT_FOUND",
    "SCHEMA_NOT_FOUND",
    "does not exist",
)


async def _check_delta_runs() -> PrereqCheck:
    """Tabelas de EXECUÇÃO (Delta/UC) — grant de UC, reaplicável pelo job.

    Separado do Lakebase: falham e se corrigem em lugares diferentes.
    """
    try:
        await execute_query(f"SELECT 1 FROM {DQX_VALIDATION_RUNS_TABLE} LIMIT 0", {})
        await execute_query(f"SELECT 1 FROM {DQX_METRICS_TABLE} LIMIT 0", {})
        return PrereqCheck(id=DELTA_RUNS_SELECT, state=PASSED)
    except Exception as exc:  # noqa: BLE001
        raw = str(exc)
        msg = raw.strip().splitlines()[0] if raw.strip() else ""
        params = {"runs_table": DQX_VALIDATION_RUNS_TABLE, "metrics_table": DQX_METRICS_TABLE}

        if not any(sig in raw for sig in _UC_ACCESS_ERRORS):
            # Outro motivo (warehouse indisponível etc.): erro cru, sem prescrição.
            return PrereqCheck(id=DELTA_RUNS_SELECT, state=FAILED, params=params, detail=msg)

        client_id = await dqx_lakebase.identity()
        role = client_id or "<client-id-do-sp-do-app>"
        remediation = "\n".join(
            f"GRANT SELECT ON TABLE {t} TO `{role}`;"
            for t in (DQX_VALIDATION_RUNS_TABLE, DQX_METRICS_TABLE)
        )
        return PrereqCheck(
            id=DELTA_RUNS_SELECT,
            state=ACTION_REQUIRED,
            params=params,
            remediation=remediation,
            remediation_kind="sql",
            detail=msg,
        )


async def _check_rules_materialized() -> PrereqCheck:
    """Há regra aprovada no escopo deste deployment? (só roda com acesso OK)

    Codifica a pegadinha do fluxo novo: importar YAML cria regra no Registry, e
    ela só chega em `dq_quality_rules` quando o binding é PUBLICADO em Tabelas.
    """
    scope_pred, scope_params = await rule_scope_clause(paramstyle="pyformat")
    rows = await dqx_lakebase.query(
        f"SELECT count(*) AS n FROM {dqx_lakebase.rules_table()} "
        f"WHERE status = '{dqx_lakebase.ACTIVE_STATUS}' AND {scope_pred}",
        scope_params,
    )
    total = int((rows[0] or {}).get("n") or 0) if rows else 0
    if total > 0:
        return PrereqCheck(id=RULES_MATERIALIZED, state=PASSED, params={"count": str(total)})
    return PrereqCheck(id=RULES_MATERIALIZED, state=ACTION_REQUIRED, params={"count": "0"})


async def run_prereq_checks() -> PrereqReport:
    """Verificações na ordem da cadeia. Cada chamada é nova — é o "Re-verificar"."""
    now = datetime.now(timezone.utc).isoformat()

    if USE_MOCK:
        # Devloop não tem workspace; alarme aqui seria só ruído.
        return PrereqReport(
            state=PASSED,
            checks=[PrereqCheck(id=i, state=PASSED) for i in (STUDIO_URL, LAKEBASE_ENDPOINT)],
            checked_at=now,
        )

    checks: list[PrereqCheck] = [await _check_studio_url(), await _check_lakebase_endpoint()]

    endpoint_ok = checks[-1].state == PASSED
    if not endpoint_ok:
        checks += [
            PrereqCheck(id=LAKEBASE_CONNECTION, state=SKIPPED),
            PrereqCheck(id=LAKEBASE_RULES_SELECT, state=SKIPPED),
            PrereqCheck(id=RULES_MATERIALIZED, state=SKIPPED),
        ]
    else:
        state, detail = await dqx_lakebase.probe_rules_access()
        client_id = await dqx_lakebase.identity()

        if state == dqx_lakebase.PROBE_OK:
            checks.append(PrereqCheck(id=LAKEBASE_CONNECTION, state=PASSED,
                                      params={"client_id": client_id}))
            checks.append(PrereqCheck(id=LAKEBASE_RULES_SELECT, state=PASSED,
                                      params={"table": dqx_lakebase.rules_table()}))
            try:
                checks.append(await _check_rules_materialized())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Contagem de regras materializadas falhou: %s", exc)
                checks.append(PrereqCheck(id=RULES_MATERIALIZED, state=FAILED,
                                          detail=str(exc).splitlines()[0]))

        elif state == dqx_lakebase.PROBE_PERMISSION_DENIED:
            # O caso que motivou o módulo: conecta, mas não lê.
            checks.append(PrereqCheck(id=LAKEBASE_CONNECTION, state=PASSED,
                                      params={"client_id": client_id}))
            checks.append(PrereqCheck(
                id=LAKEBASE_RULES_SELECT,
                state=ACTION_REQUIRED,
                params={
                    "client_id": client_id,
                    "schema": dqx_lakebase.LAKEBASE_SCHEMA,
                    "table": dqx_lakebase.RULES_TABLE,
                    "psql": _psql_command(),
                },
                remediation=_grant_command(client_id),
                remediation_kind="psql",
                detail=detail or None,
            ))
            checks.append(PrereqCheck(id=RULES_MATERIALIZED, state=SKIPPED))

        else:
            # Role inexistente (corrige no bundle) ou erro inesperado — este
            # último sem prescrição, para não convidar a execução à toa.
            connect_failed = state == dqx_lakebase.PROBE_CONNECT_FAILED
            checks.append(PrereqCheck(
                id=LAKEBASE_CONNECTION,
                state=ACTION_REQUIRED if connect_failed else FAILED,
                params={"client_id": client_id, "endpoint": dqx_lakebase.LAKEBASE_ENDPOINT},
                remediation="databricks bundle deploy" if connect_failed else None,
                remediation_kind="shell" if connect_failed else None,
                detail=detail or None,
            ))
            checks.append(PrereqCheck(id=LAKEBASE_RULES_SELECT, state=SKIPPED))
            checks.append(PrereqCheck(id=RULES_MATERIALIZED, state=SKIPPED))

    checks.append(await _check_delta_runs())

    overall = PASSED if all(c.state in (PASSED, SKIPPED) for c in checks) else ACTION_REQUIRED
    if any(c.state == FAILED for c in checks):
        overall = FAILED
    return PrereqReport(state=overall, checks=checks, checked_at=now)
