"""Governance endpoints: incident log, lifecycle, action plans, and semi-annual reports.

Post Phase-7 / DQX migration this router reads/writes ``governance.incidents``
(see docs/spec/08_dqx_app_integration.md §1.6) — replacing the legacy
``gold.violacoes_log`` source. Incidents are either:

- **Auto-emitted** by a post-silver job (``detected_by='dqx:auto-emit'``) — see
  spec §4.1. This router does not run that job; it only surfaces the resulting
  rows and applies the same dedup semantics on manual creation.
- **Manually created** from the Críticas SCR drilldown via
  ``POST /api/v1/governance/incidents`` (``detected_by='manual:<email>'``).

The legacy GET URLs (``/irregularities`` and ``/irregularities/{id}``) are
preserved so the frontend keeps working through the migration.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db import CATALOG, USE_MOCK
from i18n import get_locale
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when governance tables haven't been populated yet.
from db import execute_query_or_empty as execute_query

# Roman → int mapping for the R.18 dimension key stored in
# `governance.incidents.dimensao_r18` (matches `reference.dimensoes_r18.dimensao_id`).
_DIM_ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
_DIM_INT_TO_ROMAN = {v: k for k, v in _DIM_ROMAN_TO_INT.items()}

# `governance.incidents.severidade` ∈ {BLOQUEANTE, ALERTA, INFO}
# `governance.incidents.status` ∈ {detected, assigned, in_progress, escalated, resolved, validated, reopened}
_SEVERITY_MAP = {"BLOQUEANTE": "high", "ALERTA": "medium", "INFO": "low"}
_SEVERITY_REVERSE_MAP = {
    "high": "BLOQUEANTE", "medium": "ALERTA", "low": "INFO",
    # Críticas SCR severity vocabulary → storage
    "error": "BLOQUEANTE", "warning": "ALERTA", "info": "INFO",
}
# Incident lifecycle storage → UI. The UI vocabulary keeps backward-compat with
# the legacy ``open`` shorthand for ``detected`` (the original ``Aberto`` label).
_STATUS_MAP = {
    "detected":    "open",
    "in_progress": "in_progress",
    "resolved":    "resolved",
    "reopened":    "reopened",
    # Legacy mappings — back-compat com linhas antigas em `governance.incidents`
    # gravadas pela FSM anterior de 7 estados. Render-only: surface como o
    # estado ativo mais próximo. NÃO entram no reverse map (ninguém ESCREVE
    # esses valores hoje).
    "assigned":  "in_progress",
    "escalated": "in_progress",
    "validated": "resolved",
}
# Reverse map: UI → storage. Construído explicitamente porque _STATUS_MAP tem
# duplicatas de VALOR (legacy → in_progress/resolved); um dict comp simples
# perderia entradas ativas.
_STATUS_REVERSE_MAP = {
    "open":        "detected",
    "in_progress": "in_progress",
    "resolved":    "resolved",
    "reopened":    "reopened",
}

# Finite-state machine simplificada — 4 estados, ciclo claro:
#   detected (UI: Aberto) → in_progress → resolved → (reopened) → in_progress
# Estados removidos vs spec original (07 §12.4): assigned, escalated, validated.
# Razão: o fluxo com 7 estados ficou confuso pra usuários ("Assumir" de
# in_progress voltava pra assigned, etc.). Versão atual cobre 95% dos casos
# reais (incidente é aberto, alguém pega, resolve; eventualmente reabre).
_FSM_TRANSITIONS: dict[str, set[str]] = {
    "detected":    {"in_progress", "resolved"},
    "in_progress": {"resolved"},
    "resolved":    {"reopened"},
    "reopened":    {"in_progress", "resolved"},
}

from models import (
    ActionPlan,
    ActionPlansResponse,
    ActionPlanUpdate,
    GovernanceReport,
    GovernanceReportsResponse,
    IncidentCreateRequest,
    IncidentEvent,
    IncidentStatusUpdateRequest,
    Irregularity,
    IrregularitiesResponse,
    IrregularityDetailResponse,
    IrregularityDimensionSummary,
    IrregularitySummary,
    Pagination,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dqx_studio_url(_run_config_name: str | None, check_name: str | None) -> str | None:
    """Linkback URL para DQX Studio (lista de regras ativas).

    Studio não tem deep-link por (run_config_name, check_name) — apontamos pra
    `/rules/active` e o usuário localiza a regra na lista. Retorna ``None``
    quando ``DQX_STUDIO_URL`` está como `about:blank`, OU
    quando ``check_name`` é nulo. `_run_config_name` mantido na assinatura
    apenas pra compatibilidade com call sites antigos; não é consumido."""
    base = (os.getenv("DQX_STUDIO_URL") or "").rstrip("/")
    if not base or base in ("about:blank",) or not check_name:
        return None
    return f"{base}/rules/active"


def _caller_email(request: Request) -> str:
    """Best-effort caller identity for the audit trail. Falls back to
    ``unknown@bankcorp.com`` when running outside the Databricks Apps OAuth
    envelope (e.g. local devloop)."""
    return request.headers.get("X-Forwarded-Email") or "unknown@bankcorp.com"


def _document_from_run_config(run_config_name: str | None) -> str:
    if not run_config_name:
        return ""
    return "3040" if run_config_name.startswith("silver_3040_") else "3050" if run_config_name.startswith("silver_3050") else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Mock data — covers both provenance flavors:
#   - ``dqx:auto-emit`` rows simulate the post-silver job output (§4.1)
#   - ``manual:<email>`` rows simulate Críticas SCR drilldown creations (§4.2)
# ---------------------------------------------------------------------------

_MOCK_IRREGULARITIES: list[Irregularity] = [
    # ---- AUTO-EMITTED (DQX) ----
    Irregularity(
        id="IRR-2026-0042",
        detected_at="2026-03-15T14:00:00Z",
        data_base="2026-02",
        document="3040",
        dimension_r18=8,
        dimension_name="Consistência",
        severity="high",
        status="resolved",
        description="Divergência 3040 vs 3050 acima da tolerância para modalidade crédito imobiliário (0.7% > 0.5%)",
        root_cause="Operações de cessão imobiliária não mapeadas na tabela de equivalência V11",
        impact="Bloqueio de envio do 3040 e 3050 por 2 dias úteis",
        remedial_action="Atualizada tabela de equivalência com novas regras de cessão imobiliária",
        owner="eng.dados@bankcorp.com",
        resolved_at="2026-03-17T10:00:00Z",
        resolution_days=2,
        included_in_report="2026-S1",
        detected_by="dqx:auto-emit",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-15T16:00:00Z",
        validated_by="gestor.info@bankcorp.com",
        validated_at="2026-03-17T14:00:00Z",
        critica_id="CR2_018",
        run_config_name="silver_3050",
        dqx_check_name="saldo_3040_vs_3050_consistente",
        dqx_check_function="sql_expression",
        affected_records=412,
        last_seen_run_id="run_2026_03_15_silver_3050_b421",
        studio_url=_dqx_studio_url("silver_3050", "saldo_3040_vs_3050_consistente"),
        timeline=[
            IncidentEvent(timestamp="2026-03-15T14:00:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detectado pela execução DQX silver_3050 — 412 registros divergentes acima da tolerância de 0,5%."),
            IncidentEvent(timestamp="2026-03-15T14:30:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com para análise de causa raiz"),
            IncidentEvent(timestamp="2026-03-15T16:00:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Causa raiz identificada: cessões imobiliárias não mapeadas na equivalência V11"),
            IncidentEvent(timestamp="2026-03-17T10:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Tabela de equivalência atualizada e reprocessamento concluído com sucesso"),
            IncidentEvent(timestamp="2026-03-17T14:00:00Z", event_type="validated", actor="gestor.info@bankcorp.com",
                          description="Resolução validada. Divergência eliminada nos dados reprocessados."),
        ],
    ),
    Irregularity(
        id="IRR-2026-0041",
        detected_at="2026-03-10T08:00:00Z",
        data_base="2026-02",
        document="3040",
        dimension_r18=6,
        dimension_name="Completude / Adaptabilidade",
        severity="high",
        status="resolved",
        description="250 operações com CNPJ_IF fora do formato (8 dígitos numéricos exigidos pelo leiaute)",
        root_cause="Bug na transformação silver: cnpj_if truncado para 7 dígitos",
        impact="Rejeição da remessa 1 do 3040 fev/2026",
        remedial_action="Corrigido pipeline silver, reprocessados dados e reenviada remessa 2",
        owner="eng.dados@bankcorp.com",
        resolved_at="2026-03-12T16:00:00Z",
        resolution_days=2,
        included_in_report="2026-S1",
        detected_by="dqx:auto-emit",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-10T10:30:00Z",
        validated_by="coord.dados@bankcorp.com",
        validated_at="2026-03-12T17:00:00Z",
        critica_id="S10_002",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="cnpj_if_format_valid",
        dqx_check_function="regex_match",
        affected_records=250,
        last_seen_run_id="run_2026_03_10_silver_3040_a812",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "cnpj_if_format_valid"),
        timeline=[
            IncidentEvent(timestamp="2026-03-10T08:00:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detectado pela execução DQX silver_3040_operacoes — 250 operações com CNPJ_IF inválido."),
            IncidentEvent(timestamp="2026-03-10T08:15:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com - prioridade alta por bloqueio de remessa"),
            IncidentEvent(timestamp="2026-03-10T10:30:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Bug identificado: cnpj_if truncado para 7 dígitos no notebook silver_3040"),
            IncidentEvent(timestamp="2026-03-12T16:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Pipeline corrigido, dados reprocessados, remessa 2 enviada com sucesso"),
            IncidentEvent(timestamp="2026-03-12T17:00:00Z", event_type="validated", actor="coord.dados@bankcorp.com",
                          description="Validação confirmada: todas as 250 operações com CNPJ_IF correto"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0048",
        detected_at="2026-04-02T03:12:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=3,
        dimension_name="Adaptabilidade",
        severity="high",
        status="in_progress",
        description="38 clientes com PorteCli fora do domínio vigente do leiaute SCR 3040",
        owner="eng.dados@bankcorp.com",
        detected_by="dqx:auto-emit",
        critica_id="S20_005",
        run_config_name="silver_3040_clientes",
        dqx_check_name="porte_cli_in_dominio",
        dqx_check_function="foreign_key",
        affected_records=38,
        last_seen_run_id="run_2026_04_02_silver_3040_clientes_c014",
        studio_url=_dqx_studio_url("silver_3040_clientes", "porte_cli_in_dominio"),
        timeline=[
            IncidentEvent(timestamp="2026-04-02T03:12:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detectado pela execução DQX silver_3040_clientes — 38 clientes com PorteCli inválido."),
            IncidentEvent(timestamp="2026-04-02T09:40:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a eng.dados@bankcorp.com para investigação"),
            IncidentEvent(timestamp="2026-04-02T11:05:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Iniciada investigação — suspeita de domínio desatualizado no reference.dominios"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0049",
        detected_at="2026-04-08T03:10:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=11,
        dimension_name="Relevância",
        severity="medium",
        status="open",
        description="14 operações da modalidade 0102 acima do teto interno definido pelo Curador de Dados",
        detected_by="dqx:auto-emit",
        critica_id="N3_001",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="limite_credito_por_modalidade",
        dqx_check_function="sql_expression",
        affected_records=14,
        last_seen_run_id="run_2026_04_08_silver_3040_d901",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "limite_credito_por_modalidade"),
        timeline=[
            IncidentEvent(timestamp="2026-04-08T03:10:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detectado pela execução DQX silver_3040_operacoes — 14 operações acima do teto da modalidade 0102."),
        ],
    ),
    # ---- MANUAL (Críticas SCR drilldown) ----
    Irregularity(
        id="IRR-2026-0050",
        detected_at="2026-04-10T11:20:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=8,
        dimension_name="Consistência",
        severity="medium",
        status="in_progress",
        description="Modalidades sem mapeamento na tabela de equivalência 3040↔3050 — operações não consolidarão no 3050",
        owner="analyst@bankcorp.com",
        detected_by="manual:analyst@bankcorp.com",
        critica_id="CR2_018",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="modalidade_equivalencia_3040_3050",
        dqx_check_function="foreign_key",
        affected_records=89,
        last_seen_run_id="run_2026_04_10_silver_3040_e502",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "modalidade_equivalencia_3040_3050"),
        timeline=[
            IncidentEvent(timestamp="2026-04-10T11:20:00Z", event_type="detected", actor="manual:analyst@bankcorp.com",
                          description="Criado manualmente a partir da Críticas SCR — 89 registros sem equivalência 3040↔3050."),
            IncidentEvent(timestamp="2026-04-10T13:00:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Atribuído a analyst@bankcorp.com para abertura do plano de ação"),
            IncidentEvent(timestamp="2026-04-10T14:30:00Z", event_type="in_progress", actor="analyst@bankcorp.com",
                          description="Iniciada análise das modalidades sem mapeamento na tabela de equivalência V11"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0051",
        detected_at="2026-04-01T09:00:00Z",
        data_base="2026-03",
        document="3050",
        dimension_r18=9,
        dimension_name="Integridade",
        severity="low",
        status="open",
        description="Permissões de escrita encontradas em perfil 'consulta' no schema gold — viola segregação gerar/aprovar exigida pelo Art. 2, §2, IX",
        owner="seguranca.dados@bankcorp.com",
        detected_by="manual:auditoria.interna@bankcorp.com",
        critica_id=None,
        run_config_name="silver_3050",
        dqx_check_name=None,
        dqx_check_function=None,
        affected_records=None,
        studio_url=None,
        timeline=[
            IncidentEvent(timestamp="2026-04-01T09:00:00Z", event_type="detected", actor="manual:auditoria.interna@bankcorp.com",
                          description="Auditoria interna identificou perfil 'consulta' com permissão de modificação no Unity Catalog (gold.qualidade_dimensoes_mensal)."),
        ],
    ),
]

# English (en-US) variant of `_MOCK_IRREGULARITIES`. Same structure; only
# human-readable free text is translated. Codes/identifiers/emails/dates/numbers
# are kept byte-identical with the PT originals.
_MOCK_IRREGULARITIES_EN: list[Irregularity] = [
    # ---- AUTO-EMITTED (DQX) ----
    Irregularity(
        id="IRR-2026-0042",
        detected_at="2026-03-15T14:00:00Z",
        data_base="2026-02",
        document="3040",
        dimension_r18=8,
        dimension_name="Consistency",
        severity="high",
        status="resolved",
        description="3040 vs 3050 divergence above tolerance for the real estate credit modality (0.7% > 0.5%)",
        root_cause="Real estate assignment operations not mapped in the V11 equivalence table",
        impact="Submission block on 3040 and 3050 for 2 business days",
        remedial_action="Equivalence table updated with new real estate assignment rules",
        owner="eng.dados@bankcorp.com",
        resolved_at="2026-03-17T10:00:00Z",
        resolution_days=2,
        included_in_report="2026-S1",
        detected_by="dqx:auto-emit",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-15T16:00:00Z",
        validated_by="gestor.info@bankcorp.com",
        validated_at="2026-03-17T14:00:00Z",
        critica_id="CR2_018",
        run_config_name="silver_3050",
        dqx_check_name="saldo_3040_vs_3050_consistente",
        dqx_check_function="sql_expression",
        affected_records=412,
        last_seen_run_id="run_2026_03_15_silver_3050_b421",
        studio_url=_dqx_studio_url("silver_3050", "saldo_3040_vs_3050_consistente"),
        timeline=[
            IncidentEvent(timestamp="2026-03-15T14:00:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detected by the DQX run silver_3050 — 412 divergent records above the 0.5% tolerance."),
            IncidentEvent(timestamp="2026-03-15T14:30:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Assigned to eng.dados@bankcorp.com for root cause analysis"),
            IncidentEvent(timestamp="2026-03-15T16:00:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Root cause identified: real estate assignments not mapped in the V11 equivalence"),
            IncidentEvent(timestamp="2026-03-17T10:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Equivalence table updated and reprocessing completed successfully"),
            IncidentEvent(timestamp="2026-03-17T14:00:00Z", event_type="validated", actor="gestor.info@bankcorp.com",
                          description="Resolution validated. Divergence eliminated in the reprocessed data."),
        ],
    ),
    Irregularity(
        id="IRR-2026-0041",
        detected_at="2026-03-10T08:00:00Z",
        data_base="2026-02",
        document="3040",
        dimension_r18=6,
        dimension_name="Completeness / Adaptability",
        severity="high",
        status="resolved",
        description="250 operations with CNPJ_IF outside the required format (8 numeric digits required by the layout)",
        root_cause="Bug in the silver transformation: cnpj_if truncated to 7 digits",
        impact="Rejection of 3040 submission 1 for Feb/2026",
        remedial_action="Silver pipeline fixed, data reprocessed and submission 2 resent",
        owner="eng.dados@bankcorp.com",
        resolved_at="2026-03-12T16:00:00Z",
        resolution_days=2,
        included_in_report="2026-S1",
        detected_by="dqx:auto-emit",
        responded_by="eng.dados@bankcorp.com",
        responded_at="2026-03-10T10:30:00Z",
        validated_by="coord.dados@bankcorp.com",
        validated_at="2026-03-12T17:00:00Z",
        critica_id="S10_002",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="cnpj_if_format_valid",
        dqx_check_function="regex_match",
        affected_records=250,
        last_seen_run_id="run_2026_03_10_silver_3040_a812",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "cnpj_if_format_valid"),
        timeline=[
            IncidentEvent(timestamp="2026-03-10T08:00:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detected by the DQX run silver_3040_operacoes — 250 operations with invalid CNPJ_IF."),
            IncidentEvent(timestamp="2026-03-10T08:15:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Assigned to eng.dados@bankcorp.com - high priority due to submission block"),
            IncidentEvent(timestamp="2026-03-10T10:30:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Bug identified: cnpj_if truncated to 7 digits in the silver_3040 notebook"),
            IncidentEvent(timestamp="2026-03-12T16:00:00Z", event_type="resolved", actor="eng.dados@bankcorp.com",
                          description="Pipeline fixed, data reprocessed, submission 2 sent successfully"),
            IncidentEvent(timestamp="2026-03-12T17:00:00Z", event_type="validated", actor="coord.dados@bankcorp.com",
                          description="Validation confirmed: all 250 operations with correct CNPJ_IF"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0048",
        detected_at="2026-04-02T03:12:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=3,
        dimension_name="Adaptability",
        severity="high",
        status="in_progress",
        description="38 clients with PorteCli outside the current domain of the SCR 3040 layout",
        owner="eng.dados@bankcorp.com",
        detected_by="dqx:auto-emit",
        critica_id="S20_005",
        run_config_name="silver_3040_clientes",
        dqx_check_name="porte_cli_in_dominio",
        dqx_check_function="foreign_key",
        affected_records=38,
        last_seen_run_id="run_2026_04_02_silver_3040_clientes_c014",
        studio_url=_dqx_studio_url("silver_3040_clientes", "porte_cli_in_dominio"),
        timeline=[
            IncidentEvent(timestamp="2026-04-02T03:12:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detected by the DQX run silver_3040_clientes — 38 clients with invalid PorteCli."),
            IncidentEvent(timestamp="2026-04-02T09:40:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Assigned to eng.dados@bankcorp.com for investigation"),
            IncidentEvent(timestamp="2026-04-02T11:05:00Z", event_type="in_progress", actor="eng.dados@bankcorp.com",
                          description="Investigation started — suspected outdated domain in reference.dominios"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0049",
        detected_at="2026-04-08T03:10:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=11,
        dimension_name="Relevance",
        severity="medium",
        status="open",
        description="14 operations of modality 0102 above the internal cap defined by the Data Curator",
        detected_by="dqx:auto-emit",
        critica_id="N3_001",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="limite_credito_por_modalidade",
        dqx_check_function="sql_expression",
        affected_records=14,
        last_seen_run_id="run_2026_04_08_silver_3040_d901",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "limite_credito_por_modalidade"),
        timeline=[
            IncidentEvent(timestamp="2026-04-08T03:10:00Z", event_type="detected", actor="dqx:auto-emit",
                          description="Auto-detected by the DQX run silver_3040_operacoes — 14 operations above the cap of modality 0102."),
        ],
    ),
    # ---- MANUAL (Críticas SCR drilldown) ----
    Irregularity(
        id="IRR-2026-0050",
        detected_at="2026-04-10T11:20:00Z",
        data_base="2026-03",
        document="3040",
        dimension_r18=8,
        dimension_name="Consistency",
        severity="medium",
        status="in_progress",
        description="Modalities without mapping in the 3040↔3050 equivalence table — operations will not consolidate into the 3050",
        owner="analyst@bankcorp.com",
        detected_by="manual:analyst@bankcorp.com",
        critica_id="CR2_018",
        run_config_name="silver_3040_operacoes",
        dqx_check_name="modalidade_equivalencia_3040_3050",
        dqx_check_function="foreign_key",
        affected_records=89,
        last_seen_run_id="run_2026_04_10_silver_3040_e502",
        studio_url=_dqx_studio_url("silver_3040_operacoes", "modalidade_equivalencia_3040_3050"),
        timeline=[
            IncidentEvent(timestamp="2026-04-10T11:20:00Z", event_type="detected", actor="manual:analyst@bankcorp.com",
                          description="Created manually from Críticas SCR — 89 records without 3040↔3050 equivalence."),
            IncidentEvent(timestamp="2026-04-10T13:00:00Z", event_type="assigned", actor="coord.dados@bankcorp.com",
                          description="Assigned to analyst@bankcorp.com to open the action plan"),
            IncidentEvent(timestamp="2026-04-10T14:30:00Z", event_type="in_progress", actor="analyst@bankcorp.com",
                          description="Started analysis of modalities without mapping in the V11 equivalence table"),
        ],
    ),
    Irregularity(
        id="IRR-2026-0051",
        detected_at="2026-04-01T09:00:00Z",
        data_base="2026-03",
        document="3050",
        dimension_r18=9,
        dimension_name="Integrity",
        severity="low",
        status="open",
        description="Write permissions found on a 'consulta' profile in the gold schema — violates the generate/approve segregation required by Art. 2, §2, IX",
        owner="seguranca.dados@bankcorp.com",
        detected_by="manual:auditoria.interna@bankcorp.com",
        critica_id=None,
        run_config_name="silver_3050",
        dqx_check_name=None,
        dqx_check_function=None,
        affected_records=None,
        studio_url=None,
        timeline=[
            IncidentEvent(timestamp="2026-04-01T09:00:00Z", event_type="detected", actor="manual:auditoria.interna@bankcorp.com",
                          description="Internal audit identified a 'consulta' profile with modification permission in Unity Catalog (gold.qualidade_dimensoes_mensal)."),
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
        description="Fix na transformação silver para preservar 8 dígitos do CNPJ_IF conforme layout SCR",
        owner="eng.dados@bankcorp.com", created_at="2026-03-10T11:00:00Z",
        deadline="2026-03-25", status="completed", progress_pct=100.0,
        dimension_r18=6, dimension_name="Completude / Adaptabilidade",
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

# English (en-US) variant of `_MOCK_ACTION_PLANS`. Same structure; only
# human-readable free text is translated.
_MOCK_ACTION_PLANS_EN = [
    ActionPlan(
        id="AP-2026-001", irregularity_id="IRR-2026-0042",
        title="Update the V11 equivalence table",
        description="Include real estate assignment rules in the 3040→3050 mapping (mod_3050_equiv) used by silver",
        owner="eng.dados@bankcorp.com", created_at="2026-03-15T17:00:00Z",
        deadline="2026-04-15", status="completed", progress_pct=100.0,
        dimension_r18=8, dimension_name="Consistency",
        updates=[
            ActionPlanUpdate(date="2026-03-16", author="eng.dados@bankcorp.com", note="Mapping of new assignment rules started"),
            ActionPlanUpdate(date="2026-03-17", author="eng.dados@bankcorp.com", note="Table updated, reprocessing completed and validated"),
        ],
    ),
    ActionPlan(
        id="AP-2026-002", irregularity_id="IRR-2026-0041",
        title="Fix CNPJ truncation in the silver pipeline",
        description="Fix in the silver transformation to preserve the 8 digits of CNPJ_IF per the SCR layout",
        owner="eng.dados@bankcorp.com", created_at="2026-03-10T11:00:00Z",
        deadline="2026-03-25", status="completed", progress_pct=100.0,
        dimension_r18=6, dimension_name="Completeness / Adaptability",
        updates=[
            ActionPlanUpdate(date="2026-03-11", author="eng.dados@bankcorp.com", note="Bug identified in the silver_3040 notebook, line 142"),
            ActionPlanUpdate(date="2026-03-12", author="eng.dados@bankcorp.com", note="Fix applied, reprocessing completed, submission 2 accepted"),
        ],
    ),
    ActionPlan(
        id="AP-2026-004", irregularity_id="IRR-2026-0051",
        title="Apply segregation of duties on the gold schema (Integrity)",
        description="Revoke modification privileges from the 'consulta' profile on gold.qualidade_dimensoes_mensal and other gold tables; keep read-only access per the SoD matrix of Art. 2, §2, IX (R.18)",
        owner="seguranca.dados@bankcorp.com", created_at="2026-04-01T10:00:00Z",
        deadline="2026-05-15", status="pending", progress_pct=0.0,
        dimension_r18=9, dimension_name="Integrity",
        auditor_caveat="R8 - Complete the segregation matrix for the semi-annual report per the caveat",
        updates=[],
    ),
]


# ---------------------------------------------------------------------------
# Locale-aware mock dataset selectors
# ---------------------------------------------------------------------------

def _irregularities(locale: str) -> list[Irregularity]:
    return _MOCK_IRREGULARITIES_EN if locale == "en" else _MOCK_IRREGULARITIES


def _action_plans(locale: str) -> list[ActionPlan]:
    return _MOCK_ACTION_PLANS_EN if locale == "en" else _MOCK_ACTION_PLANS


# ---------------------------------------------------------------------------
# Internal: row → Irregularity mappers
# ---------------------------------------------------------------------------

def _row_to_irregularity(r: dict) -> Irregularity:
    """Map a ``governance.incidents`` row to the UI ``Irregularity`` shape."""
    dim_raw = r.get("dimensao_r18")
    dim_int = dim_raw if isinstance(dim_raw, int) else _DIM_ROMAN_TO_INT.get(str(dim_raw or ""), 0)
    detected_at = r.get("detected_at")
    resolved_at = r.get("resolved_at")
    resolution_days = None
    if detected_at and resolved_at:
        try:
            resolution_days = max(0, int((resolved_at - detected_at).days))
        except Exception:  # noqa: BLE001
            resolution_days = None
    # `r.get("timeline")` pode vir como numpy.ndarray (databricks-sql-connector
    # converte ARRAY<STRUCT<>> via pandas em alguns paths). `arr or []` chama
    # bool(arr) que dispara "truth value of array is ambiguous". Tratamos
    # explicitamente: None vira []; arrays e listas iteramos direto.
    timeline_raw = r.get("timeline")
    if timeline_raw is None:
        timeline_iter = []
    else:
        try:
            timeline_iter = list(timeline_raw)
        except TypeError:
            timeline_iter = []
    timeline: list[IncidentEvent] = []
    for ev in timeline_iter:
        # STRUCT pode chegar como dict OU numpy structured row. Acessamos via
        # dict() quando possível.
        if not isinstance(ev, dict):
            try:
                ev = dict(ev)
            except (TypeError, ValueError):
                continue
        timeline.append(IncidentEvent(
            timestamp=str(ev.get("timestamp") or ""),
            event_type=str(ev.get("event_type") or ""),
            actor=str(ev.get("actor") or ""),
            description=str(ev.get("description") or ""),
        ))
    return Irregularity(
        id=r.get("incident_id") or "",
        detected_at=str(detected_at) if detected_at else "",
        data_base=str(r.get("dt_base") or ""),
        document=r.get("documento") or "",
        dimension_r18=dim_int,
        dimension_name=r.get("dimensao_nome") or "",
        severity=_SEVERITY_MAP.get(r.get("severidade") or "", "medium"),
        status=_STATUS_MAP.get(r.get("status") or "", "open"),
        description=r.get("mensagem") or "",
        root_cause=r.get("root_cause"),
        impact=r.get("impact"),
        remedial_action=r.get("remedial_action"),
        owner=r.get("owner"),
        resolved_at=str(resolved_at) if resolved_at else None,
        resolution_days=resolution_days,
        detected_by=r.get("detected_by"),
        responded_by=r.get("responded_by"),
        responded_at=str(r["responded_at"]) if r.get("responded_at") else None,
        validated_by=r.get("validated_by"),
        validated_at=str(r["validated_at"]) if r.get("validated_at") else None,
        escalated_at=str(r["escalated_at"]) if r.get("escalated_at") else None,
        escalated_to=r.get("escalated_to"),
        bcb_communication_required=bool(r.get("bcb_communication_required") or False),
        included_in_report=r.get("included_in_report"),
        timeline=timeline,
        critica_id=r.get("critica_id"),
        run_config_name=r.get("run_config_name"),
        dqx_check_name=r.get("check_name"),
        dqx_check_function=None,
        studio_url=_dqx_studio_url(r.get("run_config_name"), r.get("check_name")),
        affected_records=int(r["affected_records"]) if r.get("affected_records") is not None else None,
        last_seen_run_id=r.get("last_seen_run_id"),
    )


# ---------------------------------------------------------------------------
# Endpoints — Incidents
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
    locale: str = Depends(get_locale),
):
    """Return log of quality incidents with resolution status.

    URL is preserved as ``/irregularities`` for backward compat; underlying
    table is now ``governance.incidents`` (post Phase-7)."""
    if USE_MOCK:
        mock_items = _irregularities(locale)
        items = list(mock_items)
        if status:
            items = [i for i in items if i.status == status]
        if severity:
            items = [i for i in items if i.severity == severity]
        if dimension_r18:
            items = [i for i in items if i.dimension_r18 == dimension_r18]
        total = len(items)
        paged = items[(page - 1) * page_size : page * page_size]
        counts = {"open": 0, "in_progress": 0, "resolved": 0}
        for it in mock_items:
            if it.status == "open":
                counts["open"] += 1
            elif it.status == "in_progress":
                counts["in_progress"] += 1
            elif it.status in ("resolved", "validated"):
                counts["resolved"] += 1
        by_dim: dict[int, dict] = {}
        for it in mock_items:
            if it.dimension_r18:
                e = by_dim.setdefault(it.dimension_r18, {"name": it.dimension_name, "count": 0})
                e["count"] += 1
        return IrregularitiesResponse(
            total=total,
            irregularities=paged,
            summary=IrregularitySummary(
                total_open=counts["open"],
                total_in_progress=counts["in_progress"],
                total_resolved=counts["resolved"],
                avg_resolution_days=2.0,
                by_dimension=[
                    IrregularityDimensionSummary(dimension_id=k, name=v["name"], count=v["count"])
                    for k, v in sorted(by_dim.items())
                ],
            ),
            pagination=Pagination(
                page=page, page_size=page_size, total_results=total,
                total_pages=max(1, (total + page_size - 1) // page_size),
            ),
        )

    # ── Real mode: read from governance.incidents ──────────────────────────
    status_filter = _STATUS_REVERSE_MAP.get(status) if status else None
    severity_filter = _SEVERITY_REVERSE_MAP.get(severity) if severity else None
    dim_roman_filter = _DIM_INT_TO_ROMAN.get(int(dimension_r18)) if dimension_r18 else None

    where_parts = [
        "(:status IS NULL OR i.status = :status)",
        "(:severidade IS NULL OR i.severidade = :severidade)",
        "(:dim_roman IS NULL OR i.dimensao_r18 = :dim_roman)",
        "i.dt_base >= :data_base_from AND i.dt_base <= :data_base_to",
    ]
    where_sql = " AND ".join(where_parts)

    rows = await execute_query(
        "SELECT i.incident_id, i.critica_id, i.run_config_name, i.dt_base, i.documento, "
        "i.check_name, i.rule_fingerprint, i.first_seen_run_id, i.last_seen_run_id, "
        "i.affected_records, i.total_records, i.taxa_violacao_pct, "
        "i.dimensao_r18, i.artigo_r18, i.nivel_verificacao, i.severidade, i.mensagem, "
        "i.status, i.owner, i.detected_at, i.detected_by, "
        "i.assigned_at, i.responded_at, i.responded_by, "
        "i.escalated_at, i.escalated_to, "
        "i.resolved_at, i.resolved_by, i.validated_at, i.validated_by, i.reopened_at, "
        "i.root_cause, i.remedial_action, i.impact, i.bcb_communication_required, "
        "i.included_in_report, i.timeline, "
        "d.nome AS dimensao_nome "
        f"FROM {CATALOG}.governance.incidents i "
        f"LEFT JOIN {CATALOG}.reference.dimensoes_r18 d ON d.dimensao_id = "
        "  CASE i.dimensao_r18 WHEN 'I' THEN 1 WHEN 'II' THEN 2 WHEN 'III' THEN 3 "
        "    WHEN 'IV' THEN 4 WHEN 'V' THEN 5 WHEN 'VI' THEN 6 WHEN 'VII' THEN 7 "
        "    WHEN 'VIII' THEN 8 WHEN 'IX' THEN 9 WHEN 'X' THEN 10 "
        "    WHEN 'XI' THEN 11 WHEN 'XII' THEN 12 END "
        f"WHERE {where_sql} "
        "ORDER BY i.detected_at DESC LIMIT :page_size OFFSET :offset",
        {
            "status": status_filter,
            "severidade": severity_filter,
            "dim_roman": dim_roman_filter,
            "data_base_from": data_base_from,
            "data_base_to": data_base_to,
            "page_size": page_size,
            "offset": (page - 1) * page_size,
        },
    )

    items = [_row_to_irregularity(r) for r in rows]

    # Aggregations across the full filtered result set (not just the current page).
    summary_rows = await execute_query(
        "SELECT i.status, i.dimensao_r18, i.detected_at, i.resolved_at, d.nome "
        f"FROM {CATALOG}.governance.incidents i "
        f"LEFT JOIN {CATALOG}.reference.dimensoes_r18 d ON d.dimensao_id = "
        "  CASE i.dimensao_r18 WHEN 'I' THEN 1 WHEN 'II' THEN 2 WHEN 'III' THEN 3 "
        "    WHEN 'IV' THEN 4 WHEN 'V' THEN 5 WHEN 'VI' THEN 6 WHEN 'VII' THEN 7 "
        "    WHEN 'VIII' THEN 8 WHEN 'IX' THEN 9 WHEN 'X' THEN 10 "
        "    WHEN 'XI' THEN 11 WHEN 'XII' THEN 12 END "
        f"WHERE {where_sql}",
        {
            "status": status_filter,
            "severidade": severity_filter,
            "dim_roman": dim_roman_filter,
            "data_base_from": data_base_from,
            "data_base_to": data_base_to,
        },
    )
    total = len(summary_rows)
    counts = {"open": 0, "in_progress": 0, "resolved": 0}
    resolution_days_sum = 0
    resolution_days_count = 0
    by_dim: dict[int, dict] = {}
    for s in summary_rows:
        ui_status = _STATUS_MAP.get(s.get("status") or "", "open")
        if ui_status in ("open", "assigned"):
            counts["open"] += 1
        elif ui_status in ("in_progress", "escalated"):
            counts["in_progress"] += 1
        elif ui_status in ("resolved", "validated"):
            counts["resolved"] += 1
        if s.get("resolved_at") and s.get("detected_at"):
            try:
                delta = s["resolved_at"] - s["detected_at"]
                resolution_days_sum += delta.days
                resolution_days_count += 1
            except Exception:  # noqa: BLE001
                pass
        d_int = _DIM_ROMAN_TO_INT.get(str(s.get("dimensao_r18") or ""), 0)
        if d_int:
            entry = by_dim.setdefault(d_int, {"name": s.get("nome") or "", "count": 0})
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
async def get_irregularity_detail(
    irregularity_id: str,
    locale: str = Depends(get_locale),
):
    """Return single incident with full lifecycle timeline and linked action plans."""
    if USE_MOCK:
        item = next((i for i in _irregularities(locale) if i.id == irregularity_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Incidente não encontrado")
        plans = [p for p in _action_plans(locale) if p.irregularity_id == irregularity_id]
        return IrregularityDetailResponse(irregularity=item, action_plans=plans)

    rows = await execute_query(
        "SELECT i.incident_id, i.critica_id, i.run_config_name, i.dt_base, i.documento, "
        "i.check_name, i.rule_fingerprint, i.first_seen_run_id, i.last_seen_run_id, "
        "i.affected_records, i.total_records, i.taxa_violacao_pct, "
        "i.dimensao_r18, i.artigo_r18, i.nivel_verificacao, i.severidade, i.mensagem, "
        "i.status, i.owner, i.detected_at, i.detected_by, "
        "i.assigned_at, i.responded_at, i.responded_by, "
        "i.escalated_at, i.escalated_to, "
        "i.resolved_at, i.resolved_by, i.validated_at, i.validated_by, i.reopened_at, "
        "i.root_cause, i.remedial_action, i.impact, i.bcb_communication_required, "
        "i.included_in_report, i.timeline, "
        "d.nome AS dimensao_nome "
        f"FROM {CATALOG}.governance.incidents i "
        f"LEFT JOIN {CATALOG}.reference.dimensoes_r18 d ON d.dimensao_id = "
        "  CASE i.dimensao_r18 WHEN 'I' THEN 1 WHEN 'II' THEN 2 WHEN 'III' THEN 3 "
        "    WHEN 'IV' THEN 4 WHEN 'V' THEN 5 WHEN 'VI' THEN 6 WHEN 'VII' THEN 7 "
        "    WHEN 'VIII' THEN 8 WHEN 'IX' THEN 9 WHEN 'X' THEN 10 "
        "    WHEN 'XI' THEN 11 WHEN 'XII' THEN 12 END "
        "WHERE i.incident_id = :incident_id LIMIT 1",
        {"incident_id": irregularity_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Incidente não encontrado")
    return IrregularityDetailResponse(irregularity=_row_to_irregularity(rows[0]), action_plans=[])


# ---------------------------------------------------------------------------
# Endpoints — Incident creation & lifecycle (spec §4.2 / §4.3)
# ---------------------------------------------------------------------------


@router.post("/incidents", response_model=Irregularity, status_code=201)
async def create_incident(
    body: IncidentCreateRequest,
    request: Request,
    locale: str = Depends(get_locale),
):
    """Manually create an incident from the Críticas SCR drilldown.

    Dedup key (spec §4.1 / §4.2): ``(critica_id, run_config_name, dt_base)``
    constrained to ``status NOT IN ('resolved','validated')``. When a matching
    open incident already exists, returns **409 Conflict** with the existing
    ``incident_id`` in the response body so the frontend can deep-link to it.
    """
    actor = _caller_email(request)
    detected_by = f"manual:{actor}"

    if USE_MOCK:
        mock_items = _irregularities(locale)
        # In-memory dedup against open incidents.
        existing = next(
            (i for i in mock_items
             if i.critica_id == body.critica_id
             and i.run_config_name == body.run_config_name
             and i.data_base == body.dt_base
             and i.status not in ("resolved", "validated")),
            None,
        )
        if existing and body.critica_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "incident_already_open",
                    "message": (
                        "An open incident already exists for this validation on this data-base."
                        if locale == "en"
                        else "Já existe um incidente aberto para esta crítica nesta data-base."
                    ),
                    "incident_id": existing.id,
                    "existing_incident_id": existing.id,
                },
            )

        # Build new mock incident
        new_id = f"IRR-MAN-{uuid.uuid4().hex[:8].upper()}"
        severity_ui = body.severity
        if severity_ui in ("error",):
            severity_ui = "high"
        elif severity_ui in ("warning",):
            severity_ui = "medium"
        elif severity_ui in ("info",):
            severity_ui = "low"
        now = _now_iso()
        item = Irregularity(
            id=new_id,
            detected_at=now,
            data_base=body.dt_base,
            document=body.document or _document_from_run_config(body.run_config_name),
            dimension_r18=body.dimension_r18 or 0,
            dimension_name="",
            severity=severity_ui if severity_ui in ("high", "medium", "low") else "medium",
            status="open",
            description=body.description,
            owner=body.owner,
            detected_by=detected_by,
            critica_id=body.critica_id,
            run_config_name=body.run_config_name,
            dqx_check_name=body.dqx_check_name,
            dqx_check_function=body.dqx_check_function,
            affected_records=body.affected_records,
            studio_url=_dqx_studio_url(body.run_config_name, body.dqx_check_name),
            timeline=[
                IncidentEvent(
                    timestamp=now, event_type="detected", actor=detected_by,
                    description=(
                        f"Created manually from Críticas SCR by user {actor}."
                        if locale == "en"
                        else f"Criado manualmente a partir da Críticas SCR pelo usuário {actor}."
                    ),
                ),
            ],
        )
        mock_items.insert(0, item)
        return item

    # ── Real mode: MERGE INTO governance.incidents ─────────────────────────
    # Pre-check: is there an open incident matching the dedup key?
    dedup_rows = await execute_query(
        "SELECT incident_id "
        f"FROM {CATALOG}.governance.incidents "
        "WHERE critica_id = :critica_id "
        "  AND run_config_name = :run_config_name "
        "  AND dt_base = :dt_base "
        "  AND status NOT IN ('resolved','validated') "
        "LIMIT 1",
        {
            "critica_id": body.critica_id,
            "run_config_name": body.run_config_name,
            "dt_base": body.dt_base,
        },
    )
    if dedup_rows and body.critica_id:
        existing_id = dedup_rows[0]["incident_id"]
        raise HTTPException(
            status_code=409,
            detail={
                "code": "incident_already_open",
                "message": "Já existe um incidente aberto para esta crítica nesta data-base.",
                "incident_id": existing_id,
                "existing_incident_id": existing_id,
            },
        )

    incident_id = str(uuid.uuid4())
    severidade = _SEVERITY_REVERSE_MAP.get(body.severity, "ALERTA")
    dim_roman = _DIM_INT_TO_ROMAN.get(int(body.dimension_r18)) if body.dimension_r18 else None
    documento = body.document or _document_from_run_config(body.run_config_name)

    # INSERT (MERGE is used by the auto-emit job for re-observation; manual
    # creation is INSERT-only because the dedup-pre-check above guarantees no
    # open row exists).
    await execute_query(
        f"INSERT INTO {CATALOG}.governance.incidents ("
        "  incident_id, critica_id, run_config_name, dt_base, "
        "  check_name, affected_records, "
        "  documento, dimensao_r18, nivel_verificacao, severidade, mensagem, "
        "  status, owner, detected_at, detected_by, timeline"
        ") VALUES ("
        "  :incident_id, :critica_id, :run_config_name, :dt_base, "
        "  :check_name, :affected_records, "
        "  :documento, :dimensao_r18, NULL, :severidade, :mensagem, "
        "  'detected', :owner, current_timestamp(), :detected_by, "
        "  array(named_struct("
        "    'timestamp',   current_timestamp(),"
        "    'event_type',  'detected',"
        "    'actor',       :detected_by,"
        "    'description', :timeline_desc))"
        ")",
        {
            "incident_id": incident_id,
            "critica_id": body.critica_id,
            "run_config_name": body.run_config_name,
            "dt_base": body.dt_base,
            "check_name": body.dqx_check_name,
            "affected_records": body.affected_records,
            "documento": documento,
            "dimensao_r18": dim_roman,
            "severidade": severidade,
            "mensagem": body.description,
            "owner": body.owner,
            "detected_by": detected_by,
            "timeline_desc": f"Criado manualmente a partir da Críticas SCR pelo usuário {actor}.",
        },
    )

    rows = await execute_query(
        "SELECT incident_id, critica_id, run_config_name, dt_base, documento, check_name, "
        "  affected_records, dimensao_r18, severidade, mensagem, status, owner, "
        "  detected_at, detected_by, timeline "
        f"FROM {CATALOG}.governance.incidents WHERE incident_id = :id",
        {"id": incident_id},
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Falha ao gravar incidente.")
    return _row_to_irregularity(rows[0])


@router.patch("/incidents/{incident_id}/status", response_model=Irregularity)
async def update_incident_status(
    incident_id: str,
    body: IncidentStatusUpdateRequest,
    request: Request,
    locale: str = Depends(get_locale),
):
    """Transition an incident through the FSM (spec §4.3 / §12.4).

    Allowed transitions are defined in ``_FSM_TRANSITIONS``. Each call appends
    an ``IncidentEvent`` to ``timeline`` and updates denormalized columns
    (``owner``, ``resolved_at``, ``validated_at`` …) as appropriate.
    """
    target_storage = _STATUS_REVERSE_MAP.get(body.status, body.status)
    if target_storage not in _STATUS_REVERSE_MAP.values():
        raise HTTPException(status_code=400, detail=f"Status inválido: {body.status}")

    actor = _caller_email(request)
    now = _now_iso()

    if USE_MOCK:
        item = next((i for i in _irregularities(locale) if i.id == incident_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Incidente não encontrado")
        current_storage = _STATUS_REVERSE_MAP.get(item.status, item.status)
        allowed = _FSM_TRANSITIONS.get(current_storage, set())
        if target_storage not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Transição inválida: {current_storage} → {target_storage}. Permitidas: {sorted(allowed)}",
            )
        item.status = _STATUS_MAP.get(target_storage, target_storage)
        if body.owner:
            item.owner = body.owner
        if body.root_cause:
            item.root_cause = body.root_cause
        if body.remedial_action:
            item.remedial_action = body.remedial_action
        if body.escalated_to:
            item.escalated_to = body.escalated_to
        if target_storage == "resolved":
            item.resolved_at = now
            item.responded_by = item.responded_by or actor
        if target_storage == "validated":
            item.validated_at = now
            item.validated_by = actor
        if target_storage == "escalated":
            item.escalated_at = now
        timeline_desc = body.comment or (
            f"Transitioned to {target_storage} by {actor}."
            if locale == "en"
            else f"Transição para {target_storage} por {actor}."
        )
        item.timeline = list(item.timeline) + [
            IncidentEvent(timestamp=now, event_type=target_storage, actor=actor, description=timeline_desc)
        ]
        return item

    # ── Real mode ──────────────────────────────────────────────────────────
    current_rows = await execute_query(
        "SELECT status "
        f"FROM {CATALOG}.governance.incidents WHERE incident_id = :id LIMIT 1",
        {"id": incident_id},
    )
    if not current_rows:
        raise HTTPException(status_code=404, detail="Incidente não encontrado")
    current_storage = current_rows[0].get("status") or "detected"
    allowed = _FSM_TRANSITIONS.get(current_storage, set())
    if target_storage not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição inválida: {current_storage} → {target_storage}. Permitidas: {sorted(allowed)}",
        )

    set_clauses = [
        "status = :target",
        "updated_at = current_timestamp()",
        "timeline = array_union(COALESCE(timeline, array()), array(named_struct("
        "  'timestamp', current_timestamp(),"
        "  'event_type', :target,"
        "  'actor', :actor,"
        "  'description', :timeline_desc)))",
    ]
    params: dict[str, str | int | None] = {
        "id": incident_id,
        "target": target_storage,
        "actor": actor,
        "timeline_desc": body.comment or f"Transição para {target_storage} por {actor}.",
    }
    if body.owner:
        set_clauses.append("owner = :owner")
        params["owner"] = body.owner
    if body.root_cause:
        set_clauses.append("root_cause = :root_cause")
        params["root_cause"] = body.root_cause
    if body.remedial_action:
        set_clauses.append("remedial_action = :remedial_action")
        params["remedial_action"] = body.remedial_action
    if body.escalated_to:
        set_clauses.append("escalated_to = :escalated_to")
        params["escalated_to"] = body.escalated_to
    if target_storage == "resolved":
        set_clauses.append("resolved_at = current_timestamp()")
        set_clauses.append("resolved_by = :actor")
    elif target_storage == "validated":
        set_clauses.append("validated_at = current_timestamp()")
        set_clauses.append("validated_by = :actor")
    elif target_storage == "escalated":
        set_clauses.append("escalated_at = current_timestamp()")
    elif target_storage == "assigned":
        set_clauses.append("assigned_at = current_timestamp()")
    elif target_storage == "reopened":
        set_clauses.append("reopened_at = current_timestamp()")

    await execute_query(
        f"UPDATE {CATALOG}.governance.incidents SET {', '.join(set_clauses)} "
        "WHERE incident_id = :id",
        params,
    )

    rows = await execute_query(
        "SELECT incident_id, critica_id, run_config_name, dt_base, documento, check_name, "
        "  affected_records, dimensao_r18, severidade, mensagem, status, owner, "
        "  detected_at, detected_by, resolved_at, resolved_by, validated_at, validated_by, "
        "  escalated_at, escalated_to, root_cause, remedial_action, impact, "
        "  bcb_communication_required, included_in_report, timeline "
        f"FROM {CATALOG}.governance.incidents WHERE incident_id = :id",
        {"id": incident_id},
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Falha ao recuperar incidente atualizado.")
    return _row_to_irregularity(rows[0])


# ---------------------------------------------------------------------------
# Endpoints — Action Plans / Reports (unchanged)
# ---------------------------------------------------------------------------


@router.get("/action-plans", response_model=ActionPlansResponse)
async def get_action_plans(
    status: str | None = Query(None),
    owner: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    locale: str = Depends(get_locale),
):
    """Return action plans with filtering and pagination."""
    if USE_MOCK:
        items = list(_action_plans(locale))
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
async def get_governance_reports(locale: str = Depends(get_locale)):
    """Return list of semi-annual reports with generation and approval status.

    ``GovernanceReport`` carries no human-readable free text (only ids, codes,
    dates, counts), so the mock payload is locale-independent. ``locale`` is
    accepted for consistency with the other governance endpoints."""
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
