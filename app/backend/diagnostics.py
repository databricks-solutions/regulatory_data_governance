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
from data_base import LEDGER_TABLE, NON_DATA_OPERATIONS, load_ledger
from dqx_config import dqx_studio_base_url
from dqx_rules import load_executed_rules
from rc18_links import load_cadoc_tables

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
DATA_BASE_HISTORY = "data_base_history"
DATA_BASE_HISTORY_LAG = "data_base_history_lag"
DATA_BASE_HISTORY_GRANT = "data_base_history_grant"


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


async def _check_data_base_history() -> PrereqCheck:
    """O histórico de data-base acompanha as tabelas? (ver data_base.py)

    Sem ele as telas mostram o último run sem saber qual data-base avaliou. Fica
    atrasado quando a silver/gold é regravada fora do job gold/rc18_end_to_end.
    """
    tables_by_doc, _doc_by_table = await load_cadoc_tables()
    try:
        ledger = await load_ledger(sorted({t for ts in tables_by_doc.values() for t in ts}), strict=True)
    except Exception as exc:  # noqa: BLE001
        raw = str(exc)
        msg = raw.strip().splitlines()[0] if raw.strip() else ""
        if not any(sig in raw for sig in _UC_ACCESS_ERRORS):
            return PrereqCheck(id=DATA_BASE_HISTORY, state=FAILED, detail=msg)
        # A tabela existe mas o SP do app não lê: o GRANT só vem com o
        # grant_warehouse_perms (rc18_end_to_end) — quem rodou só o job gold fica assim.
        role = await _identity() or "<client-id-do-sp-do-app>"
        return PrereqCheck(
            id=DATA_BASE_HISTORY_GRANT, state=ACTION_REQUIRED,
            params={"table": LEDGER_TABLE},
            remediation=f"GRANT SELECT ON TABLE {LEDGER_TABLE} TO `{role}`;",
            remediation_kind="sql", detail=msg,
        )
    if not ledger:
        return PrereqCheck(
            id=DATA_BASE_HISTORY, state=ACTION_REQUIRED,
            remediation="databricks bundle run rc18_end_to_end", remediation_kind="shell",
        )

    async def _atrasada(table_fqn: str) -> str | None:
        vistas = [r["last_seen_version"] for r in ledger[table_fqn] if r.get("last_seen_version") is not None]
        if not vistas:
            return None  # materialized view (SDP): sem versão para comparar
        quoted = ".".join(f"`{p}`" for p in table_fqn.split("."))
        try:
            hist = await execute_query(f"DESCRIBE HISTORY {quoted} LIMIT 20", {})
        except Exception:  # noqa: BLE001 — sem acesso ao histórico: não acusa
            return None
        versoes = [int(h["version"]) for h in hist if h.get("operation") not in NON_DATA_OPERATIONS]
        return table_fqn if versoes and max(versoes) > max(vistas) else None

    atrasadas = [t for t in await asyncio.gather(*(_atrasada(t) for t in sorted(ledger))) if t]
    if not atrasadas:
        return PrereqCheck(id=DATA_BASE_HISTORY, state=PASSED)
    return PrereqCheck(
        id=DATA_BASE_HISTORY_LAG, state=ACTION_REQUIRED,
        params={"tables": ", ".join(t.split(".", 1)[-1] for t in atrasadas)},
        remediation="databricks bundle run gold", remediation_kind="shell",
    )


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

    # Independe da Studio: o histórico é do RC18.
    try:
        checks.append(await _check_data_base_history())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Verificação do histórico de data-base falhou: %s", exc)
        checks.append(PrereqCheck(id=DATA_BASE_HISTORY, state=FAILED,
                                  detail=str(exc).splitlines()[0]))

    overall = PASSED if all(c.state in (PASSED, SKIPPED) for c in checks) else ACTION_REQUIRED
    if any(c.state == FAILED for c in checks):
        overall = FAILED
    return PrereqReport(state=overall, checks=checks, checked_at=now)
