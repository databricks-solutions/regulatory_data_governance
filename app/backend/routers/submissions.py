"""Submission tracking endpoints: history and quality gate."""

from __future__ import annotations

from fastapi import APIRouter, Query

from db import CATALOG, USE_MOCK, execute_query
from models import (
    QualityGateBlocker,
    QualityGateCheck,
    QualityGateResponse,
    SubmissionRecord,
    SubmissionsResponse,
    SubmissionSummary,
)

router = APIRouter()

_MOCK_SUBMISSIONS = [
    SubmissionRecord(
        id="sub_202603_3040_r1", document="3040", data_base="2026-03", remessa=1, parts=4,
        status="aceito", submitted_at="2026-04-10T14:00:00Z", accepted_at="2026-04-10T16:30:00Z",
        file_size_mb=3800, validator_result="approved", validator_errors=0, validator_warnings=12,
        channel="STA", submitted_by="operacoes@bankcorp.com", approved_by="diretor.designado@bankcorp.com",
        quality_gate_passed=True, quality_gate_score=96.5,
    ),
    SubmissionRecord(
        id="sub_202603_3050_w13", document="3050", data_base="2026-03-28", remessa=1, parts=1,
        status="aceito", submitted_at="2026-03-31T10:00:00Z", accepted_at="2026-03-31T11:00:00Z",
        file_size_mb=2.5, validator_result="approved", validator_errors=0, validator_warnings=0,
        channel="CADIP", submitted_by="operacoes@bankcorp.com", approved_by="diretor.designado@bankcorp.com",
        quality_gate_passed=True, quality_gate_score=98.0,
    ),
    SubmissionRecord(
        id="sub_202602_3040_r1", document="3040", data_base="2026-02", remessa=1, parts=4,
        status="rejeitado", submitted_at="2026-03-08T10:00:00Z", rejected_at="2026-03-08T14:00:00Z",
        rejection_reasons=["Critica SEM_014: IPOC divergente em 250+ operacoes"],
        file_size_mb=3750, validator_result="rejected", validator_errors=3, validator_warnings=8,
        channel="STA", submitted_by="operacoes@bankcorp.com",
        quality_gate_passed=False, quality_gate_score=89.0,
    ),
    SubmissionRecord(
        id="sub_202602_3040_r2", document="3040", data_base="2026-02", remessa=2, parts=4,
        status="aceito", submitted_at="2026-03-10T14:00:00Z", accepted_at="2026-03-10T16:00:00Z",
        file_size_mb=3760, validator_result="approved", validator_errors=0, validator_warnings=5,
        channel="STA", submitted_by="operacoes@bankcorp.com", approved_by="diretor.designado@bankcorp.com",
        quality_gate_passed=True, quality_gate_score=95.0,
    ),
]


@router.get("", response_model=SubmissionsResponse)
async def get_submissions(
    document: str | None = Query(None),
    status: str | None = Query(None),
    data_base_from: str = Query("2025-10"),
    data_base_to: str = Query("2026-12"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return history of SCR submissions to BCB."""
    if USE_MOCK:
        subs = _MOCK_SUBMISSIONS
        if document:
            subs = [s for s in subs if s.document == document]
        if status:
            subs = [s for s in subs if s.status == status]
        subs = subs[:limit]
        accepted = sum(1 for s in _MOCK_SUBMISSIONS if s.status == "aceito")
        rejected = sum(1 for s in _MOCK_SUBMISSIONS if s.status == "rejeitado")
        total = len(_MOCK_SUBMISSIONS)
        return SubmissionsResponse(
            submissions=subs,
            summary=SubmissionSummary(
                total_submissions=total, accepted=accepted, rejected=rejected,
                acceptance_rate_pct=round(accepted / max(total, 1) * 100, 1),
                avg_days_before_deadline=2.4,
            ),
        )

    rows = await execute_query(
        "SELECT documento, dt_base, remessa, parte, nome_arquivo, "
        "validador_bcb_status, validador_bcb_errors, bcb_status, bcb_descricao_retorno, "
        "dt_envio_sta, dt_resposta_bcb, enviado_no_prazo, antecedencia_dias_uteis, responsavel_aprovacao "
        f"FROM {CATALOG}.quality.quality_submissao_historico "
        "WHERE (:documento IS NULL OR documento = :documento) "
        "AND (:bcb_status IS NULL OR bcb_status = :bcb_status) "
        "AND dt_base >= :data_base_from AND dt_base <= :data_base_to "
        "ORDER BY dt_envio_sta DESC LIMIT :limit",
        {"documento": document, "bcb_status": status, "data_base_from": data_base_from, "data_base_to": data_base_to, "limit": limit},
    )
    subs = [
        SubmissionRecord(
            id=f"sub_{r['dt_base']}_{r['documento']}_r{r['remessa']}", document=r["documento"],
            data_base=r["dt_base"], remessa=r["remessa"], parts=r.get("parte", 1),
            status=r["bcb_status"], submitted_at=str(r["dt_envio_sta"]),
            file_size_mb=0, validator_result=r.get("validador_bcb_status", ""),
            validator_errors=r.get("validador_bcb_errors", 0), validator_warnings=0,
            channel="STA", submitted_by="", quality_gate_passed=True, quality_gate_score=0,
        )
        for r in rows
    ]
    return SubmissionsResponse(
        submissions=subs,
        summary=SubmissionSummary(total_submissions=len(subs), accepted=0, rejected=0, acceptance_rate_pct=0, avg_days_before_deadline=0),
    )


@router.get("/quality-gate", response_model=QualityGateResponse)
async def get_quality_gate(
    document: str = Query(..., description="3040 or 3050"),
    data_base: str = Query(..., description="Reference date"),
):
    """Return consolidated quality gate status (go/no-go for submission)."""
    if USE_MOCK:
        checks = [
            QualityGateCheck(category="syntactic_validation", name="Validacao Sintatica SCR " + document, status="passed", pass_rate_pct=100.0, last_run="2026-04-09T23:00:00Z"),
            QualityGateCheck(category="semantic_validation", name="Validacao Semantica SCR " + document, status="passed", pass_rate_pct=99.7, last_run="2026-04-09T23:00:00Z"),
            QualityGateCheck(category="completeness", name="Completude de Campos Obrigatorios", status="passed", pass_rate_pct=100.0, last_run="2026-04-09T23:00:00Z"),
        ]
        has_failed_blocking = any(c.status == "failed" and c.blocking for c in checks)
        blockers = []
        return QualityGateResponse(
            document=document, data_base=data_base,
            gate_status="blocked" if has_failed_blocking else "approved",
            overall_score=99.85,
            checks=checks, blockers=blockers,
            submission_allowed=not has_failed_blocking,
            evaluated_at="2026-04-09T23:30:00Z",
        )

    return QualityGateResponse(
        document=document, data_base=data_base, gate_status="unknown", overall_score=0,
        checks=[], blockers=[], submission_allowed=False, evaluated_at="",
    )
