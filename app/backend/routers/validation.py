"""Validation endpoints: results, trigger, status, runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, SCHEMA_SILVER, USE_MOCK, execute_query
from models import (
    Pagination,
    RunProgress,
    RunSummary,
    TriggerValidationRequest,
    TriggerValidationResponse,
    ValidationResult,
    ValidationResultsResponse,
    ValidationRunsResponse,
    ValidationRunStatus,
    ValidationSummary,
)

router = APIRouter()

# silver.criticas_results emits Portuguese vocabulary; normalize to the UI-facing one.
_DIM_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                     "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
_SEVERITY_MAP = {"BLOQUEANTE": "error", "ALERTA": "warning", "INFO": "info"}
_STATUS_MAP = {"APROVADO": "pass", "REPROVADO": "fail", "ALERTA": "warning"}


def _normalize_critica_row(r: dict) -> ValidationResult:
    """Map a silver.criticas_results row to the UI ValidationResult shape."""
    sev_raw = r.get("severidade") or ""
    status_raw = r.get("status") or ""
    dim_raw = r.get("dimension_r18")
    dim_int = (
        dim_raw if isinstance(dim_raw, int)
        else _DIM_ROMAN_TO_INT.get(str(dim_raw), 0)
    )
    total = int(r.get("registros_avaliados") or 0)
    nc = int(r.get("registros_nao_conformes") or 0)
    pct = float(r.get("taxa_conformidade_pct") or 0)
    return ValidationResult(
        rule_id=r.get("critica_id") or "",
        rule_name=r.get("critica_descricao") or "",
        rule_type=r.get("grupo") or "",
        severity=_SEVERITY_MAP.get(sev_raw, sev_raw.lower() if sev_raw else "info"),
        dimension_r18=dim_int,
        dimension_name="",
        status=_STATUS_MAP.get(status_raw, status_raw.lower() if status_raw else "pass"),
        affected_records=nc,
        total_records=total,
        affected_pct=round(100 - pct, 4) if total else 0.0,
        description=r.get("critica_descricao") or "",
        sample_ipocs=[],
        nivel_verificacao=1,
    )

_MOCK_RULES_3040 = [
    # ── Nível 1: Verificações genéricas básicas (Completude, Consistência, Adaptabilidade, Integridade) ──
    # Mapping uses the spec-canonical 12 R.18 dimensions per docs/spec/01_requirements.md §1.2:
    # 1 Acessibilidade, 2 Acurácia, 3 Adaptabilidade, 4 Clareza, 5 Comparabilidade,
    # 6 Completude, 7 Confiabilidade, 8 Consistência, 9 Integridade, 10 Rastreabilidade,
    # 11 Relevância, 12 Tempestividade.
    ValidationResult(rule_id="N1_001", rule_name="Campos obrigatórios vazios", rule_type="syntactic", severity="error", dimension_r18=6, dimension_name="Completude", status="fail", affected_records=42, total_records=50000000, affected_pct=0.000084, description="Campo DtContr ausente em 42 operações. Campos obrigatórios não podem ser nulos conforme leiaute CADOC.", sample_ipocs=["12345678020101234567890CONTR001"], nivel_verificacao=1),
    ValidationResult(rule_id="N1_002", rule_name="Idade do cliente > 150 anos", rule_type="syntactic", severity="error", dimension_r18=2, dimension_name="Acurácia", status="fail", affected_records=8, total_records=50000000, affected_pct=0.000016, description="8 operações com data de nascimento do cliente resultando em idade superior a 150 anos — provável erro de preenchimento.", sample_ipocs=["IPOC_99887766..."], nivel_verificacao=1),
    ValidationResult(rule_id="N1_003", rule_name="Chaves-únicas duplicadas", rule_type="syntactic", severity="error", dimension_r18=8, dimension_name="Consistência", status="fail", affected_records=15, total_records=50000000, affected_pct=0.00003, description="15 registros com IPOC duplicado na mesma data-base. Chaves-únicas devem ser exclusivas por período (livres de contradicoes — Art. 2, §2, VIII).", sample_ipocs=["IPOC_12345678...", "IPOC_12345678..."], nivel_verificacao=1),
    ValidationResult(rule_id="N1_004", rule_name="Datas fora do padrão", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="fail", affected_records=23, total_records=50000000, affected_pct=0.000046, description="23 operações com DtVencOp em formato inválido (esperado AAAA-MM-DD). Datas devem seguir o padrão ISO 8601 do leiaute V11.", sample_ipocs=[], nivel_verificacao=1),
    ValidationResult(rule_id="N1_005", rule_name="Formato CADOC inválido", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="fail", affected_records=5, total_records=50000000, affected_pct=0.00001, description="5 registros com estrutura de arquivo fora do leiaute CADOC Doc 3040 V11. Campos com tamanho ou tipo incompatível.", sample_ipocs=[], nivel_verificacao=1),
    ValidationResult(rule_id="N1_006", rule_name="Formato CNPJ IF válido", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="pass", affected_records=0, total_records=50000000, affected_pct=0.0, description="CNPJ da IF no formato correto (14 dígitos com verificadores válidos).", sample_ipocs=[], nivel_verificacao=1),
    ValidationResult(rule_id="N1_007", rule_name="Modalidade pertence ao domínio", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="pass", affected_records=0, total_records=50000000, affected_pct=0.0, description="Todas as modalidades pertencem ao domínio válido do Doc 3040.", sample_ipocs=[], nivel_verificacao=1),
    ValidationResult(rule_id="N1_008", rule_name="CPF/CNPJ cliente mascarado", rule_type="syntactic", severity="warning", dimension_r18=9, dimension_name="Integridade", status="pass", affected_records=0, total_records=50000000, affected_pct=0.0, description="Dados sensíveis de CPF/CNPJ devidamente mascarados nos logs e interfaces conforme LGPD (controle de acesso — Art. 2, §2, IX).", sample_ipocs=[], nivel_verificacao=1),

    # ── Nível 2: Coerência com meses anteriores ──
    ValidationResult(rule_id="N2_001", rule_name="Contrato inadimplente sem histórico anterior", rule_type="inter_document", severity="error", dimension_r18=8, dimension_name="Consistência", status="fail", affected_records=37, total_records=50000000, affected_pct=0.000074, description="37 contratos marcados como inadimplentes há 120 dias no arquivo atual, porém inexistentes no arquivo do mês anterior. Operações com atraso significativo devem ter histórico progressivo.", sample_ipocs=["IPOC_CONTR_2024001...", "IPOC_CONTR_2024002..."], nivel_verificacao=2),
    ValidationResult(rule_id="N2_002", rule_name="Saldo 3040 vs COSIF mês anterior", rule_type="inter_document", severity="warning", dimension_r18=8, dimension_name="Consistência", status="warning", affected_records=3, total_records=18, affected_pct=16.67, description="3 modalidades com divergência > 5% entre saldo Doc 3040 atual e saldo COSIF do mês anterior. Variações abruptas devem ser justificadas.", sample_ipocs=[], nivel_verificacao=2),
    ValidationResult(rule_id="N2_003", rule_name="Operações encerradas reaparecendo", rule_type="inter_document", severity="error", dimension_r18=8, dimension_name="Consistência", status="fail", affected_records=12, total_records=50000000, affected_pct=0.000024, description="12 operações com situação 'encerrada' no mês anterior reapareceram como ativas no arquivo atual. Operações liquidadas não devem reaparecer.", sample_ipocs=[], nivel_verificacao=2),
    ValidationResult(rule_id="N2_004", rule_name="Variação abrupta de saldo individual", rule_type="inter_document", severity="warning", dimension_r18=7, dimension_name="Confiabilidade", status="warning", affected_records=89, total_records=50000000, affected_pct=0.000178, description="89 operações com variação de saldo devedor > 200% em relação ao mês anterior sem evento de cessão ou renegociação registrado.", sample_ipocs=[], nivel_verificacao=2),

    # ── Nível 3: Regras negociais (definidas pelo Curador de Dados / Gestor da Informação) ──
    ValidationResult(rule_id="N3_001", rule_name="Limite de crédito vs política interna", rule_type="business", severity="error", dimension_r18=11, dimension_name="Relevância", status="fail", affected_records=18, total_records=50000000, affected_pct=0.000036, description="18 operações de crédito com valor acima do limite da alçada aprovada para a modalidade, conforme política interna definida pelo Gestor da Informação.", sample_ipocs=[], nivel_verificacao=3),
    ValidationResult(rule_id="N3_002", rule_name="Classificação de risco vs regra de provisionamento", rule_type="business", severity="error", dimension_r18=2, dimension_name="Acurácia", status="fail", affected_records=54, total_records=50000000, affected_pct=0.000108, description="54 operações com classificação de risco incompatível com os dias de atraso, segundo regra de provisionamento definida pela área de Risco (Resolução 2.682). Curador: Gestão de Risco de Crédito.", sample_ipocs=[], nivel_verificacao=3),
    ValidationResult(rule_id="N3_003", rule_name="Garantia mínima por modalidade", rule_type="business", severity="warning", dimension_r18=11, dimension_name="Relevância", status="warning", affected_records=7, total_records=50000000, affected_pct=0.000014, description="7 operações de crédito imobiliário sem garantia real vinculada, contrariando regra negocial do Curador de Dados da área de Habitação.", sample_ipocs=[], nivel_verificacao=3),
    ValidationResult(rule_id="N3_004", rule_name="Prazo máximo por produto", rule_type="business", severity="warning", dimension_r18=11, dimension_name="Relevância", status="warning", affected_records=11, total_records=50000000, affected_pct=0.000022, description="11 operações com prazo de vencimento superior ao máximo permitido para o produto, conforme definição do Gestor da Informação da área Comercial.", sample_ipocs=[], nivel_verificacao=3),
]


@router.get("/scr3040/results", response_model=ValidationResultsResponse)
async def get_validation_results_3040(
    data_base: str = Query("2026-03"),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    modality: str | None = Query(None),
    rule_type: str | None = Query(None),
    dimension_r18: int | None = Query(None),
    nivel_verificacao: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return validation results for SCR 3040 criticas."""
    if USE_MOCK:
        results = _MOCK_RULES_3040
        if severity:
            results = [r for r in results if r.severity == severity]
        if status:
            results = [r for r in results if r.status == status]
        if rule_type:
            results = [r for r in results if r.rule_type == rule_type]
        if dimension_r18:
            results = [r for r in results if r.dimension_r18 == dimension_r18]
        if nivel_verificacao:
            results = [r for r in results if r.nivel_verificacao == nivel_verificacao]
        total = len(results)
        start = (page - 1) * page_size
        paged = results[start : start + page_size]
        passed = sum(1 for r in _MOCK_RULES_3040 if r.status == "pass")
        failed = sum(1 for r in _MOCK_RULES_3040 if r.status == "fail")
        warnings = sum(1 for r in _MOCK_RULES_3040 if r.status == "warning")
        return ValidationResultsResponse(
            data_base=data_base,
            run_id="run_20260330_142200",
            run_status="completed",
            run_completed_at="2026-03-30T14:45:00Z",
            summary=ValidationSummary(
                total_rules=len(_MOCK_RULES_3040),
                passed=passed,
                failed=failed,
                warnings=warnings,
                pass_rate_pct=round(passed / len(_MOCK_RULES_3040) * 100, 1),
            ),
            results=paged,
            pagination=Pagination(page=page, page_size=page_size, total_results=total, total_pages=max(1, (total + page_size - 1) // page_size)),
        )

    rows = await execute_query(
        "SELECT critica_id, critica_descricao, grupo, severidade, dimension_r18, status, "
        "registros_avaliados, registros_conformes, registros_nao_conformes, "
        "taxa_conformidade_pct, sample_falhas "
        f"FROM {CATALOG}.{SCHEMA_SILVER}.criticas_results "
        "WHERE dt_base = :data_base AND documento = '3040' "
        "ORDER BY severidade DESC, registros_nao_conformes DESC "
        "LIMIT :page_size OFFSET :offset",
        {"data_base": data_base, "page_size": page_size, "offset": (page - 1) * page_size},
    )
    results = [_normalize_critica_row(r) for r in rows]
    # Aggregate summary across the same (data_base, documento) scope, not just this page.
    summary_rows = await execute_query(
        "SELECT status, COUNT(*) AS n "
        f"FROM {CATALOG}.{SCHEMA_SILVER}.criticas_results "
        "WHERE dt_base = :data_base AND documento = '3040' "
        "GROUP BY status",
        {"data_base": data_base},
    )
    by_status = {s["status"]: int(s["n"] or 0) for s in summary_rows}
    total_rules = sum(by_status.values())
    passed = by_status.get("APROVADO", 0)
    failed = by_status.get("REPROVADO", 0)
    warnings = by_status.get("ALERTA", 0)
    pass_rate = round(passed / total_rules * 100, 1) if total_rules else 0.0
    return ValidationResultsResponse(
        data_base=data_base, run_id="", run_status="completed",
        summary=ValidationSummary(total_rules=total_rules, passed=passed, failed=failed, warnings=warnings, pass_rate_pct=pass_rate),
        results=results,
        pagination=Pagination(page=page, page_size=page_size, total_results=total_rules, total_pages=max(1, (total_rules + page_size - 1) // page_size)),
    )


@router.get("/scr3050/results", response_model=ValidationResultsResponse)
async def get_validation_results_3050(
    data_base: str = Query("2026-03"),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    critica_group: int | None = Query(None),
    layout_version: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return validation results for SCR 3050 criticas."""
    if USE_MOCK:
        mock_results_3050 = [
            # Nível 1 — dimension_r18 ids per spec-canonical 12 (docs/spec/01_requirements.md §1.2)
            ValidationResult(rule_id="N1_050_001", rule_name="Campos obrigatórios TXB", rule_type="syntactic", severity="error", dimension_r18=6, dimension_name="Completude", status="fail", affected_records=3, total_records=5000000, affected_pct=0.00006, description="3 registros com campo encargo ausente no leiaute TXB.", sample_ipocs=[], nivel_verificacao=1),
            ValidationResult(rule_id="N1_050_002", rule_name="Formato data período", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="pass", affected_records=0, total_records=5000000, affected_pct=0.0, description="Periodicidade diário/mensal com datas no formato válido do leiaute V11.", sample_ipocs=[], nivel_verificacao=1),
            ValidationResult(rule_id="N1_050_003", rule_name="Valor concessão positivo", rule_type="syntactic", severity="error", dimension_r18=2, dimension_name="Acurácia", status="fail", affected_records=5, total_records=5000000, affected_pct=0.0001, description="5 registros com valor de concessão negativo ou zero.", sample_ipocs=[], nivel_verificacao=1),
            # Nível 2
            ValidationResult(rule_id="N2_050_001", rule_name="Volume concessões vs mês anterior", rule_type="inter_document", severity="warning", dimension_r18=8, dimension_name="Consistência", status="warning", affected_records=2, total_records=48, affected_pct=4.17, description="2 modalidades com variação > 50% no volume de concessões em relação ao mês anterior sem justificativa sazonal.", sample_ipocs=[], nivel_verificacao=2),
            # Nível 3
            ValidationResult(rule_id="N3_050_001", rule_name="Teto de modalidade por segmento", rule_type="business", severity="warning", dimension_r18=11, dimension_name="Relevância", status="warning", affected_records=4, total_records=5000000, affected_pct=0.00008, description="4 concessões acima do teto definido pelo Curador de Dados para o segmento pessoa física.", sample_ipocs=[], nivel_verificacao=3),
        ]
        total = len(mock_results_3050)
        passed = sum(1 for r in mock_results_3050 if r.status == "pass")
        failed = sum(1 for r in mock_results_3050 if r.status == "fail")
        return ValidationResultsResponse(
            data_base=data_base, run_id="run_20260331_100000", run_status="completed",
            run_completed_at="2026-03-31T10:30:00Z",
            summary=ValidationSummary(total_rules=total, passed=passed, failed=failed, warnings=0, pass_rate_pct=round(passed / total * 100, 1)),
            results=mock_results_3050,
            pagination=Pagination(page=1, page_size=page_size, total_results=total, total_pages=1),
        )

    rows = await execute_query(
        "SELECT critica_id, critica_descricao, grupo, severidade, dimension_r18, status, "
        "registros_avaliados, registros_conformes, registros_nao_conformes, "
        "taxa_conformidade_pct, sample_falhas "
        f"FROM {CATALOG}.{SCHEMA_SILVER}.criticas_results "
        "WHERE dt_base = :data_base AND documento = '3050' "
        "ORDER BY severidade DESC LIMIT :page_size OFFSET :offset",
        {"data_base": data_base, "page_size": page_size, "offset": (page - 1) * page_size},
    )
    results = [_normalize_critica_row(r) for r in rows]
    summary_rows = await execute_query(
        "SELECT status, COUNT(*) AS n "
        f"FROM {CATALOG}.{SCHEMA_SILVER}.criticas_results "
        "WHERE dt_base = :data_base AND documento = '3050' "
        "GROUP BY status",
        {"data_base": data_base},
    )
    by_status = {s["status"]: int(s["n"] or 0) for s in summary_rows}
    total_rules = sum(by_status.values())
    passed = by_status.get("APROVADO", 0)
    failed = by_status.get("REPROVADO", 0)
    warnings = by_status.get("ALERTA", 0)
    pass_rate = round(passed / total_rules * 100, 1) if total_rules else 0.0
    return ValidationResultsResponse(
        data_base=data_base, run_id="", run_status="completed",
        summary=ValidationSummary(total_rules=total_rules, passed=passed, failed=failed, warnings=warnings, pass_rate_pct=pass_rate),
        results=results,
        pagination=Pagination(page=page, page_size=page_size, total_results=total_rules, total_pages=max(1, (total_rules + page_size - 1) // page_size)),
    )


@router.post("/trigger", response_model=TriggerValidationResponse, status_code=202)
async def trigger_validation(req: TriggerValidationRequest):
    """Trigger an on-demand validation run."""
    if req.document not in ("3040", "3050"):
        raise HTTPException(status_code=400, detail="Document must be 3040 or 3050")

    now = datetime.now(timezone.utc)
    run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"

    if USE_MOCK:
        return TriggerValidationResponse(
            run_id=run_id,
            job_run_id=12345678,
            status="pending",
            document=req.document,
            data_base=req.data_base,
            scope=req.scope,
            triggered_by="analyst@bankcorp.com",
            triggered_at=now.isoformat(),
            estimated_duration_minutes=45,
        )

    from databricks.sdk import WorkspaceClient
    import os, json
    w = WorkspaceClient()
    job_id = int(os.getenv(f"VALIDATION_JOB_{req.document}_ID", "0"))
    run = w.jobs.run_now(
        job_id=job_id,
        notebook_params={
            "document": req.document,
            "data_base": req.data_base,
            "scope": req.scope,
            "rule_ids": json.dumps(req.rule_ids) if req.rule_ids else "",
        },
    )
    return TriggerValidationResponse(
        run_id=run_id, job_run_id=run.run_id, status="pending",
        document=req.document, data_base=req.data_base, scope=req.scope,
        triggered_by="service-principal", triggered_at=now.isoformat(),
    )


@router.get("/runs/{run_id}", response_model=ValidationRunStatus)
async def get_validation_run_status(run_id: str):
    """Get status of a validation run."""
    if USE_MOCK:
        return ValidationRunStatus(
            run_id=run_id, job_run_id=12345678, status="completed",
            document="3040", data_base="2026-03",
            progress=RunProgress(
                current_step="completed", steps_completed=4, total_steps=4,
                records_processed=50000000, total_records=50000000, elapsed_seconds=2520,
            ),
            triggered_by="analyst@bankcorp.com",
            triggered_at="2026-04-02T10:00:00Z",
            started_at="2026-04-02T10:00:15Z",
            completed_at="2026-04-02T10:42:00Z",
        )
    raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs", response_model=ValidationRunsResponse)
async def list_validation_runs(
    document: str | None = Query(None),
    status: str | None = Query(None),
    data_base: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Return history of validation runs."""
    if USE_MOCK:
        runs = [
            RunSummary(
                run_id="run_20260402_100000", document="3040", data_base="2026-03",
                status="completed", scope="full",
                summary=ValidationSummary(total_rules=145, passed=140, failed=3, warnings=2, pass_rate_pct=96.5),
                triggered_by="analyst@bankcorp.com", triggered_at="2026-04-02T10:00:00Z",
                completed_at="2026-04-02T10:42:00Z", duration_seconds=2520,
            ),
            RunSummary(
                run_id="run_20260331_100000", document="3050", data_base="2026-03-28",
                status="completed", scope="full",
                summary=ValidationSummary(total_rules=85, passed=83, failed=1, warnings=1, pass_rate_pct=97.6),
                triggered_by="analyst@bankcorp.com", triggered_at="2026-03-31T10:00:00Z",
                completed_at="2026-03-31T10:25:00Z", duration_seconds=1500,
            ),
        ]
        if document:
            runs = [r for r in runs if r.document == document]
        return ValidationRunsResponse(runs=runs[:limit])
    return ValidationRunsResponse(runs=[])
