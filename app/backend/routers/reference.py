"""Reference data endpoints: dominios, criticas, calendario, equivalencia, dimensions."""

from __future__ import annotations

from fastapi import APIRouter, Query

from db import CATALOG, USE_MOCK, execute_query
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

_MOCK_CRITICAS = [
    CriticaRule(rule_id="S10_001", document="3040", rule_type="syntactic", severity="error", dimension_r18=6, dimension_name="Completude", expression="DtContr IS NOT NULL", description="Campo DtContr (Data de Contratacao) e obrigatorio para todas as operacoes", bcb_reference="SCR3040_Criticas.xls, regra S10", layout_version="V11"),
    CriticaRule(rule_id="S10_002", document="3040", rule_type="syntactic", severity="error", dimension_r18=6, dimension_name="Conformidade", expression="LENGTH(CNPJ_IF) = 8", description="CNPJ da IF deve ter exatamente 8 digitos", bcb_reference="SCR3040_Criticas.xls, regra S10", layout_version="V11"),
    CriticaRule(rule_id="SEM_014", document="3040", rule_type="semantic", severity="error", dimension_r18=2, dimension_name="Acuracia", expression="IPOC components match operation fields", description="Componentes do IPOC devem corresponder aos campos da operacao", bcb_reference="SCR3040_Criticas.xls, regra SEM14", layout_version="V11"),
    CriticaRule(rule_id="SEM_020", document="3040", rule_type="semantic", severity="error", dimension_r18=8, dimension_name="Consistencia", expression="DtVencOp >= DtContr", description="Data de vencimento nao pode ser anterior a data de contratacao", bcb_reference="SCR3040_Criticas.xls, regra SEM20", layout_version="V11"),
    CriticaRule(rule_id="INT_001", document="3040", rule_type="inter_document", severity="warning", dimension_r18=8, dimension_name="Consistencia", expression="ABS(saldo_3040 - saldo_cosif) / saldo_cosif < 0.001", description="Saldo total SCR 3040 deve estar dentro de 0.1% do saldo COSIF", bcb_reference="Reconciliacao manual BCB", layout_version="V11"),
    CriticaRule(rule_id="CR1_001", document="3050", rule_type="syntactic", severity="error", dimension_r18=6, dimension_name="Completude", expression="encargo IS NOT NULL", description="Campo encargo obrigatorio para todas as concessoes TXB", bcb_reference="Criticas_TXB_V11.xlsx", layout_version="V11"),
    CriticaRule(rule_id="CR4_001", document="3050", rule_type="semantic", severity="error", dimension_r18=2, dimension_name="Acuracia", expression="valor_concessao > 0", description="Valor de concessao deve ser positivo", bcb_reference="Criticas_TXB_V11.xlsx", layout_version="V11"),
]

_MOCK_DIMENSIONS = [
    DimensionDefinition(id=1, code="acessibilidade", name="Acessibilidade", article="Art. 2, par.2, I", definition="Condicoes para obter informacoes, incluindo local, forma, prazos e tratamento PcD", implementation="Portal/sistema com SLA documentado; canais para demandas do BCB; catalogo acessivel a nao-tecnicos", databricks_capability="Unity Catalog (catalogo publico) + AI/BI Dashboards com ACLs por perfil", metrics=[DimensionMetricDef(code="sla_atendimento_pct", name="SLA de Atendimento", target=95.0, unit="%"), DimensionMetricDef(code="catalogo_cobertura_pct", name="Cobertura do Catalogo", target=100.0, unit="%")]),
    DimensionDefinition(id=2, code="acuracia", name="Acuracia", article="Art. 2, par.2, II", definition="Medida em que a informacao reflete a realidade de forma precisa", implementation="Validacao fonte primaria, reconciliacao pre-envio, monitoramento de rejeicoes BCB", databricks_capability="DLT Expectations + reconciliacao gold layer", metrics=[DimensionMetricDef(code="taxa_rejeicao_bcb_pct", name="Taxa de Rejeicao BCB", target=0.0, unit="%"), DimensionMetricDef(code="reconciliacao_pre_envio_pct", name="Reconciliacao Pre-Envio", target=99.5, unit="%")]),
    DimensionDefinition(id=3, code="atualidade", name="Atualidade", article="Art. 2, par.2, III", definition="Intervalo entre a ocorrencia e a disponibilizacao da informacao", implementation="CDC com baixa latencia, monitoramento de lag entre fonte e bronze", databricks_capability="Auto Loader + Lakeflow Connect CDC", metrics=[DimensionMetricDef(code="latencia_media_horas", name="Latencia Media", target=4.0, unit="horas")]),
    DimensionDefinition(id=4, code="completude", name="Completude", article="Art. 2, par.2, IV", definition="Abrangencia dos dados em relacao ao esperado", implementation="Contagem de campos obrigatorios preenchidos, cobertura de clientes/operacoes", databricks_capability="DLT Expectations (NOT NULL, completeness checks)", metrics=[DimensionMetricDef(code="campos_obrigatorios_pct", name="Campos Obrigatorios Preenchidos", target=100.0, unit="%")]),
    DimensionDefinition(id=5, code="confidencialidade", name="Confidencialidade", article="Art. 2, par.2, V", definition="Controle de acesso segundo autorizacoes e legislacao vigente", implementation="RBAC via Unity Catalog, audit logs, masking de dados sensiveis", databricks_capability="UC ACLs + Row/Column Level Security + Audit Logs", metrics=[DimensionMetricDef(code="acessos_nao_autorizados", name="Acessos Nao Autorizados", target=0.0, unit="count")]),
    DimensionDefinition(id=6, code="conformidade", name="Conformidade", article="Art. 2, par.2, VI", definition="Aderencia a regras, padroes e leiautes normativos", implementation="Validacao contra criticas BCB, dominos e XSD", databricks_capability="DLT Expectations parametrizadas com ref_criticas", metrics=[DimensionMetricDef(code="taxa_conformidade_pct", name="Taxa de Conformidade", target=100.0, unit="%")]),
    DimensionDefinition(id=7, code="confiabilidade", name="Confiabilidade", article="Art. 2, par.2, VII", definition="Nivel de confianca nos dados em funcao de processos e controles", implementation="SLAs de pipeline, monitoramento de falhas, testes automatizados", databricks_capability="DLT monitoring + Job alerts", metrics=[DimensionMetricDef(code="uptime_pipeline_pct", name="Uptime Pipeline", target=99.5, unit="%")]),
    DimensionDefinition(id=8, code="consistencia", name="Consistencia", article="Art. 2, par.2, VIII", definition="Coerencia entre dados de diferentes fontes e documentos", implementation="Reconciliacao 3040 vs 3050 vs COSIF vs sistemas internos", databricks_capability="Gold layer reconciliation tables + quality.reconciliation_results", metrics=[DimensionMetricDef(code="divergencia_maxima_pct", name="Divergencia Maxima", target=0.1, unit="%")]),
    DimensionDefinition(id=9, code="efetividade", name="Efetividade", article="Art. 2, par.2, IX", definition="Capacidade da informacao de produzir resultados pretendidos", implementation="Monitoramento de uso dos dados, KPIs de processo", databricks_capability="AI/BI Dashboards + usage tracking", metrics=[DimensionMetricDef(code="utilizacao_dados_pct", name="Utilizacao dos Dados", target=90.0, unit="%")]),
    DimensionDefinition(id=10, code="rastreabilidade", name="Rastreabilidade", article="Art. 2, par.2, X", definition="Capacidade de rastrear a origem, transformacoes e destino do dado", implementation="Lineage automatica UC + external lineage API (BYOL)", databricks_capability="UC System Tables (table_lineage, column_lineage) + External Lineage API", metrics=[DimensionMetricDef(code="cobertura_lineage_pct", name="Cobertura de Lineage", target=100.0, unit="%")]),
    DimensionDefinition(id=11, code="tempestividade", name="Tempestividade", article="Art. 2, par.2, XI", definition="Disponibilizacao dentro dos prazos estabelecidos", implementation="Monitoramento de prazos BCB, alertas de deadline", databricks_capability="BCB calendar + submission tracking", metrics=[DimensionMetricDef(code="envios_no_prazo_pct", name="Envios no Prazo", target=100.0, unit="%")]),
    DimensionDefinition(id=12, code="unicidade", name="Unicidade", article="Art. 2, par.2, XII", definition="Ausencia de registros duplicados ou redundantes", implementation="Dedup por _pk_hash, unicidade de IPOC + data-base", databricks_capability="DLT Expectations (DISTINCT checks) + dedup transformations", metrics=[DimensionMetricDef(code="taxa_duplicatas_pct", name="Taxa de Duplicatas", target=0.0, unit="%")]),
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
        f"FROM {CATALOG}.reference.ref_dominios "
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

    rows = await execute_query(
        "SELECT critica_id, documento, grupo, descricao, expressao_sql, "
        "campo_alvo, severidade, acao_dlt, dimensao_r18, artigo_r18, "
        "mensagem_erro, leiaute_versao, is_active "
        f"FROM {CATALOG}.reference.ref_criticas "
        "WHERE (:documento IS NULL OR documento = :documento) "
        "AND (:grupo IS NULL OR grupo = :grupo) "
        "AND (:severidade IS NULL OR severidade = :severidade) "
        "AND is_active = TRUE ORDER BY documento, critica_id",
        {"documento": document, "grupo": rule_type, "severidade": severity},
    )
    rules = [
        CriticaRule(
            rule_id=r["critica_id"], document=r["documento"], rule_type=r["grupo"],
            severity=r["severidade"], dimension_r18=r.get("dimensao_r18", 0), dimension_name="",
            expression=r.get("expressao_sql", ""), description=r["descricao"],
            bcb_reference="", layout_version=r.get("leiaute_versao", "V11"),
        )
        for r in rows
    ]
    return CriticasResponse(total=len(rules), rules=rules)


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
        f"FROM {CATALOG}.reference.ref_calendario_bcb "
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
        f"FROM {CATALOG}.reference.ref_equivalencia_modalidades "
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
        f"FROM {CATALOG}.reference.ref_dimensoes_r18 ORDER BY dimensao_id",
    )
    dims = [
        DimensionDefinition(
            id=r["dimensao_id"], code=r["nome"].lower().replace(" ", "_"),
            name=r["nome"], article=r.get("artigo_r18", ""),
            definition=r.get("definicao_regulatoria", ""), implementation=r.get("metrica_implementacao", ""),
            databricks_capability=r.get("capacidade_databricks", ""), metrics=[],
        )
        for r in rows
    ]
    return DimensionsResponse(dimensions=dims)
