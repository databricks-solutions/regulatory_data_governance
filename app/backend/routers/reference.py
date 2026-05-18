"""Reference data endpoints: dominios, criticas, calendario, equivalencia, dimensions."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query

from db import CATALOG, DQX_CHECKS_TABLE, SCHEMA_REFERENCE, USE_MOCK
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when reference tables haven't been seeded yet (setup_job not run).
from db import execute_query_or_empty as execute_query
from rc18_rule_meta import meta_for
from models import (
    CalendarioDay,
    CalendarioResponse,
    CalendarioSummary,
    CalendarioWeek,
    CriticaRule,
    CriticasResponse,
    DimensionDefinition,
    DimensionMetricDef,
    DimensionsResponse,
    DominioField,
    DominioValue,
    DominiosResponse,
    EquivalenciaMapping,
    EquivalenciaResponse,
)

router = APIRouter()

# --- Mock data ---

_MOCK_DOMINIOS = [
    DominioField(field="Mod", description="Modalidade da operacao de credito", values=[
        DominioValue(code="0101", description="Adiantamento a depositantes"),
        DominioValue(code="0201", description="Emprestimos - Capital de giro com prazo de vencimento ate 365 dias"),
        DominioValue(code="0202", description="Emprestimos - Capital de giro com prazo superior a 365 dias"),
        DominioValue(code="0204", description="Emprestimos - Credito pessoal nao consignado"),
        DominioValue(code="0301", description="Titulos descontados"),
        DominioValue(code="0401", description="Financiamento imobiliario - SFH"),
        DominioValue(code="0402", description="Financiamento imobiliario - SFI"),
    ]),
    DominioField(field="TpCli", description="Tipo de cliente", values=[
        DominioValue(code="1", description="CPF (Pessoa Fisica)"),
        DominioValue(code="2", description="CNPJ base (8 digitos)"),
        DominioValue(code="3", description="CEI"),
        DominioValue(code="4", description="Nao residente"),
        DominioValue(code="5", description="CNPJ completo (14 digitos)"),
        DominioValue(code="6", description="Codigo BCB"),
    ]),
    DominioField(field="NatuOp", description="Natureza da operacao", values=[
        DominioValue(code="01", description="Normal (titular)"),
        DominioValue(code="04", description="Cessionaria"),
        DominioValue(code="11", description="Cedente com coobrigacao"),
        DominioValue(code="12", description="Cedente sem coobrigacao"),
    ]),
    DominioField(field="ClassOp", description="Classificacao de risco da operacao", values=[
        DominioValue(code="AA", description="Risco minimo"),
        DominioValue(code="A", description="Risco muito baixo"),
        DominioValue(code="B", description="Risco baixo"),
        DominioValue(code="C", description="Risco medio-baixo"),
        DominioValue(code="D", description="Risco medio"),
        DominioValue(code="E", description="Risco medio-alto"),
        DominioValue(code="F", description="Risco alto"),
        DominioValue(code="G", description="Risco muito alto"),
        DominioValue(code="H", description="Risco maximo (perda)"),
    ]),
]

# 4 regras iniciais do acelerador (mesmas semeadas em
# `${var.catalog}.quality.dqx_checks` a partir de
# `pipelines/silver/dqx_checks/scr3040.yml`). Novas regras serão criadas via
# DQX Studio (Motor de Regras) e aparecerão aqui assim que o pipeline silver
# as executar.
_MOCK_CRITICAS = [
    CriticaRule(rule_id="S20_001", document="3040", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", expression="autorzc IN ('S','N')", description="Autorzc deve pertencer ao dominio oficial {'S','N'} do leiaute SCR 3040", bcb_reference="SCR3040_Dominios.xlsx, Anexo Autorzc", layout_version="V1"),
    CriticaRule(rule_id="S20_002", document="3040", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", expression="CASE WHEN is_pf THEN porte_cli IN ('0'..'8') WHEN is_pj THEN porte_cli IN ('0'..'4') ELSE FALSE END", description="PorteCli condicional ao tipo de cliente — PF aceita 0-8; PJ aceita 0-4", bcb_reference="SCR3040_Dominios.xlsx, Anexo PorteCli", layout_version="V1"),
    CriticaRule(rule_id="S20_003", document="3040", rule_type="syntactic", severity="error", dimension_r18=3, dimension_name="Adaptabilidade", expression="tp_ctrl IN ('01','02','03','04')", description="TpCtrl deve pertencer ao dominio oficial {'01','02','03','04'} do leiaute SCR 3040", bcb_reference="SCR3040_Dominios.xlsx, Anexo TpCtrl", layout_version="V1"),
    CriticaRule(rule_id="S10_004", document="3040", rule_type="syntactic", severity="error", dimension_r18=2, dimension_name="Acurácia", expression="dia_atraso >= 0", description="DiaAtraso (dias em atraso) deve ser inteiro nao negativo", bcb_reference="SCR3040_Leiaute.xlsx, campo DiaAtraso", layout_version="V1"),
]

# Canonical 12 R.18 dimensions per docs/spec/01_requirements.md §1.2 (Art. 2, §2 of Joint Resolution 18).
_MOCK_DIMENSIONS = [
    DimensionDefinition(id=1, code="acessibilidade", name="Acessibilidade", article="Art. 2, par.2, I", definition="Condicoes para obter informacoes, incluindo local, forma, prazos e tratamento PcD", implementation="SLA de atendimento a demandas BCB documentado; catalogo acessivel a nao-tecnicos", databricks_capability="Unity Catalog (catalogo publico) + AI/BI Dashboards com ACLs por perfil", metrics=[DimensionMetricDef(code="sla_atendimento_pct", name="SLA de Atendimento", target=95.0, unit="%"), DimensionMetricDef(code="catalogo_cobertura_pct", name="Cobertura do Catalogo", target=100.0, unit="%")]),
    DimensionDefinition(id=2, code="acuracia", name="Acurácia", article="Art. 2, par.2, II", definition="Medida em que a informacao reflete a realidade de forma precisa, conforme metodologia", implementation="Taxa de rejeicao BCB <= 5%; reconciliacao pre-envio aprovada", databricks_capability="DLT Expectations pass/fail rates; reconciliation results", metrics=[DimensionMetricDef(code="taxa_rejeicao_bcb_pct", name="Taxa de Rejeicao BCB", target=5.0, unit="%")]),
    DimensionDefinition(id=3, code="adaptabilidade", name="Adaptabilidade", article="Art. 2, par.2, III", definition="Capacidade de gerar informacoes em formato que atenda diversas demandas e mudancas regulamentares, inclusive em crise", implementation="Evidencia de adaptacao V10->V11 dentro do prazo; plano de contingencia testado", databricks_capability="Layout version SCD Type 2 table; DR test logs", metrics=[DimensionMetricDef(code="adaptacao_layout_pct", name="Adaptacao de Leiaute no Prazo", target=100.0, unit="%")]),
    DimensionDefinition(id=4, code="clareza", name="Clareza", article="Art. 2, par.2, IV", definition="Apresentacao concisa, compreensivel, atendendo as necessidades do usuario", implementation="Dicionario de dados com descricoes em linguagem de negocio; onboarding <= 2 semanas", databricks_capability="UC COMMENT ON COLUMN coverage; AI/BI dashboards", metrics=[DimensionMetricDef(code="coberura_comentarios_pct", name="Cobertura de Comentarios UC", target=100.0, unit="%")]),
    DimensionDefinition(id=5, code="comparabilidade", name="Comparabilidade", article="Art. 2, par.2, V", definition="Capacidade de identificar semelhancas e diferencas entre periodos ou dominios", implementation="Historico de mudancas de leiaute versionado; metadados de versao em cada registro", databricks_capability="Delta Time Travel; SCD Type 2 for layout versions", metrics=[DimensionMetricDef(code="versao_leiaute_rastreavel_pct", name="Cobertura de Versao de Leiaute", target=100.0, unit="%")]),
    DimensionDefinition(id=6, code="completude", name="Completude", article="Art. 2, par.2, VI", definition="Capacidade de atender integralmente os aspectos requeridos", implementation="Zero rejeicoes por campos obrigatorios; reconciliacao de universo (qtd operacoes/clientes)", databricks_capability="DLT expect_or_drop rules (S10/S12/S13); universe count checks", metrics=[DimensionMetricDef(code="campos_obrigatorios_pct", name="Campos Obrigatorios Preenchidos", target=100.0, unit="%")]),
    DimensionDefinition(id=7, code="confiabilidade", name="Confiabilidade", article="Art. 2, par.2, VII", definition="Ausencia de desvio relevante nos dados revisados vs valor inicial", implementation="Dados intermediarios imutaveis; taxa de retrabalho < 10%", databricks_capability="Delta ACID; append-only audit tables; resubmission count", metrics=[DimensionMetricDef(code="taxa_retrabalho_pct", name="Taxa de Retrabalho", target=10.0, unit="%")]),
    DimensionDefinition(id=8, code="consistencia", name="Consistência", article="Art. 2, par.2, VIII", definition="Informacoes padronizadas e livres de contradicoes, mesmo de fontes diferentes", implementation="Pipeline automatizado: 3040 vs 3050 vs COSIF; divergencias acima de limiar bloqueiam envio", databricks_capability="Gold reconciliation tables (cross_3040_3050, cosif_t02_t10)", metrics=[DimensionMetricDef(code="taxa_consistencia_pct", name="Taxa de Consistencia", target=99.0, unit="%")]),
    DimensionDefinition(id=9, code="integridade", name="Integridade", article="Art. 2, par.2, IX", definition="Garantia de autenticidade e ausencia de modificacao nao autorizada", implementation="RBAC com menor privilegio; audit log inalteravel; segregacao gerar/aprovar", databricks_capability="UC RBAC configuration; audit logs; SoD matrix", metrics=[DimensionMetricDef(code="acessos_nao_autorizados", name="Acessos Nao Autorizados", target=0.0, unit="count")]),
    DimensionDefinition(id=10, code="rastreabilidade", name="Rastreabilidade", article="Art. 2, par.2, X", definition="Condicoes para rastrear a informacao desde a origem ate a disponibilizacao ao usuario final", implementation="Lineage end-to-end >= 95% do caminho; demonstracao em auditoria em < 30 min", databricks_capability="UC System Tables lineage + External Lineage API (BYOL)", metrics=[DimensionMetricDef(code="cobertura_lineage_pct", name="Cobertura de Lineage", target=95.0, unit="%")]),
    DimensionDefinition(id=11, code="relevancia", name="Relevância", article="Art. 2, par.2, XI", definition="Capacidade de fornecer informacoes uteis que influenciem tomada de decisoes", implementation="Relatorio semestral apresentado ao CA com ata de discussao; indicadores revisados pela diretoria mensalmente", databricks_capability="Semi-annual report generation; CA meeting evidence", metrics=[DimensionMetricDef(code="relatorios_apresentados", name="Relatorios Apresentados ao CA", target=2.0, unit="por ano")]),
    DimensionDefinition(id=12, code="tempestividade", name="Tempestividade", article="Art. 2, par.2, XII", definition="Fornecimento em tempo habil, no prazo estabelecido", implementation="Historico de cumprimento de prazos >= 95%; envio com >= 2 dias uteis de antecedencia", databricks_capability="Workflow SLA monitoring; submission timestamp logs", metrics=[DimensionMetricDef(code="envios_no_prazo_pct", name="Envios no Prazo", target=95.0, unit="%")]),
]


@router.get("/dominios", response_model=DominiosResponse)
async def get_dominios(
    document: str | None = Query(None),
    field: str | None = Query(None),
    version: str | None = Query(None),
):
    """Return domain values for SCR fields."""
    if USE_MOCK:
        fields = _MOCK_DOMINIOS
        if field:
            fields = [f for f in fields if f.field.lower() == field.lower()]
        return DominiosResponse(document=document, version=version or "V11", fields=fields)

    rows = await execute_query(
        "SELECT campo, valor_codigo, valor_descricao, anexo_referencia, "
        "leiaute_versao, is_current, observacoes "
        f"FROM {CATALOG}.{SCHEMA_REFERENCE}.dominios "
        "WHERE (:documento IS NULL OR documento = :documento) "
        "AND (:campo IS NULL OR campo = :campo) "
        "AND is_current = TRUE ORDER BY campo, valor_codigo",
        {"documento": document, "campo": field},
    )
    fields_map: dict[str, DominioField] = {}
    for r in rows:
        campo = r["campo"]
        if campo not in fields_map:
            fields_map[campo] = DominioField(field=campo, description=campo, values=[])
        fields_map[campo].values.append(DominioValue(code=r["valor_codigo"], description=r["valor_descricao"]))
    return DominiosResponse(document=document, version=version or "V11", fields=list(fields_map.values()))


@router.get("/criticas", response_model=CriticasResponse)
async def get_criticas(
    document: str | None = Query(None),
    rule_type: str | None = Query(None),
    severity: str | None = Query(None),
    dimension_r18: int | None = Query(None),
    search: str | None = Query(None),
):
    """Return criticas (validation rules) catalog."""
    if USE_MOCK:
        rules = _MOCK_CRITICAS
        if document:
            rules = [r for r in rules if r.document == document]
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        if severity:
            rules = [r for r in rules if r.severity == severity]
        if dimension_r18:
            rules = [r for r in rules if r.dimension_r18 == dimension_r18]
        if search:
            search_lower = search.lower()
            rules = [r for r in rules if search_lower in r.description.lower()]
        return CriticasResponse(total=len(rules), rules=rules)

    # Lê da tabela autoritativa de regras (DQX Studio `dq_quality_rules`).
    # Schema: rule_id, table_fqn, checks (JSON ARRAY), version, status, source.
    # Studio considera "active" tanto status='active' (snapshot inicial) quanto
    # 'approved' (workflow padrão da UI após aprovação). Outros estados
    # ('draft', 'archived', etc.) ficam fora.
    rows = await execute_query(
        "SELECT rule_id, table_fqn, checks, status, version, source, updated_at "
        f"FROM {DQX_CHECKS_TABLE} "
        "WHERE status IN ('active', 'approved') "
        "ORDER BY table_fqn, rule_id",
        {},
    )
    rules = _parse_dq_quality_rules_rows(rows)
    # Apply filters in Python — set is small (10s of rules) so this is fine.
    if document:
        rules = [r for r in rules if r.document == document]
    if rule_type:
        rules = [r for r in rules if r.rule_type == rule_type]
    if severity:
        rules = [r for r in rules if r.severity == severity]
    if dimension_r18:
        rules = [r for r in rules if r.dimension_r18 == dimension_r18]
    if search:
        s = search.lower()
        rules = [r for r in rules if s in r.description.lower()]
    return CriticasResponse(total=len(rules), rules=rules)


# Dimension Roman → int — duplicated from validation.py to avoid a cross-router
# import dependency. Keep in sync with docs/spec/01_requirements.md §1.2.
_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                 "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
_DIM_NAMES = {1: "Acessibilidade", 2: "Acurácia", 3: "Adaptabilidade",
              4: "Clareza", 5: "Comparabilidade", 6: "Completude",
              7: "Confiabilidade", 8: "Consistência", 9: "Integridade",
              10: "Rastreabilidade", 11: "Relevância", 12: "Tempestividade"}
# Mapping run_config_name prefix → document. Longest prefix wins to avoid
# `silver_3050` accidentally matching `silver_3040` (it doesn't, but be safe).
_DOC_FROM_RUN = [
    ("silver_3050", "3050"),
    ("silver_3040_", "3040"),
]


def _doc_from_table_fqn(table_fqn: str) -> str:
    """Derive '3040' or '3050' from a silver table FQN.

    Examples:
      rc18_catalog.silver.scr3040_clientes → '3040'
      rc18_catalog.silver.scr3050          → '3050'
      __sql_check__/<name>                 → '' (SQL-query checks; doc-agnostic)
    """
    if not table_fqn:
        return ""
    lower = table_fqn.lower()
    if "scr3040" in lower or ".3040" in lower:
        return "3040"
    if "scr3050" in lower or ".3050" in lower:
        return "3050"
    return ""


def _parse_dq_quality_rules_rows(rows: list[dict]) -> list[CriticaRule]:
    """Translate dq_quality_rules rows (Studio's JSON ARRAY shape) → CriticaRule.

    Studio stores each rule's `checks` column as a **JSON array** of check
    definitions (usually 1 element, but multi-check rows are valid). Each
    check carries the DQX library shape (`name`, `criticality`, `check`,
    optional `filter`, optional `user_metadata`, optional `run_config_name`).

    UI-created rules may omit `run_config_name` and `user_metadata` entirely
    — the binding is then the row's `table_fqn`. We accommodate both shapes.
    """
    out: list[CriticaRule] = []
    for r in rows:
        chk_raw = r.get("checks")
        try:
            parsed = json.loads(chk_raw) if isinstance(chk_raw, str) else (chk_raw or [])
        except (json.JSONDecodeError, TypeError):
            continue
        # Coerce: legacy seed wrote a single object; Studio writes an array.
        if isinstance(parsed, dict):
            checks_list = [parsed]
        elif isinstance(parsed, list):
            checks_list = parsed
        else:
            continue

        table_fqn = r.get("table_fqn") or ""
        # Prefer document derived from run_config_name (precise), fall back to
        # table_fqn (works for UI rules that lack a run_config).
        doc_from_table = _doc_from_table_fqn(table_fqn)

        for chk in checks_list:
            if not isinstance(chk, dict):
                continue
            um = chk.get("user_metadata") or {}
            args = (chk.get("check") or {}).get("arguments") or {}
            check_name = chk.get("name") or (args.get("name") if isinstance(args, dict) else None) or ""
            sev = "error" if chk.get("criticality") == "error" else "warning"
            expr = ""
            if isinstance(args, dict):
                expr = str(args.get("expression") or args.get("query") or "")[:300]
            # Structural metadata sourced from rc18_rule_meta (RC18 hard-codes
            # the 4 initial rules). User-authored Studio rules get safe defaults.
            meta = meta_for(check_name, table_fqn=table_fqn, user_metadata=um)
            doc = meta["document"] or doc_from_table
            description = um.get("descricao") or um.get("mensagem_erro") or args.get("msg") or check_name or ""
            out.append(CriticaRule(
                rule_id=meta["critica_id"] or check_name or r.get("rule_id") or "",
                document=doc,
                rule_type=meta["rule_type"],
                severity=sev,
                dimension_r18=meta["dimension_r18"],
                dimension_name=meta["dimension_name"],
                expression=expr,
                description=description,
                bcb_reference="",
                layout_version="V1" if doc == "3040" else ("V11" if doc == "3050" else ""),
            ))
    return out


_NIVEL_TO_RULE_TYPE = {
    "1": "syntactic",
    "2": "inter_document",
    "3": "business",
}


@router.get("/calendario", response_model=CalendarioResponse)
async def get_calendario(
    year: int = Query(2026),
    month: int | None = Query(None, ge=1, le=12),
):
    """Return BCB business day calendar."""
    if USE_MOCK:
        import calendar as cal
        days = []
        months_to_gen = [month] if month else list(range(1, 13))
        feriados = {
            "2026-01-01": "Confraternizacao Universal",
            "2026-02-16": "Carnaval", "2026-02-17": "Carnaval",
            "2026-04-03": "Sexta-feira Santa",
            "2026-04-21": "Tiradentes",
            "2026-05-01": "Dia do Trabalho",
            "2026-06-04": "Corpus Christi",
            "2026-09-07": "Independencia",
            "2026-10-12": "N.S. Aparecida",
            "2026-11-02": "Finados",
            "2026-11-15": "Proclamacao da Republica",
            "2026-12-25": "Natal",
        }
        total_du = 0
        total_feriados = 0
        for m in months_to_gen:
            for d in range(1, cal.monthrange(year, m)[1] + 1):
                dt_str = f"{year}-{m:02d}-{d:02d}"
                import datetime as dt_mod
                dt_obj = dt_mod.date(year, m, d)
                weekday = dt_obj.weekday()
                is_weekend = weekday >= 5
                feriado = feriados.get(dt_str)
                is_du = not is_weekend and feriado is None
                if is_du:
                    total_du += 1
                if feriado:
                    total_feriados += 1
                days.append(CalendarioDay(
                    date=dt_str, is_dia_util=is_du, is_ultimo_du_semana=False,
                    is_ultimo_du_mes=False, feriado=feriado,
                ))
        # Mark last business day of month
        for i in range(len(days) - 1, -1, -1):
            if days[i].is_dia_util:
                days[i].is_ultimo_du_mes = True
                break
        ultimo_du = next((d.date for d in reversed(days) if d.is_dia_util), "")
        return CalendarioResponse(
            year=year, month=month, days=days,
            summary=CalendarioSummary(total_dias_uteis=total_du, total_feriados=total_feriados, ultimo_du_mes=ultimo_du, semanas=[]),
        )

    rows = await execute_query(
        "SELECT data, is_dia_util, is_ultimo_du_semana, is_ultimo_du_mes, nm_feriado "
        f"FROM {CATALOG}.{SCHEMA_REFERENCE}.bcb_calendar "
        "WHERE ano = :year AND (:month IS NULL OR MONTH(data) = :month) ORDER BY data",
        {"year": year, "month": month},
    )
    days = [
        CalendarioDay(date=str(r["data"]), is_dia_util=r["is_dia_util"], is_ultimo_du_semana=r["is_ultimo_du_semana"], is_ultimo_du_mes=r["is_ultimo_du_mes"], feriado=r.get("nm_feriado"))
        for r in rows
    ]
    total_du = sum(1 for d in days if d.is_dia_util)
    total_fer = sum(1 for d in days if d.feriado)
    ultimo = next((d.date for d in reversed(days) if d.is_dia_util), "")
    return CalendarioResponse(year=year, month=month, days=days, summary=CalendarioSummary(total_dias_uteis=total_du, total_feriados=total_fer, ultimo_du_mes=ultimo, semanas=[]))


@router.get("/equivalencia", response_model=EquivalenciaResponse)
async def get_equivalencia(
    modality_3040: str | None = Query(None),
    category_3050: str | None = Query(None),
):
    """Return mapping between SCR 3040 modalities and SCR 3050 categories."""
    if USE_MOCK:
        mappings = [
            EquivalenciaMapping(modality_3040="0201", modality_3040_description="Emprestimos - Capital de giro ate 365 dias", category_3050="capitalDeGiro", category_3050_description="Capital de Giro", segment="pesJuridica", credit_type="crdLivre", periodicity="diario"),
            EquivalenciaMapping(modality_3040="0202", modality_3040_description="Emprestimos - Capital de giro acima 365 dias", category_3050="capitalDeGiro", category_3050_description="Capital de Giro", segment="pesJuridica", credit_type="crdLivre", periodicity="diario", special_rules="Considerar PF se tipo cliente for PJ"),
            EquivalenciaMapping(modality_3040="0204", modality_3040_description="Credito pessoal nao consignado", category_3050="crdPessoal", category_3050_description="Credito Pessoal", segment="pesFisica", credit_type="crdLivre", periodicity="diario"),
            EquivalenciaMapping(modality_3040="0301", modality_3040_description="Titulos descontados", category_3050="descDuplicatas", category_3050_description="Desconto de Duplicatas", segment="pesJuridica", credit_type="crdLivre", periodicity="diario"),
            EquivalenciaMapping(modality_3040="0401", modality_3040_description="Financiamento imobiliario - SFH", category_3050="aquisicaoImovel", category_3050_description="Aquisicao de Imovel", segment="pesFisica", credit_type="crdDirecionado", periodicity="mensal"),
        ]
        if modality_3040:
            mappings = [m for m in mappings if m.modality_3040 == modality_3040]
        if category_3050:
            mappings = [m for m in mappings if m.category_3050 == category_3050]
        return EquivalenciaResponse(version="2026-01", mappings=mappings)

    rows = await execute_query(
        "SELECT mod_3040, mod_3040_descricao, modalidade_3050, segmento_3050, encargo_3050, regra_especial "
        f"FROM {CATALOG}.{SCHEMA_REFERENCE}.modalidades_equivalencia "
        "WHERE (:mod_3040 IS NULL OR mod_3040 = :mod_3040) "
        "AND (:modalidade_3050 IS NULL OR modalidade_3050 = :modalidade_3050) ORDER BY mod_3040",
        {"mod_3040": modality_3040, "modalidade_3050": category_3050},
    )
    mappings = [
        EquivalenciaMapping(
            modality_3040=r["mod_3040"], modality_3040_description=r["mod_3040_descricao"],
            category_3050=r["modalidade_3050"], category_3050_description=r["modalidade_3050"],
            segment=r["segmento_3050"], credit_type="", periodicity="",
            special_rules=r.get("regra_especial"),
        )
        for r in rows
    ]
    return EquivalenciaResponse(version="2026-01", mappings=mappings)


@router.get("/dimensions", response_model=DimensionsResponse)
async def get_dimensions():
    """Return the 12 R.18 quality dimension definitions."""
    if USE_MOCK:
        return DimensionsResponse(dimensions=_MOCK_DIMENSIONS)

    rows = await execute_query(
        "SELECT dimensao_id, nome, definicao_regulatoria, artigo_r18, "
        "metrica_implementacao, meta_padrao_pct, capacidade_databricks "
        f"FROM {CATALOG}.{SCHEMA_REFERENCE}.dimensoes_r18 ORDER BY dimensao_id",
    )
    # `dimensao_id` is stored as a Roman numeral string (I..XII) in setup_reference_tables.
    # Map to int 1..12 for the DimensionDefinition.id field (which the App's frontend expects).
    _ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                     "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
    import unicodedata
    def _slug(s: str) -> str:
        # Strip accents → ASCII slug for the canonical dimension `code`.
        nfkd = unicodedata.normalize("NFKD", s or "")
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().replace(" ", "_")
    dims = [
        DimensionDefinition(
            id=_ROMAN_TO_INT.get(r["dimensao_id"], 0), code=_slug(r["nome"]),
            name=r["nome"], article=r.get("artigo_r18", ""),
            definition=r.get("definicao_regulatoria", ""), implementation=r.get("metrica_implementacao", ""),
            databricks_capability=r.get("capacidade_databricks", ""), metrics=[],
        )
        for r in rows
    ]
    return DimensionsResponse(dimensions=dims)
