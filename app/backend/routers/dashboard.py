"""Dashboard endpoints: KPIs, alerts, timeline, embed, list."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from db import CATALOG, SCHEMA_GOLD, USE_MOCK, execute_query
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
_MOCK_DIMENSIONS = [
    DimensionScore(id=1, name="Acessibilidade", score=95.0, status="conforme"),
    DimensionScore(id=2, name="Acurácia", score=92.5, status="atencao"),
    DimensionScore(id=3, name="Adaptabilidade", score=98.0, status="conforme"),
    DimensionScore(id=4, name="Clareza", score=88.0, status="atencao"),
    DimensionScore(id=5, name="Comparabilidade", score=100.0, status="conforme"),
    DimensionScore(id=6, name="Completude", score=91.0, status="conforme"),
    DimensionScore(id=7, name="Confiabilidade", score=89.5, status="atencao"),
    DimensionScore(id=8, name="Consistência", score=85.0, status="atencao"),
    DimensionScore(id=9, name="Integridade", score=78.0, status="nao_conforme"),
    DimensionScore(id=10, name="Rastreabilidade", score=90.0, status="conforme"),
    DimensionScore(id=11, name="Relevância", score=93.0, status="conforme"),
    DimensionScore(id=12, name="Tempestividade", score=97.0, status="conforme"),
]


def _mock_kpis(data_base: str) -> DashboardKPIs:
    scores = [d.score for d in _MOCK_DIMENSIONS]
    return DashboardKPIs(
        data_base=data_base,
        compliance_score=round(sum(scores) / len(scores), 1),
        dimensions=_MOCK_DIMENSIONS,
        pending_validations=PendingValidations(scr3040=3, scr3050=1),
        last_submission=LastSubmission(
            document="SCR 3050",
            data_base="2026-03-28",
            status="aceito",
            submitted_at="2026-03-30T14:22:00Z",
        ),
        alerts=[
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
        ],
        deadline=Deadline(
            date="2026-12-31",
            days_remaining=274,
            phase="Fase 1 - Fundacao",
        ),
    )


# --- Endpoints ---


@router.get("/kpis", response_model=DashboardKPIs)
async def get_dashboard_kpis(data_base: str = Query("2026-03", description="Reference month (YYYY-MM)")):
    """Return executive summary KPIs for the home page."""
    if USE_MOCK:
        return _mock_kpis(data_base)

    dim_rows = await execute_query(
        "SELECT dimensao_id, dimensao_nome, score_pct, meta_pct, status, documento "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.qualidade_dimensoes_mensal "
        "WHERE dt_base = :data_base ORDER BY dimensao_id",
        {"data_base": data_base},
    )
    # gold.qualidade_dimensoes_mensal.dimensao_id is Roman ('I'..'XII'); the
    # frontend's DimensionScore.id is int — translate.
    _ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                     "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
    dimensions = [
        DimensionScore(
            id=_ROMAN_TO_INT.get(r["dimensao_id"], 0) if isinstance(r["dimensao_id"], str) else r["dimensao_id"],
            name=r["dimensao_nome"] or "",
            score=float(r["score_pct"] or 0),
            status=r["status"] or "",
        )
        for r in dim_rows
    ]
    scores = [d.score for d in dimensions] or [0]
    return DashboardKPIs(
        data_base=data_base,
        compliance_score=round(sum(scores) / len(scores), 1),
        dimensions=dimensions,
        pending_validations=PendingValidations(),
        last_submission=LastSubmission(document="", data_base=data_base, status="", submitted_at=""),
        alerts=[],
        deadline=Deadline(date="2026-12-31", days_remaining=274, phase="Fase 1 - Fundacao"),
    )


@router.get("/alerts", response_model=list[Alert])
async def get_dashboard_alerts(limit: int = Query(10, ge=1, le=50)):
    """Return recent quality alerts."""
    if USE_MOCK:
        return [
            Alert(severity="warning", message="Reconciliacao 3040 vs COSIF: divergencia 0.08%", created_at="2026-03-29T10:00:00Z"),
            Alert(severity="error", message="Critica SEM_014: 127 operacoes com IPOC divergente", created_at="2026-03-28T22:00:00Z"),
            Alert(severity="info", message="Pipeline bronze concluido com sucesso", created_at="2026-03-28T06:00:00Z"),
        ][:limit]

    rows = await execute_query(
        "SELECT severidade, expectation_name, log_timestamp "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.violacoes_log WHERE status_resolucao = 'ABERTA' "
        "ORDER BY log_timestamp DESC LIMIT :limit",
        {"limit": limit},
    )
    # Normalize Portuguese pipeline severity vocabulary to the UI-facing one.
    _SEV_MAP = {"BLOQUEANTE": "error", "ALERTA": "warning", "INFO": "info"}
    return [
        Alert(
            severity=_SEV_MAP.get(r["severidade"], "info"),
            message=r["expectation_name"] or "",
            created_at=str(r["log_timestamp"]) if r["log_timestamp"] else "",
        )
        for r in rows
    ]


@router.get("/timeline")
async def get_dashboard_timeline(data_base: str = Query("2026-03")):
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
    "criticas": "Monitor de Críticas SCR",
    "genie": "Consulta Natural — SCR R.18",
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
            embed_url=f"{host}/explore/genie/{real_id}?o={workspace_id}",
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
                description="12 dimensoes com scores, tendencias e targets",
                type="compliance",
                last_published="2026-04-01T08:00:00Z",
            ),
            DashboardInfo(
                id=os.getenv("DASHBOARD_ID_CRITICAS", ""),
                name="Monitor de Criticas",
                description="Taxa de aprovacao/rejeicao por documento, categoria de regra e severidade",
                type="criticas",
                last_published="2026-04-01T08:00:00Z",
            ),
        ]
    )
