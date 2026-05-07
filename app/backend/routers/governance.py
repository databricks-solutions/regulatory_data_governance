"""Governance endpoints: irregularity log, incident lifecycle, action plans, and semi-annual reports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, SCHEMA_GOLD, SCHEMA_REFERENCE, USE_MOCK
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when gold/reference tables haven't been populated yet.
from db import execute_query_or_empty as execute_query

# Roman → int mapping for the R.18 dimension key stored in
# `gold.violacoes_log.dimension_r18` (matches `reference.dimensoes_r18.dimensao_id`).
_DIM_ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}

# `gold.violacoes_log.severidade` ∈ {BLOQUEANTE, ALERTA}
# `gold.violacoes_log.status_resolucao` ∈ {ABERTA, EM_ANDAMENTO, RESOLVIDA, ESCALADA}
_SEVERITY_MAP = {"BLOQUEANTE": "high", "ALERTA": "medium", "INFO": "low"}
_STATUS_MAP = {
    "ABERTA": "open",
    "EM_ANDAMENTO": "in_progress",
    "RESOLVIDA": "resolved",
    "ESCALADA": "escalated",
    "VALIDADA": "validated",
}

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
        dimension_r18=8, dimension_name="Consistência", severity="high", status="resolved",  # Consistência (VIII) per spec §1.2
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
        id="IRR-2026-0051", detected_at="2026-04-01T09:00:00Z", data_base="2026-03", document="3050",
        dimension_r18=9, dimension_name="Integridade", severity="low", status="open",
        description="Permissões de escrita encontradas em perfil 'consulta' no schema gold — viola segregação gerar/aprovar exigida pelo Art. 2, §2, IX",
        owner="seguranca.dados@bankcorp.com",
        detected_by="auditoria.interna@bankcorp.com",
        timeline=[
            IncidentEvent(timestamp="2026-04-01T09:00:00Z", event_type="detected", actor="auditoria.interna@bankcorp.com",
                          description="Auditoria interna identificou perfil 'consulta' com permissão de modificação no Unity Catalog (gold.qualidade_dimensoes_mensal)"),
        ],
    ),
]

_MOCK_ACTION_PLANS = [
    ActionPlan(
        id="AP-2026-001", irregularity_id="IRR-2026-0042",
        title="Atualizar tabela de equivalência V11",
        description="Incluir regras de cessão imobiliária no mapeamento 3040→3050 (mod_3050_equiv) usado pelo silver",
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
        id="AP-2026-004", irregularity_id="IRR-2026-0051",
        title="Aplicar segregação de funções no schema gold (Integridade)",
        description="Revogar privilégios de modificação do perfil 'consulta' em gold.qualidade_dimensoes_mensal e demais tabelas gold; manter apenas acesso de leitura conforme matriz de SoD do Art. 2, §2, IX (R.18)",
        owner="seguranca.dados@bankcorp.com", created_at="2026-04-01T10:00:00Z",
        deadline="2026-05-15", status="pending", progress_pct=0.0,
        dimension_r18=9, dimension_name="Integridade",
        auditor_caveat="R8 - Completar matriz de segregação para relatório semestral conforme ressalva",
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
                    IrregularityDimensionSummary(dimension_id=9, name="Integridade", count=1),
                ],
            ),
            pagination=Pagination(page=page, page_size=page_size, total_results=total, total_pages=max(1, (total + page_size - 1) // page_size)),
        )

    # Map UI-facing filter values back to the storage vocabulary used by the pipeline.
    status_filter = next((k for k, v in _STATUS_MAP.items() if v == status), None) if status else None
    severity_filter = next((k for k, v in _SEVERITY_MAP.items() if v == severity), None) if severity else None
    dim_roman_filter = next((k for k, v in _DIM_ROMAN_TO_INT.items() if v == dimension_r18), None) if dimension_r18 else None

    where_parts = [
        "(:status_resolucao IS NULL OR v.status_resolucao = :status_resolucao)",
        "(:severidade IS NULL OR v.severidade = :severidade)",
        "(:dim_roman IS NULL OR v.dimension_r18 = :dim_roman)",
        "v.dt_base >= :data_base_from AND v.dt_base <= :data_base_to",
    ]
    where_sql = " AND ".join(where_parts)

    rows = await execute_query(
        "SELECT v.dt_base, v.documento, v.expectation_name, v.critica_id, "
        "v.dimension_r18, v.severidade, v.registros_afetados, v.total_registros, "
        "v.taxa_violacao_pct, v.acao_tomada, v.status_resolucao, "
        "v.responsavel_resolucao, v.dt_resolucao, v.log_timestamp, "
        "d.nome AS dimensao_nome "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.violacoes_log v "
        f"LEFT JOIN {CATALOG}.{SCHEMA_REFERENCE}.dimensoes_r18 d ON d.dimensao_id = v.dimension_r18 "
        f"WHERE {where_sql} "
        "ORDER BY v.log_timestamp DESC LIMIT :page_size OFFSET :offset",
        {
            "status_resolucao": status_filter, "severidade": severity_filter, "dim_roman": dim_roman_filter,
            "data_base_from": data_base_from, "data_base_to": data_base_to,
            "page_size": page_size, "offset": (page - 1) * page_size,
        },
    )

    items: list[Irregularity] = []
    for r in rows:
        dim_int = _DIM_ROMAN_TO_INT.get(r["dimension_r18"], 0)
        detected_at = r["log_timestamp"]
        resolved_at = r["dt_resolucao"]
        resolution_days = None
        if detected_at and resolved_at:
            resolution_days = max(0, int((resolved_at - detected_at).days)) if hasattr(resolved_at, "days") or hasattr((resolved_at - detected_at), "days") else None
        items.append(Irregularity(
            id=f"IRR-{r['critica_id']}-{r['dt_base']}",
            detected_at=str(detected_at),
            data_base=r["dt_base"],
            document=r["documento"],
            dimension_r18=dim_int,
            dimension_name=r.get("dimensao_nome") or "",
            severity=_SEVERITY_MAP.get(r["severidade"], "medium"),
            status=_STATUS_MAP.get(r["status_resolucao"], "open"),
            description=f"{r['expectation_name']} — {r['registros_afetados']} registros afetados ({r['taxa_violacao_pct']:.2f}%)",
            owner=r.get("responsavel_resolucao"),
            resolved_at=str(resolved_at) if resolved_at else None,
            resolution_days=resolution_days,
            detected_by="dlt-pipeline",
            timeline=[IncidentEvent(
                timestamp=str(detected_at), event_type="detected", actor="dlt-pipeline",
                description=f"Violação detectada automaticamente pelo pipeline DLT (crítica {r['critica_id']})",
            )],
        ))

    # Aggregations across the full filtered result set (not just the current page).
    summary_rows = await execute_query(
        "SELECT v.status_resolucao, v.dimension_r18, v.dt_resolucao, v.log_timestamp, d.nome "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.violacoes_log v "
        f"LEFT JOIN {CATALOG}.{SCHEMA_REFERENCE}.dimensoes_r18 d ON d.dimensao_id = v.dimension_r18 "
        f"WHERE {where_sql}",
        {
            "status_resolucao": status_filter, "severidade": severity_filter, "dim_roman": dim_roman_filter,
            "data_base_from": data_base_from, "data_base_to": data_base_to,
        },
    )
    total = len(summary_rows)
    counts = {"open": 0, "in_progress": 0, "resolved": 0}
    resolution_days_sum = 0
    resolution_days_count = 0
    by_dim: dict[int, dict] = {}
    for s in summary_rows:
        st = _STATUS_MAP.get(s["status_resolucao"], "open")
        if st in counts:
            counts[st] += 1
        if s["dt_resolucao"] and s["log_timestamp"]:
            delta = s["dt_resolucao"] - s["log_timestamp"]
            resolution_days_sum += delta.days
            resolution_days_count += 1
        d_int = _DIM_ROMAN_TO_INT.get(s["dimension_r18"], 0)
        if d_int:
            entry = by_dim.setdefault(d_int, {"name": s["nome"] or "", "count": 0})
            entry["count"] += 1

    summary = IrregularitySummary(
        total_open=counts["open"],
        total_in_progress=counts["in_progress"],
        total_resolved=counts["resolved"],
        avg_resolution_days=round(resolution_days_sum / resolution_days_count, 2) if resolution_days_count else 0.0,
        by_dimension=[IrregularityDimensionSummary(dimension_id=k, name=v["name"], count=v["count"]) for k, v in sorted(by_dim.items())],
    )

    return IrregularitiesResponse(
        total=total,
        irregularities=items,
        summary=summary,
        pagination=Pagination(
            page=page, page_size=page_size, total_results=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
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

    # Real DB: ID format is "IRR-<critica_id>-<dt_base>" where dt_base is "YYYY-MM"
    # (see get_irregularities). Since both critica_id and dt_base may contain '-', we
    # peel the trailing 7-char "YYYY-MM" off the end.
    if not irregularity_id.startswith("IRR-") or len(irregularity_id) < 12:
        raise HTTPException(status_code=404, detail="Irregularity not found")
    body = irregularity_id.removeprefix("IRR-")
    if len(body) < 8 or body[-8] != "-":
        raise HTTPException(status_code=404, detail="Irregularity not found")
    critica_id, dt_base = body[:-8], body[-7:]

    rows = await execute_query(
        "SELECT v.dt_base, v.documento, v.expectation_name, v.critica_id, "
        "v.dimension_r18, v.severidade, v.registros_afetados, v.total_registros, "
        "v.taxa_violacao_pct, v.status_resolucao, v.responsavel_resolucao, "
        "v.dt_resolucao, v.log_timestamp, d.nome AS dimensao_nome "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.violacoes_log v "
        f"LEFT JOIN {CATALOG}.{SCHEMA_REFERENCE}.dimensoes_r18 d ON d.dimensao_id = v.dimension_r18 "
        "WHERE v.critica_id = :critica_id AND v.dt_base = :dt_base LIMIT 1",
        {"critica_id": critica_id, "dt_base": dt_base},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Irregularity not found")
    r = rows[0]
    detected_at = r["log_timestamp"]
    resolved_at = r["dt_resolucao"]
    resolution_days = (resolved_at - detected_at).days if (detected_at and resolved_at) else None
    timeline = [IncidentEvent(
        timestamp=str(detected_at), event_type="detected", actor="dlt-pipeline",
        description=f"Violação detectada automaticamente pelo pipeline DLT (crítica {r['critica_id']})",
    )]
    if resolved_at:
        timeline.append(IncidentEvent(
            timestamp=str(resolved_at), event_type="resolved",
            actor=r.get("responsavel_resolucao") or "system",
            description="Violação marcada como resolvida no log de governança.",
        ))
    item = Irregularity(
        id=irregularity_id,
        detected_at=str(detected_at),
        data_base=r["dt_base"],
        document=r["documento"],
        dimension_r18=_DIM_ROMAN_TO_INT.get(r["dimension_r18"], 0),
        dimension_name=r.get("dimensao_nome") or "",
        severity=_SEVERITY_MAP.get(r["severidade"], "medium"),
        status=_STATUS_MAP.get(r["status_resolucao"], "open"),
        description=f"{r['expectation_name']} — {r['registros_afetados']} registros afetados ({r['taxa_violacao_pct']:.2f}%)",
        owner=r.get("responsavel_resolucao"),
        resolved_at=str(resolved_at) if resolved_at else None,
        resolution_days=resolution_days,
        detected_by="dlt-pipeline",
        timeline=timeline,
    )
    return IrregularityDetailResponse(irregularity=item, action_plans=[])


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
