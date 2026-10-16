"""Diagnóstico dos acessos externos (DQX Studio / UC).

Como as leituras degradam para vazio, "falta permissão" e "não há regra" dão a
MESMA tela. Este módulo classifica a causa e devolve o comando de correção já
preenchido com a identidade real do app. Formato espelha o `SetupStep` da Studio.

Regra de ouro: prescrição só quando a causa é conhecida (UC por assinatura de
mensagem). Erro não diagnosticado vira `failed` SEM comando.

Texto fica no frontend (i18n por `id`); daqui só sai o que é neutro de idioma.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from db import (
    DQX_METRICS_TABLE,
    DQX_VALIDATION_RUNS_TABLE,
    USE_MOCK,
    execute_query,
)
from dqx_config import dqx_studio_base_url
from dqx_rules import load_executed_rules

logger = logging.getLogger(__name__)

# Vocabulário do `StepState` da Studio.
PASSED = "passed"
ACTION_REQUIRED = "action_required"  # falta ação humana
FAILED = "failed"                    # inesperado — não sabemos prescrever
SKIPPED = "skipped"                  # dependência anterior falhou

# Ids estáveis = chaves i18n no frontend.
STUDIO_URL = "studio_url"
DELTA_RUNS_SELECT = "delta_runs_select"
RULES_EXECUTED = "rules_executed"


class PrereqCheck(BaseModel):
    """Uma verificação. `remediation` é copiável como está."""

    id: str
    state: str
    params: dict[str, str] = Field(default_factory=dict)  # interpolações do i18n
    remediation: str | None = None
    remediation_kind: str | None = None  # sql | shell | yaml
    detail: str | None = None            # mensagem crua do UC


class PrereqReport(BaseModel):
    state: str          # PASSED quando nada exige ação
    checks: list[PrereqCheck]
    checked_at: str


async def _identity() -> str:
    """Client id do SP do app = alvo do GRANT. `""` se não der para resolver."""
    def _me() -> str:
        from databricks.sdk import WorkspaceClient

        me = WorkspaceClient().current_user.me()
        return me.user_name or me.id or ""

    try:
        return await asyncio.to_thread(_me)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível resolver a identidade do app: %s", exc)
        return ""


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


# Único caso em que prescrever GRANT no UC é correto. Sem esse recorte, qualquer
# falha (warehouse parado, rede) viraria "rode este GRANT". Casamos por substring
# porque o connector não expõe código.
_UC_ACCESS_ERRORS = (
    "INSUFFICIENT_PERMISSIONS",
    "PERMISSION_DENIED",
    "TABLE_OR_VIEW_NOT_FOUND",
    "SCHEMA_NOT_FOUND",
    "does not exist",
)


async def _check_delta_runs() -> PrereqCheck:
    """Tabelas de EXECUÇÃO (Delta/UC) — de onde saem resultados E regras.

    Grant de UC, reaplicável pelo job.
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

        client_id = await _identity()
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


async def _check_rules_executed() -> PrereqCheck:
    """Há regra em vigor no escopo deste deployment? (só roda com acesso OK)

    Codifica a pegadinha do fluxo novo: a regra só aparece no RC18 depois que a
    tabela foi PUBLICADA na Studio e EXECUTADA na versão aprovada — aprovar sem
    rodar não basta, e run de rascunho não conta.
    """
    total = len(await load_executed_rules())
    state = PASSED if total > 0 else ACTION_REQUIRED
    return PrereqCheck(id=RULES_EXECUTED, state=state, params={"count": str(total)})


async def run_prereq_checks() -> PrereqReport:
    """Verificações na ordem da cadeia. Cada chamada é nova — é o "Re-verificar"."""
    now = datetime.now(timezone.utc).isoformat()

    if USE_MOCK:
        # Devloop não tem workspace; alarme aqui seria só ruído.
        return PrereqReport(
            state=PASSED,
            checks=[PrereqCheck(id=STUDIO_URL, state=PASSED)],
            checked_at=now,
        )

    checks: list[PrereqCheck] = [await _check_studio_url(), await _check_delta_runs()]

    if checks[-1].state == PASSED:
        try:
            checks.append(await _check_rules_executed())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Contagem de regras executadas falhou: %s", exc)
            checks.append(PrereqCheck(id=RULES_EXECUTED, state=FAILED,
                                      detail=str(exc).splitlines()[0]))
    else:
        # Sem acesso aos runs não se sabe se há regra; prescrever as duas confunde.
        checks.append(PrereqCheck(id=RULES_EXECUTED, state=SKIPPED))

    overall = PASSED if all(c.state in (PASSED, SKIPPED) for c in checks) else ACTION_REQUIRED
    if any(c.state == FAILED for c in checks):
        overall = FAILED
    return PrereqReport(state=overall, checks=checks, checked_at=now)
