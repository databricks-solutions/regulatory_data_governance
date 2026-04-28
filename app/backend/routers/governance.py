"""Governance endpoints: irregularity log, incident lifecycle, action plans, and semi-annual reports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, USE_MOCK as _DB_USE_MOCK, execute_query

# governance tables are not yet provisioned; always serve mock data
USE_MOCK = True
from models import (
    ActionPlan,
    ActionPlansResponse,
    ActionPlanUpdate,
    GovernanceReport,
    GovernanceReportsResponse,
    IncidentEvent,
    Irregularity,
    IrregularitiesResponse,
    IrregularityDetailResponse,
    IrregularityDimensionSummary,
    IrregularitySummary,
    Pagination,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_IRREGULARITIES = [
    Irregularity(
        id="IRR-2026-0042", detected_at="2026-03-15T14:00:00Z", data_base="2026-02", document="3040",
        dimension_r18=8, dimension_name="Consistência", severity="high", status="resolved",
        description="Divergência 3040 vs 3050 acima da tolerância para modalidade crédito imobiliário (0.7% > 0.5%)",
        root_cause="Operações de cessão imobiliária não mapeadas na tabela de equivalência V11",
        impact="Bloqueio de envio do 3040 e 3050 por 2 dias úteis",
        remedial_action="Atualizada tabela de equivalência com novas regras de cessão imobiliária",
        owner="eng.dados@bankcorp.com", resolved_at="2026-03-17T10:00:00Z", resolution_days=2,
        included_in_report="2026-S1",
        detected_by="monitor.dq@bankcorp.com",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-15T16:00:00Z",
        validated_by="gestor.info@bankcorp.com",
        validated_at="2026-03-17T14:00:00Z",
        timeline=[
            IncidentEvent(timestamp="2026-03-15T14:00:00Z", event_type="detected", actor="monitor.dq@bankcorp.com",
                          description="Divergência detectada automaticamente pelo monitor de consistência 3040/3050"),
            IncidentEvent(timestamp="2026-03-15T14:30:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com para análise de causa raiz"),
            IncidentEvent(timestamp="2026-03-15T16:00:00Z", event_type="responded", actor="eng.dados@bankcorp.com",
                          description="Causa raiz identificada: cessões imobiliárias não mapeadas na equivalência V11"),
            IncidentEvent(timestamp="2026-03-17T10:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Tabela de equivalência atualizada e reprocessamento concluído com sucesso"),
            IncidentEvent(timestamp="2026-03-17T14:00:00Z", event_type="validated", actor="gestor.info@bankcorp.com",
                          description="Resolução validada. Divergência eliminada nos dados reprocessados."),
        ],
    ),
    Irregularity(
        id="IRR-2026-0041", detected_at="2026-03-10T08:00:00Z", data_base="2026-02", document="3040",
        dimension_r18=2, dimension_name="Acurácia", severity="high", status="resolved",
        description="250 operações com IPOC divergente dos campos (SEM_014)",
        root_cause="Bug na transformação silver: cnpj_if truncado para 7 dígitos",
        impact="Rejeição da remessa 1 do 3040 fev/2026",
        remedial_action="Corrigido pipeline silver, reprocessados dados e reenviada remessa 2",
        owner="eng.dados@bankcorp.com", resolved_at="2026-03-12T16:00:00Z", resolution_days=2,
        included_in_report="2026-S1",
        detected_by="criticas.scr@bankcorp.com",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-10T10:30:00Z",
        validated_by="coord.dados@bankcorp.com",
        validated_at="2026-03-12T17:00:00Z",
        timeline=[
            IncidentEvent(timestamp="2026-03-10T08:00:00Z", event_type="detected", actor="criticas.scr@bankcorp.com",
                          description="Crítica SEM_014 rejeitou 250 operações na validação pré-envio do 3040"),
            IncidentEvent(timestamp="2026-03-10T08:15:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com - prioridade alta por bloqueio de remessa"),
            IncidentEvent(timestamp="2026-03-10T10:30:00Z", event_type="responded", actor="eng.dados@bankcorp.com",
                          description="Bug identificado: cnpj_if truncado para 7 dígitos no notebook silver_3040"),
            IncidentEvent(timestamp="2026-03-12T16:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Pipeline corrigido, dados reprocessados, remessa 2 enviada com sucesso"),
            IncidentEvent(timestamp="2026-03-12T17:00:00Z", event_type="validated", actor="coord.dados@bankcorp.com",
                          description="Validação confirmada: todas as 250 operações com IPOC correto"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0050", detected_at="2026-03-29T10:00:00Z", data_base="2026-03", document="3040",
        dimension_r18=8, dimension_name="Consistência", severity="medium", status="in_progress",
        description="Reconciliação COSIF regra M01: divergência 0.08% em empréstimos capital de giro",
        owner="eng.dados@bankcorp.com",
        detected_by="monitor.dq@bankcorp.com",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-29T14:00:00Z",
        timeline=[
            IncidentEvent(timestamp="2026-03-29T10:00:00Z", event_type="detected", actor="monitor.dq@bankcorp.com",
                          description="Monitor de reconciliação detectou divergência 0.08% na regra M01 (COSIF vs 3040)"),
            IncidentEvent(timestamp="2026-03-29T10:30:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com para investigação"),
            IncidentEvent(timestamp="2026-03-29T14:00:00Z", event_type="responded", actor="eng.dados@bankcorp.com",
                          description="Investigação iniciada. Suspeita de diferença temporal entre fontes Oracle e DB2"),
            IncidentEvent(timestamp="2026-04-02T09:00:00Z", event_type="comment", actor="eng.dados@bankcorp.com",
                          description="Confirmado: janela de extração DB2 difere em 2h da Oracle. Ajuste em andamento."),
        ],
    ),
    Irregularity(
        id="IRR-2026-0051", detected_at="2026-04-01T09:00:00Z", data_base="2026-03", document="3050",
        dimension_r18=9, dimension_name="Efetividade", severity="low", status="open",
        description="Dashboard de efetividade sem dados para dimensão 9 (métrica de utilização pendente)",
        owner="bi.team@bankcorp.com",
        detected_by="auditoria.interna@bankcorp.com",
        timeline=[
            IncidentEvent(timestamp="2026-04-01T09:00:00Z", event_type="detected", actor="auditoria.interna@bankcorp.com",
                          description="Auditoria interna identificou ausência de métricas de efetividade no dashboard R.18"),
        ],
    ),
]

_MOCK_ACTION_PLANS = [
    ActionPlan(
        id="AP-2026-001", irregularity_id="IRR-2026-0042",
        title="Atualizar tabela de equivalência V11",
        description="Incluir regras de cessão imobiliária no mapeamento 3040/3050 para eliminar divergências de reconciliação",
        owner="eng.dados@bankcorp.com", created_at="2026-03-15T17:00:00Z",
        deadline="2026-04-15", status="completed", progress_pct=100.0,
        dimension_r18=8, dimension_name="Consistência",
        updates=[
            ActionPlanUpdate(date="2026-03-16", author="eng.dados@bankcorp.com", note="Mapeamento de novas regras de cessão iniciado"),
            ActionPlanUpdate(date="2026-03-17", author="eng.dados@bankcorp.com", note="Tabela atualizada, reprocessamento concluído e validado"),
        ],
    ),
    ActionPlan(
        id="AP-2026-002", irregularity_id="IRR-2026-0041",
        title="Corrigir truncamento CNPJ no pipeline silver",
        description="Fix na transformação silver para preservar 14 dígitos do CNPJ_IF conforme layout SCR",
        owner="eng.dados@bankcorp.com", created_at="2026-03-10T11:00:00Z",
        deadline="2026-03-25", status="completed", progress_pct=100.0,
        dimension_r18=2, dimension_name="Acurácia",
        updates=[
            ActionPlanUpdate(date="2026-03-11", author="eng.dados@bankcorp.com", note="Bug identificado no notebook silver_3040 linha 142"),
            ActionPlanUpdate(date="2026-03-12", author="eng.dados@bankcorp.com", note="Fix aplicado, reprocessamento concluído, remessa 2 aceita"),
        ],
    ),
    ActionPlan(
        id="AP-2026-003", irregularity_id="IRR-2026-0050",
        title="Investigar divergência reconciliação COSIF M01",
        description="Análise da divergência 0.08% em empréstimos capital de giro entre COSIF e 3040",
        owner="eng.dados@bankcorp.com", created_at="2026-03-30T10:00:00Z",
        deadline="2026-04-30", status="in_progress", progress_pct=40.0,
        dimension_r18=8, dimension_name="Consistência",
        auditor_caveat="R2 - Monitorar evolução mensal conforme ressalva de auditoria",
        updates=[
            ActionPlanUpdate(date="2026-03-30", author="eng.dados@bankcorp.com", note="Investigação iniciada - comparando janelas de extração"),
            ActionPlanUpdate(date="2026-04-02", author="eng.dados@bankcorp.com", note="Confirmada diferença de 2h na janela de extração DB2 vs Oracle"),
        ],
    ),
    ActionPlan(
        id="AP-2026-004", irregularity_id="IRR-2026-0051",
        title="Implementar métrica de efetividade dimensão 9",
        description="Desenvolver e integrar métricas de utilização dos dados reportados para dashboard de efetividade R.18",
        owner="bi.team@bankcorp.com", created_at="2026-04-01T10:00:00Z",
        deadline="2026-05-15", status="pending", progress_pct=0.0,
        dimension_r18=9, dimension_name="Efetividade",
        auditor_caveat="R8 - Completar métricas para relatório semestral conforme ressalva",
        updates=[],
    ),
]

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/irregularities", response_model=IrregularitiesResponse)
async def get_irregularities(
    status: str | None = Query(None),
    severity: str | None = Query(None),
    dimension_r18: int | None = Query(None),
    data_base_from: str = Query("2025-10"),
    data_base_to: str = Query("2026-12"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return log of quality irregularities with resolution status."""
    if USE_MOCK:
        items = _MOCK_IRREGULARITIES
        if status:
            items = [i for i in items if i.status == status]
        if severity:
            items = [i for i in items if i.severity == severity]
        if dimension_r18:
            items = [i for i in items if i.dimension_r18 == dimension_r18]
        total = len(items)
        paged = items[(page - 1) * page_size : page * page_size]
        return IrregularitiesResponse(
            total=total,
            irregularities=paged,
            summary=IrregularitySummary(
                total_open=1, total_in_progress=1, total_resolved=2, avg_resolution_days=2.0,
                by_dimension=[
                    IrregularityDimensionSummary(dimension_id=2, name="Acurácia", count=1),
                    IrregularityDimensionSummary(dimension_id=8, name="Consistência", count=2),
                    IrregularityDimensionSummary(dimension_id=9, name="Efetividade", count=1),
                ],
            ),
            pagination=Pagination(page=page, page_size=page_size, total_results=total, total_pages=max(1, (total + page_size - 1) // page_size)),
        )

    rows = await execute_query(
        "SELECT violacao_sk, dt_base, documento, expectation_name, critica_id, "
        "dimension_r18, severidade, registros_afetados, total_registros, taxa_violacao_pct, "
        "acao_tomada, status_resolucao, responsavel_resolucao, dt_resolucao, log_timestamp "
        f"FROM {CATALOG}.gold.violacoes_log "
        "WHERE (:status_resolucao IS NULL OR status_resolucao = :status_resolucao) "
        "AND log_timestamp >= :data_base_from AND log_timestamp <= :data_base_to "
        "ORDER BY log_timestamp DESC LIMIT :page_size OFFSET :offset",
        {"status_resolucao": status, "data_base_from": data_base_from, "data_base_to": data_base_to, "page_size": page_size, "offset": (page - 1) * page_size},
    )
    items = [
        Irregularity(
            id=str(r["violacao_sk"]), detected_at=str(r["log_timestamp"]),
            data_base=r["dt_base"], document=r["documento"],
            dimension_r18=r["dimension_r18"], dimension_name="", severity=r["severidade"],
            status=r.get("status_resolucao", "open"), description=r.get("expectation_name", ""),
        )
        for r in rows
    ]
    return IrregularitiesResponse(
        total=len(items), irregularities=items,
        summary=IrregularitySummary(total_open=0, total_in_progress=0, total_resolved=0, avg_resolution_days=0, by_dimension=[]),
        pagination=Pagination(page=page, page_size=page_size),
    )


@router.get("/irregularities/{irregularity_id}", response_model=IrregularityDetailResponse)
async def get_irregularity_detail(irregularity_id: str):
    """Return single irregularity with full lifecycle timeline and linked action plans."""
    if USE_MOCK:
        item = next((i for i in _MOCK_IRREGULARITIES if i.id == irregularity_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Irregularity not found")
        plans = [p for p in _MOCK_ACTION_PLANS if p.irregularity_id == irregularity_id]
        return IrregularityDetailResponse(irregularity=item, action_plans=plans)
    raise HTTPException(status_code=404, detail="Not implemented for real DB yet")


@router.get("/action-plans", response_model=ActionPlansResponse)
async def get_action_plans(
    status: str | None = Query(None),
    owner: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return action plans with filtering and pagination."""
    if USE_MOCK:
        items = list(_MOCK_ACTION_PLANS)
        if status:
            items = [p for p in items if p.status == status]
        if owner:
            items = [p for p in items if p.owner == owner]
        total = len(items)
        paged = items[(page - 1) * page_size : page * page_size]
        return ActionPlansResponse(
            total=total,
            action_plans=paged,
            pagination=Pagination(page=page, page_size=page_size, total_results=total, total_pages=max(1, (total + page_size - 1) // page_size)),
        )
    return ActionPlansResponse(total=0, action_plans=[], pagination=Pagination())


@router.get("/reports", response_model=GovernanceReportsResponse)
async def get_governance_reports():
    """Return list of semi-annual reports with generation and approval status."""
    if USE_MOCK:
        return GovernanceReportsResponse(
            reports=[
                GovernanceReport(
                    id="RPT-2026-S1", period="2026-S1", period_start="2026-01-01", period_end="2026-06-30",
                    status="in_progress", irregularities_count=12, resolved_count=9, pending_count=3,
                    dimensions_covered=12,
                ),
                GovernanceReport(
                    id="RPT-2026-S2", period="2026-S2", period_start="2026-07-01", period_end="2026-12-31",
                    status="draft", irregularities_count=0, resolved_count=0, pending_count=0,
                    dimensions_covered=12,
                ),
            ]
        )
    return GovernanceReportsResponse(reports=[])
