"""Dashboard endpoints: KPIs, alerts, timeline, embed, list."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, date

from fastapi import APIRouter, Depends, Query

from db import CATALOG, DQX_CHECKS_TABLE, DQX_METRICS_TABLE, DQX_VALIDATION_RUNS_TABLE, USE_MOCK
from i18n import get_locale
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when gold/silver tables haven't been populated yet (pipelines not run).
from db import execute_query_or_empty as execute_query
from rc18_rule_meta import meta_for
from models import (
    Alert,
    DashboardEmbed,
    DashboardInfo,
    DashboardKPIs,
    DashboardListResponse,
    Deadline,
    DimensionScore,
    LastSubmission,
    PendingValidations,
)

router = APIRouter()

# --- Mock data ---

# Canonical 12 R.18 dimensions per docs/spec/01_requirements.md §1.2.
# Todas as 12 dimensões medidas — scores/status alinhados 1:1 com os mocks de
# quality.py (_MOCK_SCORES/_MOCK_STATUSES) para que o RadarChart da home e o
# scorecard de /quality contem a mesma história.
_MOCK_DIMENSIONS = [
    DimensionScore(id=1, name="Acessibilidade", score=91.0, status="conforme"),
    DimensionScore(id=2, name="Acurácia", score=92.0, status="atencao"),
    DimensionScore(id=3, name="Adaptabilidade", score=96.5, status="conforme"),
    DimensionScore(id=4, name="Clareza", score=93.5, status="atencao"),
    DimensionScore(id=5, name="Comparabilidade", score=95.5, status="conforme"),
    DimensionScore(id=6, name="Completude", score=83.0, status="nao_conforme"),
    DimensionScore(id=7, name="Confiabilidade", score=90.5, status="conforme"),
    DimensionScore(id=8, name="Consistência", score=87.0, status="atencao"),
    DimensionScore(id=9, name="Integridade", score=98.0, status="conforme"),
    DimensionScore(id=10, name="Rastreabilidade", score=91.5, status="conforme"),
    DimensionScore(id=11, name="Relevância", score=94.0, status="atencao"),
    DimensionScore(id=12, name="Tempestividade", score=96.0, status="conforme"),
]

# English mirror of _MOCK_DIMENSIONS — same ids/scores/status codes, only the
# human-readable `name` is translated (see GLOSSARY in CLAUDE/spec).
_MOCK_DIMENSIONS_EN = [
    DimensionScore(id=1, name="Accessibility", score=91.0, status="conforme"),
    DimensionScore(id=2, name="Accuracy", score=92.0, status="atencao"),
    DimensionScore(id=3, name="Adaptability", score=96.5, status="conforme"),
    DimensionScore(id=4, name="Clarity", score=93.5, status="atencao"),
    DimensionScore(id=5, name="Comparability", score=95.5, status="conforme"),
    DimensionScore(id=6, name="Completeness", score=83.0, status="nao_conforme"),
    DimensionScore(id=7, name="Reliability", score=90.5, status="conforme"),
    DimensionScore(id=8, name="Consistency", score=87.0, status="atencao"),
    DimensionScore(id=9, name="Integrity", score=98.0, status="conforme"),
    DimensionScore(id=10, name="Traceability", score=91.5, status="conforme"),
    DimensionScore(id=11, name="Relevance", score=94.0, status="atencao"),
    DimensionScore(id=12, name="Timeliness", score=96.0, status="conforme"),
]


def _mock_kpis(data_base: str, locale: str = "pt") -> DashboardKPIs:
    # Mesma semântica do real-mode: dimensões `sem_regras` ficam fora da média.
    en = locale == "en"
    dimensions = _MOCK_DIMENSIONS_EN if en else _MOCK_DIMENSIONS
    measured = [d.score for d in dimensions if d.status != "sem_regras"]
    if en:
        alerts = [
            Alert(
                severity="warning",
                message="Reconciliation 3040 vs COSIF: 0.08% divergence in the total balance",
                created_at="2026-03-29T10:00:00Z",
            ),
            Alert(
                severity="info",
                message="New 3050 V11 layout version active as of 07/11/2025",
                created_at="2026-03-28T08:00:00Z",
            ),
        ]
        phase = "Phase 1 - Foundation"
    else:
        alerts = [
            Alert(
                severity="warning",
                message="Reconciliacao 3040 vs COSIF: divergencia 0.08% no saldo total",
                created_at="2026-03-29T10:00:00Z",
            ),
            Alert(
                severity="info",
                message="Nova versao de leiaute 3050 V11 ativa a partir de 07/11/2025",
                created_at="2026-03-28T08:00:00Z",
            ),
        ]
        phase = "Fase 1 - Fundacao"
    return DashboardKPIs(
        data_base=data_base,
        compliance_score=round(sum(measured) / len(measured), 1) if measured else 0.0,
        dimensions=dimensions,
        pending_validations=PendingValidations(scr3040=3, scr3050=1),
        last_submission=LastSubmission(
            document="SCR 3050",
            data_base="2026-03-28",
            status="aceito",
            submitted_at="2026-03-30T14:22:00Z",
        ),
        alerts=alerts,
        deadline=Deadline(
            date="2026-12-31",
            days_remaining=_days_until_deadline(),
            phase=phase,
        ),
    )


# --- Endpoints ---


@router.get("/kpis", response_model=DashboardKPIs)
async def get_dashboard_kpis(
    data_base: str = Query("2026-03", description="Reference month (YYYY-MM)"),
    locale: str = Depends(get_locale),
):
    """Return executive summary KPIs for the home page."""
    if USE_MOCK:
        return _mock_kpis(data_base, locale)

    # Real-mode: agrega das tabelas de execução do DQX Studio.
    return await _build_kpis_from_dqx_studio(data_base)


# Mapping `R.18 deadline` (BACEN final date for accelerator compliance).
_R18_DEADLINE = date(2026, 12, 31)
_R18_DIM_NAMES = {
    1: "Acessibilidade", 2: "Acurácia", 3: "Adaptabilidade", 4: "Clareza",
    5: "Comparabilidade", 6: "Completude", 7: "Confiabilidade", 8: "Consistência",
    9: "Integridade", 10: "Rastreabilidade", 11: "Relevância", 12: "Tempestividade",
}


def _days_until_deadline() -> int:
    delta = (_R18_DEADLINE - date.today()).days
    return max(delta, 0)


def _deadline_phase(days: int) -> str:
    # Faixas grosseiras pra dar contexto humano ao número de dias.
    if days > 270:    return "Fase 1 - Fundação"
    if days > 180:    return "Fase 2 - Dados e Qualidade"
    if days > 90:     return "Fase 3 - Reconciliação e XML"
    if days > 30:     return "Fase 4 - Governança e Relatório"
    return "Fase 5 - Auditoria e Go-Live"


async def _build_kpis_from_dqx_studio(data_base: str) -> DashboardKPIs:
    """Compõe KPIs a partir das tabelas de execução do DQX Studio.

    Reusa a mesma lógica de agregação por dimensão usada pela rota
    /quality/dimensions (latest run per source_table_fqn → check_metrics).
    Calcula contagens de violações por documento (3040/3050) e timestamp do
    último run para o card "Última Execução".
    """
    # 1. Latest SUCCESS runs per source_table_fqn (qualquer silver RC18)
    runs = await execute_query(
        "WITH ranked AS ("
        "  SELECT run_id, source_table_fqn, total_rows, invalid_rows, created_at,"
        "         ROW_NUMBER() OVER (PARTITION BY source_table_fqn ORDER BY created_at DESC) AS rn"
        f"  FROM {DQX_VALIDATION_RUNS_TABLE}"
        "  WHERE status = 'SUCCESS'"
        "    AND source_table_fqn LIKE 'rc18_catalog.silver.%'"
        ") SELECT run_id, source_table_fqn, total_rows, invalid_rows, created_at "
        "FROM ranked WHERE rn = 1",
        {},
    )
    last_run_at = ""
    last_table = ""
    if runs:
        runs_sorted = sorted(runs, key=lambda r: str(r.get("created_at") or ""), reverse=True)
        last_run_at = str(runs_sorted[0].get("created_at") or "")
        last_table = runs_sorted[0].get("source_table_fqn") or ""

    # 2. check_metrics + active rules → por-dimensão agg + pending counts.
    by_dim: dict[int, dict] = {}
    pending = {"3040": 0, "3050": 0}
    if runs:
        quoted = ",".join(f"'{r['run_id']}'" for r in runs)
        metrics_rows = await execute_query(
            "SELECT run_id, metric_value AS check_metrics_json "
            f"FROM {DQX_METRICS_TABLE} "
            f"WHERE metric_name = 'check_metrics' AND run_id IN ({quoted})",
            {},
        )
        metrics_by_run = {m["run_id"]: m for m in metrics_rows}

        # Cache user_metadata for the rules (used for dimensao_r18 tag).
        rule_rows = await execute_query(
            f"SELECT CAST(check AS STRING) AS checks FROM {DQX_CHECKS_TABLE} WHERE status IN ('active','approved')",
            {},
        )
        rule_um_by_name: dict[str, dict] = {}
        for r in rule_rows:
            try:
                parsed = json.loads(r["checks"]) if isinstance(r.get("checks"), str) else (r.get("checks") or [])
            except (json.JSONDecodeError, TypeError):
                continue
            items = parsed if isinstance(parsed, list) else [parsed]
            for chk in items:
                if isinstance(chk, dict):
                    name = chk.get("name") or ((chk.get("check") or {}).get("arguments") or {}).get("name")
                    if name:
                        rule_um_by_name[name] = chk.get("user_metadata") or {}

        for r in runs:
            total = int(r.get("total_rows") or 0)
            table_fqn = r.get("source_table_fqn") or ""
            doc = "3040" if "scr3040" in table_fqn.lower() else "3050" if "scr3050" in table_fqn.lower() else ""
            cm = metrics_by_run.get(r["run_id"])
            if not cm:
                continue
            try:
                check_metrics = json.loads(cm["check_metrics_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(check_metrics, list):
                continue
            for cmrow in check_metrics:
                check_name = cmrow.get("check_name")
                if not check_name:
                    continue
                # Filtra runs antigos cujas regras foram deletadas de
                # dq_quality_rules — mesma semântica do /validations/*/results
                # (validation.py:_fetch_studio_results). Sem isso, o dashboard
                # contava check_metrics de regras stale (ex: source='ui' já
                # apagadas) e divergia das Críticas SCR.
                if check_name not in rule_um_by_name:
                    continue
                um = rule_um_by_name[check_name]
                meta = meta_for(check_name, table_fqn=table_fqn, user_metadata=um)
                err = int(cmrow.get("error_count") or 0)
                warn = int(cmrow.get("warning_count") or 0)
                affected = err + warn
                dim_id = meta["dimension_r18"]
                bucket = by_dim.setdefault(dim_id, {"total": 0, "invalid": 0, "rules": 0})
                bucket["total"] += total
                bucket["invalid"] += affected
                bucket["rules"] += 1
                if affected > 0 and doc in pending:
                    pending[doc] += 1

    # 3. Build DimensionScore list for the radar chart (12 dimensions).
    dims: list[DimensionScore] = []
    target = 95.0
    measured_scores: list[float] = []
    for dim_id in range(1, 13):
        agg = by_dim.get(dim_id, {"total": 0, "invalid": 0, "rules": 0})
        if agg["rules"] == 0:
            # Sem regras vinculadas → não conta no overall e marca "sem_regras"
            score = 0.0
            status = "sem_regras"
        else:
            score = round(100 * (agg["total"] - agg["invalid"]) / agg["total"], 1) if agg["total"] else 100.0
            status = (
                "conforme" if score >= target
                else "atencao" if score >= target - 10
                else "nao_conforme"
            )
            measured_scores.append(score)
        dims.append(DimensionScore(
            id=dim_id,
            name=_R18_DIM_NAMES.get(dim_id, ""),
            score=score,
            status=status,
        ))
    compliance = round(sum(measured_scores) / len(measured_scores), 1) if measured_scores else 0.0

    days_left = _days_until_deadline()
    return DashboardKPIs(
        data_base=data_base,
        compliance_score=compliance,
        dimensions=dims,
        pending_validations=PendingValidations(
            scr3040=pending.get("3040", 0),
            scr3050=pending.get("3050", 0),
        ),
        last_submission=LastSubmission(
            document=last_table.split(".")[-1] if last_table else "",
            data_base=data_base,
            status="executado" if last_run_at else "pendente",
            submitted_at=last_run_at,
        ),
        alerts=[],
        deadline=Deadline(
            date=_R18_DEADLINE.isoformat(),
            days_remaining=days_left,
            phase=_deadline_phase(days_left),
        ),
    )


@router.get("/alerts", response_model=list[Alert])
async def get_dashboard_alerts(
    limit: int = Query(10, ge=1, le=50),
    locale: str = Depends(get_locale),
):
    """Return recent quality alerts."""
    if USE_MOCK:
        if locale == "en":
            return [
                Alert(severity="warning", message="Reconciliation 3040 vs COSIF: 0.08% divergence", created_at="2026-03-29T10:00:00Z"),
                Alert(severity="error", message="Critica SEM_014: 127 operations with divergent IPOC", created_at="2026-03-28T22:00:00Z"),
                Alert(severity="info", message="Bronze pipeline completed successfully", created_at="2026-03-28T06:00:00Z"),
            ][:limit]
        return [
            Alert(severity="warning", message="Reconciliacao 3040 vs COSIF: divergencia 0.08%", created_at="2026-03-29T10:00:00Z"),
            Alert(severity="error", message="Critica SEM_014: 127 operacoes com IPOC divergente", created_at="2026-03-28T22:00:00Z"),
            Alert(severity="info", message="Pipeline bronze concluido com sucesso", created_at="2026-03-28T06:00:00Z"),
        ][:limit]

    # Lê incidentes abertos de governance.incidents (R.18 Art.2 §3).
    # Quando a tabela não existe (setup_job não rodou), execute_query_or_empty
    # retorna lista vazia — o card "Alertas Ativos" mostra estado vazio.
    rows = await execute_query(
        "SELECT severidade, mensagem, detected_at "
        f"FROM {CATALOG}.governance.incidents "
        "WHERE status NOT IN ('resolved','validated') "
        "ORDER BY detected_at DESC LIMIT :limit",
        {"limit": limit},
    )
    _SEV_MAP = {"BLOQUEANTE": "error", "ALERTA": "warning", "INFO": "info"}
    return [
        Alert(
            severity=_SEV_MAP.get(r.get("severidade") or "", "info"),
            message=r.get("mensagem") or "",
            created_at=str(r.get("detected_at")) if r.get("detected_at") else "",
        )
        for r in rows
    ]


@router.get("/timeline")
async def get_dashboard_timeline():
    """Return project implementation timeline milestones."""
    return {
        "phases": [
            {"id": 1, "name": "Fase 1 - Fundacao", "start": "2026-04-01", "end": "2026-06-30", "status": "in_progress", "progress_pct": 15},
            {"id": 2, "name": "Fase 2 - Dados e Qualidade", "start": "2026-07-01", "end": "2026-08-31", "status": "pending", "progress_pct": 0},
            {"id": 3, "name": "Fase 3 - Reconciliacao e XML", "start": "2026-09-01", "end": "2026-10-31", "status": "pending", "progress_pct": 0},
            {"id": 4, "name": "Fase 4 - Governanca e Relatorio", "start": "2026-11-01", "end": "2026-11-30", "status": "pending", "progress_pct": 0},
            {"id": 5, "name": "Fase 5 - Auditoria e Go-Live", "start": "2026-12-01", "end": "2026-12-31", "status": "pending", "progress_pct": 0},
        ],
        "deadline": "2026-12-31",
    }


# Map friendly keys to actual dashboard IDs from env vars
DASHBOARD_KEY_MAP = {
    "conformidade": os.getenv("DASHBOARD_ID_CONFORMIDADE", ""),
    "criticas": os.getenv("DASHBOARD_ID_CRITICAS", ""),
    "genie": os.getenv("GENIE_SPACE_ID", ""),
}
DASHBOARD_NAMES = {
    "conformidade": "Painel de Conformidade R.18",
    "criticas": "Monitor de Incidentes de Qualidade R.18",
    "genie": "Genie Agent — SCR R.18",
}


@router.get("/embed/{key}", response_model=DashboardEmbed)
async def get_dashboard_embed(key: str):
    """Return embed URL for a Lakeview dashboard by key or ID.

    The embed URL is always built from the live workspace config — it does not
    depend on USE_MOCK (which only gates business data). A mock URL here would
    redirect the iframe through Azure AD login and get blocked by X-Frame-Options.
    """
    real_id = DASHBOARD_KEY_MAP.get(key, key)
    name = DASHBOARD_NAMES.get(key, "Dashboard")

    import re
    from databricks.sdk import WorkspaceClient
    try:
        w = WorkspaceClient()
        host = w.config.host.rstrip("/")
    except Exception:
        host = ""
    ws_match = re.search(r"adb-(\d+)", host)
    workspace_id = ws_match.group(1) if ws_match else ""

    if key == "genie":
        return DashboardEmbed(
            dashboard_id=real_id,
            dashboard_name=name,
            embed_url=f"{host}/embed/genie/rooms/{real_id}?o={workspace_id}",
            embed_token="",
            token_expires_at=datetime.now(timezone.utc).isoformat(),
        )

    if not USE_MOCK:
        try:
            dashboard = w.lakeview.get(dashboard_id=real_id)
            name = dashboard.display_name or name
        except Exception:
            pass
    return DashboardEmbed(
        dashboard_id=real_id,
        dashboard_name=name,
        embed_url=f"{host}/embed/dashboardsv3/{real_id}?o={workspace_id}",
        embed_token="token-placeholder",
        token_expires_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/list", response_model=DashboardListResponse)
async def list_dashboards():
    """Return list of available Lakeview dashboards."""
    return DashboardListResponse(
        dashboards=[
            DashboardInfo(
                id=os.getenv("DASHBOARD_ID_CONFORMIDADE", ""),
                name="Painel de Conformidade R.18",
                description="Score das 12 dimensoes R.18 derivado de governance.incidents (DQX Studio)",
                type="compliance",
                last_published="2026-04-01T08:00:00Z",
            ),
            DashboardInfo(
                id=os.getenv("DASHBOARD_ID_CRITICAS", ""),
                name="Monitor de Incidentes de Qualidade R.18",
                description="Ciclo de vida dos incidentes DQX por dimensao R.18 (funil, TMR, top violacoes)",
                type="criticas",
                last_published="2026-04-01T08:00:00Z",
            ),
        ]
    )
