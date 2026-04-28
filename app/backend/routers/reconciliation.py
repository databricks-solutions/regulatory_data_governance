"""Reconciliation endpoints: summary and detail."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, USE_MOCK, execute_query
from models import (
    Pagination,
    ReconChecks,
    ReconDetailCheck,
    ReconciliationDetailResponse,
    ReconciliationItem,
    ReconciliationSummaryResponse,
)

router = APIRouter()

_VALID_RECON_TYPES = {"3040_vs_cosif", "3040_vs_3050", "3040_vs_internal", "3050_vs_internal"}

_MOCK_RECON = [
    ReconciliationItem(type="3040_vs_cosif", name="SCR 3040 vs COSIF 4010", status="passed", executed_at="2026-03-29T08:00:00Z", checks=ReconChecks(total=18, passed=17, failed=0, warning=1), max_divergence_pct=0.08, tolerance_pct=0.1),
    ReconciliationItem(type="3040_vs_3050", name="SCR 3040 vs SCR 3050", status="passed", executed_at="2026-03-31T10:00:00Z", checks=ReconChecks(total=35, passed=33, failed=0, warning=2), max_divergence_pct=0.32, tolerance_pct=0.5),
    ReconciliationItem(type="3040_vs_internal", name="SCR 3040 vs Sistemas Internos", status="passed", executed_at="2026-03-28T22:00:00Z", checks=ReconChecks(total=12, passed=12, failed=0, warning=0), max_divergence_pct=0.0, tolerance_pct=0.0),
    ReconciliationItem(type="3050_vs_internal", name="SCR 3050 vs Sistemas Internos", status="warning", executed_at="2026-03-28T22:30:00Z", checks=ReconChecks(total=10, passed=9, failed=0, warning=1), max_divergence_pct=0.45, tolerance_pct=0.5),
]

_MOCK_COSIF_DETAILS = [
    ReconDetailCheck(rule_id="T02", rule_name="Total titulos descontados vs COSIF", scr_value=1234567890.12, cosif_value=1234567890.12, divergence=0.0, divergence_pct=0.0, tolerance_pct=0.1, status="passed", cosif_account="1.6.1.00.00-8"),
    ReconDetailCheck(rule_id="T03", rule_name="Total emprestimos vs COSIF", scr_value=9876543210.50, cosif_value=9876543210.50, divergence=0.0, divergence_pct=0.0, tolerance_pct=0.1, status="passed", cosif_account="1.6.2.00.00-1"),
    ReconDetailCheck(rule_id="M01", rule_name="Divergencia emprestimos capital de giro", scr_value=98765432.50, cosif_value=98845678.20, divergence=80245.70, divergence_pct=0.08, tolerance_pct=0.1, status="warning", modality="0201", cosif_account="1.6.1.10.20-3"),
    ReconDetailCheck(rule_id="M02", rule_name="Divergencia financiamento imobiliario", scr_value=5432100000.00, cosif_value=5432100000.00, divergence=0.0, divergence_pct=0.0, tolerance_pct=0.1, status="passed", modality="0401", cosif_account="1.6.3.00.00-4"),
]

_MOCK_3040_3050_DETAILS = [
    ReconDetailCheck(rule_id="EQUIV_001", rule_name="Capital de giro - livre PJ", scr_value=98765432.50, cosif_value=98765000.00, divergence=432.50, divergence_pct=0.0004, tolerance_pct=0.5, status="passed", modality="0201"),
    ReconDetailCheck(rule_id="EQUIV_002", rule_name="Financiamento imobiliario - direcionado PF", scr_value=5432100000.00, cosif_value=5432000000.00, divergence=100000.00, divergence_pct=0.0018, tolerance_pct=0.5, status="passed", modality="0401"),
    ReconDetailCheck(rule_id="EQUIV_003", rule_name="Credito pessoal nao consignado", scr_value=2500000000.00, cosif_value=2499875000.00, divergence=125000.00, divergence_pct=0.005, tolerance_pct=0.5, status="passed", modality="0204"),
]


@router.get("/summary", response_model=ReconciliationSummaryResponse)
async def get_reconciliation_summary(data_base: str = Query("2026-03")):
    """Return summary of all reconciliation checks."""
    if USE_MOCK:
        return ReconciliationSummaryResponse(data_base=data_base, reconciliations=_MOCK_RECON)

    rows = await execute_query(
        "SELECT tipo_reconciliacao, total_regras, regras_aprovadas, regras_alerta, "
        "regras_bloqueadas, divergencia_maxima_pct, status_geral, status_envio, run_timestamp "
        f"FROM {CATALOG}.quality.quality_reconciliation_results "
        "WHERE dt_base = :data_base ORDER BY run_timestamp DESC",
        {"data_base": data_base},
    )
    items = [
        ReconciliationItem(
            type=r["tipo_reconciliacao"], name=r["tipo_reconciliacao"], status=r["status_geral"],
            executed_at=str(r["run_timestamp"]),
            checks=ReconChecks(total=r["total_regras"], passed=r["regras_aprovadas"], failed=r["regras_bloqueadas"], warning=r["regras_alerta"]),
            max_divergence_pct=r["divergencia_maxima_pct"], tolerance_pct=0.1,
        )
        for r in rows
    ]
    return ReconciliationSummaryResponse(data_base=data_base, reconciliations=items)


@router.get("/{recon_type}/details", response_model=ReconciliationDetailResponse)
async def get_reconciliation_details(
    recon_type: str,
    data_base: str = Query("2026-03"),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return detailed divergences for a specific reconciliation type."""
    if recon_type not in _VALID_RECON_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown recon type. Must be one of: {', '.join(sorted(_VALID_RECON_TYPES))}")

    if USE_MOCK:
        if recon_type == "3040_vs_cosif":
            checks = _MOCK_COSIF_DETAILS
        elif recon_type == "3040_vs_3050":
            checks = _MOCK_3040_3050_DETAILS
        else:
            checks = [
                ReconDetailCheck(rule_id="INT_001", rule_name="Saldo total vs core banking", scr_value=50000000000.00, cosif_value=50000000000.00, divergence=0.0, divergence_pct=0.0, tolerance_pct=0.0, status="passed"),
            ]
        if status:
            checks = [c for c in checks if c.status == status]
        total = len(checks)
        recon_item = next((r for r in _MOCK_RECON if r.type == recon_type), _MOCK_RECON[0])
        return ReconciliationDetailResponse(
            data_base=data_base, recon_type=recon_type, executed_at=recon_item.executed_at,
            checks=checks,
            pagination=Pagination(page=page, page_size=page_size, total_results=total, total_pages=1),
        )

    rows = await execute_query(
        "SELECT rule_id, rule_name, scr_value, cosif_value, divergence, divergence_pct, "
        "tolerance_pct, status, modality, cosif_account "
        f"FROM {CATALOG}.gold.reconciliacao_cosif "
        "WHERE data_base = :data_base LIMIT :page_size OFFSET :offset",
        {"data_base": data_base, "page_size": page_size, "offset": (page - 1) * page_size},
    )
    checks = [ReconDetailCheck(**r) for r in rows]
    return ReconciliationDetailResponse(
        data_base=data_base, recon_type=recon_type, executed_at="",
        checks=checks, pagination=Pagination(page=page, page_size=page_size),
    )
