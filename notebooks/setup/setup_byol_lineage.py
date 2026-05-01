# Databricks notebook source
# MAGIC %md
# MAGIC # RC18 — Bring Your Own Lineage (BYOL) Setup
# MAGIC
# MAGIC Registers all external lineage metadata with Unity Catalog using the
# MAGIC **External Metadata** and **External Lineage** APIs, giving end-to-end visibility of the
# MAGIC full SCR Doc 3040 / Doc 3050 pipeline — from source systems (Oracle Core Banking,
# MAGIC IBM DB2 Mainframe, Informatica ETL) through Databricks (Bronze → Silver → Gold) to
# MAGIC submission at BACEN's STA/CADIP system.
# MAGIC
# MAGIC ## Lineage topology
# MAGIC ```
# MAGIC Oracle TB_OPERACOES_CREDITO ─┐
# MAGIC Oracle TB_GARANTIAS         ─┤
# MAGIC Oracle TB_CONTRATANTES      ─┤─→ Informatica ETL SCR3040 ─→ bronze.raw_3040_doc
# MAGIC Oracle TB_CESSOES_FIDC      ─┤                               ↓ (DLT Silver/Gold auto)
# MAGIC DB2   CLIENTES_CREDITO      ─┘                          silver.operacoes_validadas
# MAGIC                                                               ↓
# MAGIC DB2   HISTORICO_SCR    ─┐                              gold.posicao_mensal_3040
# MAGIC DB2   PLANO_CONTAS_COSIF─┤─→ Informatica ETL SCR3050 ─→ bronze.raw_3050_doc      ─→ Validador3040 → STA/CADIP
# MAGIC                         ┘                          gold.posicao_3050 ─→ ValidadorMDR → STA/CADIP
# MAGIC ```
# MAGIC
# MAGIC ## Prerequisites
# MAGIC - User with `CREATE EXTERNAL METADATA` privilege on the metastore
# MAGIC - Run after `bundle deploy` and `setup_reference_tables`
# MAGIC
# MAGIC ## Idempotency
# MAGIC Deletes all existing `rc18_*` external metadata objects before recreating — safe to re-run.

# COMMAND ----------

dbutils.widgets.text("catalog",        "rc18_catalog", "Catalog")
dbutils.widgets.text("bronze_schema",  "bronze",        "Bronze Schema")
dbutils.widgets.text("silver_schema",  "silver",        "Silver Schema")
dbutils.widgets.text("gold_schema",    "gold",          "Gold Schema")

catalog       = dbutils.widgets.get("catalog")
bronze_schema = dbutils.widgets.get("bronze_schema")
silver_schema = dbutils.widgets.get("silver_schema")
gold_schema   = dbutils.widgets.get("gold_schema")

print(f"catalog={catalog}  bronze={bronze_schema}  silver={silver_schema}  gold={gold_schema}")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    ExternalMetadata,
    SystemType,
    CreateRequestExternalLineage,
    ExternalLineageObject,
    ExternalLineageExternalMetadata,
    ExternalLineageTable,
    ColumnRelationship,
    LineageDirection,
)

w = WorkspaceClient()
print(f"Connected to: {w.config.host}")


def fq(schema: str, table: str) -> str:
    return f"{catalog}.{schema}.{table}"


def ext_obj(name: str) -> ExternalLineageObject:
    return ExternalLineageObject(external_metadata=ExternalLineageExternalMetadata(name=name))


def uc_obj(schema: str, table: str) -> ExternalLineageObject:
    return ExternalLineageObject(table=ExternalLineageTable(name=fq(schema, table)))


def col(src: str, tgt: str) -> ColumnRelationship:
    return ColumnRelationship(source=src, target=tgt)

# COMMAND ----------

# MAGIC %md ## 1 — Teardown: remove existing rc18_* objects (idempotency)

# COMMAND ----------

existing = list(w.external_metadata.list_external_metadata())
to_delete = [m for m in existing if m.name and m.name.startswith("rc18_")]
for m in to_delete:
    try:
        w.external_metadata.delete_external_metadata(m.name)
        print(f"  Deleted: {m.name}")
    except Exception as e:
        print(f"  Warning — could not delete {m.name}: {e}")
print(f"Removed {len(to_delete)} existing rc18_* objects")

# COMMAND ----------

# MAGIC %md ## 2 — Create External Metadata Objects

# COMMAND ----------

OBJECTS = [
    # ── Oracle Core Banking ────────────────────────────────────────────────
    ExternalMetadata(
        name="rc18_oracle_tb_operacoes_credito",
        system_type=SystemType.ORACLE,
        entity_type="TABLE",
        description=(
            "Principal tabela de operacoes de credito no Core Banking Oracle. "
            "Contem 130+ campos por operacao incluindo IPOC, modalidade, valor contabil, "
            "vencimento e classificacao de risco — fonte primaria do SCR Doc 3040."
        ),
        url="jdbc:oracle:thin:@core-banking-prod.bancorp.internal:1521/CREDITO",
        columns=[
            "CD_CNPJ_IF", "CD_MODALIDADE", "TP_CLIENTE", "CD_CLIENTE",
            "NR_CONTRATO", "CD_IPOC", "VLR_CONTABIL_BRL", "VLR_PROVISIONADO_BRL",
            "DT_CONTRATACAO", "DT_VENCIMENTO", "CD_TIPO_RISCO", "CD_FASE_COBRANCA",
            "CD_CONTA_COSIF", "VLR_ENCARGO_FINANCEIRO", "NR_PRESTACOES",
            "CD_INDEXADOR", "PC_TAXA_JUROS", "VLR_LIMITE_CREDITO",
        ],
        properties={
            "source_system":      "Oracle 19c — Core Banking",
            "update_mode":        "CDC via ROWSCN — incremental a cada 15 min",
            "volume_daily_rows":  "~4.2M novas operacoes/dia",
            "r18_sensitivity":    "ALTO — dado regulatorio primario SCR 3040",
            "data_owner":         "Diretoria de Credito",
            "retention_years":    "5",
        },
    ),
    ExternalMetadata(
        name="rc18_oracle_tb_garantias",
        system_type=SystemType.ORACLE,
        entity_type="TABLE",
        description=(
            "Tabela de garantias e colaterais das operacoes de credito. "
            "Vinculada a TB_OPERACOES_CREDITO via CD_IPOC. "
            "Alimenta a secao de garantias do SCR Doc 3040."
        ),
        url="jdbc:oracle:thin:@core-banking-prod.bancorp.internal:1521/CREDITO",
        columns=[
            "CD_IPOC", "CD_SEQ_GARANTIA", "CD_TIPO_GARANTIA", "VLR_GARANTIA",
            "VLR_EXCUTAVEL", "CD_EMISSOR", "DT_VENCIMENTO_GAR", "CD_MOEDA", "CD_PAIS",
        ],
        properties={
            "source_system":   "Oracle 19c — Core Banking",
            "update_mode":     "CDC via ROWSCN",
            "r18_sensitivity": "ALTO — garantias obrigatorias no SCR 3040",
        },
    ),
    ExternalMetadata(
        name="rc18_oracle_tb_contratantes",
        system_type=SystemType.ORACLE,
        entity_type="TABLE",
        description=(
            "Cadastro de contratantes (clientes tomadores de credito). "
            "Prove dados de identificacao (CNPJ/CPF), porte e segmento "
            "para composicao do IPOC e classificacao no SCR 3040."
        ),
        url="jdbc:oracle:thin:@core-banking-prod.bancorp.internal:1521/CREDITO",
        columns=[
            "TP_CLIENTE", "CD_CLIENTE", "NM_CLIENTE", "CD_CNPJ_CPF",
            "CD_SEG_PORTE", "CD_ATIVIDADE_ECON", "DT_NASCIMENTO_ABERTURA",
            "CD_MUNICIPIO", "CD_PAIS_RESIDENCIA",
        ],
        properties={
            "source_system":   "Oracle 19c — Core Banking",
            "update_mode":     "Batch diario 02h00",
            "r18_sensitivity": "ALTO — identificacao obrigatoria no SCR 3040",
        },
    ),
    ExternalMetadata(
        name="rc18_oracle_tb_cessoes_fidc",
        system_type=SystemType.ORACLE,
        entity_type="TABLE",
        description=(
            "Registros de cessao de credito para FIDCs. "
            "Obrigatorio no SCR 3040 para operacoes cedidas — "
            "inclui cedente, cessionario e valor de cessao."
        ),
        url="jdbc:oracle:thin:@core-banking-prod.bancorp.internal:1521/CREDITO",
        columns=[
            "CD_IPOC", "DT_CESSAO", "VLR_CESSAO",
            "CD_CNPJ_CEDENTE", "CD_CNPJ_CESSIONARIO", "CD_TIPO_CESSAO", "IN_COOBRIGACAO",
        ],
        properties={
            "source_system":   "Oracle 19c — Core Banking",
            "update_mode":     "Batch mensal D-1",
            "r18_sensitivity": "MEDIO — cessoes FIDC reportaveis no SCR",
        },
    ),
    # ── IBM DB2 Mainframe ──────────────────────────────────────────────────
    ExternalMetadata(
        name="rc18_db2_clientes_credito",
        system_type=SystemType.OTHER,
        entity_type="TABLE",
        description=(
            "Cadastro mestre de clientes de credito no mainframe IBM DB2. "
            "Sistema legado com historico de clientes PF e PJ — "
            "complementa TB_CONTRATANTES com dados historicos e de agencia."
        ),
        url="jdbc:db2://mainframe.bancorp.internal:50000/CLICRED",
        columns=[
            "CD_CLIENTE", "NM_CLIENTE", "CD_CNPJ_CPF", "DT_NASCIMENTO",
            "CD_AGENCIA", "CD_GERENTE", "CD_CATEGORIA", "DT_PRIMEIRO_CREDITO",
            "VLR_LIMITE_TOTAL", "CD_SCORING",
        ],
        properties={
            "source_system":    "IBM DB2 z/OS — Mainframe",
            "update_mode":      "Batch noturno 00h30 — carga incremental",
            "volume_records":   "~12M clientes ativos",
            "r18_sensitivity":  "MEDIO — dados cadastrais complementares",
            "data_owner":       "Diretoria de TI — Sistemas Legados",
        },
    ),
    ExternalMetadata(
        name="rc18_db2_historico_scr",
        system_type=SystemType.OTHER,
        entity_type="TABLE",
        description=(
            "Historico de posicoes SCR enviadas ao BCB nos ultimos 60 meses. "
            "Armazena posicoes agregadas (Doc 3050) usadas como base para a "
            "geracao do arquivo corrente."
        ),
        url="jdbc:db2://mainframe.bancorp.internal:50000/HSCR",
        columns=[
            "CD_CNPJ_IF", "CD_PERIODO", "CD_MODALIDADE", "VLR_CARTEIRA",
            "VLR_INADIMPLENCIA", "CD_QUALIDADE", "NR_OPERACOES",
            "DT_ENVIO_BCB", "IN_REPROCESSADO",
        ],
        properties={
            "source_system":   "IBM DB2 z/OS — Mainframe",
            "update_mode":     "Atualizado apos cada envio BCB (semanal/mensal)",
            "r18_sensitivity": "ALTO — fonte historica obrigatoria para 3050",
        },
    ),
    ExternalMetadata(
        name="rc18_db2_plano_contas_cosif",
        system_type=SystemType.OTHER,
        entity_type="TABLE",
        description=(
            "Plano de Contas do Sistema Financeiro Nacional (COSIF) conforme BCB. "
            "Mapeamento de contas contabeis para modalidades SCR — usado para "
            "derivar CD_CONTA_COSIF no Doc 3040 e agregar por COSIF no Doc 3050."
        ),
        url="jdbc:db2://mainframe.bancorp.internal:50000/COSIF",
        columns=["CD_CONTA_COSIF", "DS_CONTA", "CD_GRUPO", "CD_SUBGRUPO", "CD_NATUREZA", "DT_VIGENCIA"],
        properties={
            "source_system":   "IBM DB2 z/OS — Mainframe",
            "update_mode":     "Atualizado a cada publicacao BACEN do COSIF",
            "r18_sensitivity": "ALTO — mapeamento regulatorio obrigatorio",
        },
    ),
    # ── ETL Processes ─────────────────────────────────────────────────────
    ExternalMetadata(
        name="rc18_etl_scr3040_extractor",
        system_type=SystemType.OTHER,
        entity_type="PROCESS",
        description=(
            "Job Informatica PowerCenter que extrai operacoes de credito das fontes "
            "Oracle e DB2 e gera XMLs Doc 3040 conformes com o layout BACEN. "
            "Executa validacao sintatica antes de depositar os arquivos no volume "
            "landing do Databricks (scr_xml/3040/)."
        ),
        url="https://etl-prod.bancorp.internal/powercenter/repository/RC18_SCR3040_EXTRACT",
        columns=[
            "ipoc", "modalidade", "tipo_cliente", "cnpj_if", "vlr_contabil",
            "vlr_provisionado", "dt_contratacao", "dt_vencimento", "tipo_risco",
            "cod_fase_cobranca", "cnt_garantias", "cnt_cessoes",
        ],
        properties={
            "tool":              "Informatica PowerCenter 10.5",
            "schedule":          "Diario 22h00 — janela batch noturna",
            "sla_completion":    "02h00 D+1",
            "output_format":     "XML conforme layout BACEN SCR Doc 3040",
            "output_volume":     f"dbfs:/Volumes/{catalog}/landing/scr_xml/3040/",
            "avg_files_per_run": "~850 arquivos XML / execucao mensal",
            "r18_role":          "Extracao e transformacao pre-Databricks para SCR 3040",
            "contact":           "squad-dados-regulatorios@bancorp.internal",
        },
    ),
    ExternalMetadata(
        name="rc18_etl_scr3050_aggregator",
        system_type=SystemType.OTHER,
        entity_type="PROCESS",
        description=(
            "Job Informatica PowerCenter que agrega posicoes de carteira a partir "
            "do historico SCR (DB2) e do plano de contas COSIF, gerando arquivos "
            "TXB/XML do Doc 3050. Executa equivalencias 3040 <-> 3050 e deposita "
            "em scr_xml/3050/."
        ),
        url="https://etl-prod.bancorp.internal/powercenter/repository/RC18_SCR3050_AGG",
        columns=["cnpj_if", "periodo", "modalidade", "vlr_carteira", "vlr_inadimplencia", "cnt_operacoes", "qualidade", "cosif"],
        properties={
            "tool":          "Informatica PowerCenter 10.5",
            "schedule":      "Semanal (sexta 23h00) e mensal (D-1 calendario BCB)",
            "sla_completion":"04h00 do dia de envio BCB",
            "output_format": "TXB/XML V11 conforme layout BACEN SCR Doc 3050",
            "output_volume": f"dbfs:/Volumes/{catalog}/landing/scr_xml/3050/",
            "r18_role":      "Agregacao pre-Databricks para SCR 3050",
            "contact":       "squad-dados-regulatorios@bancorp.internal",
        },
    ),
    # ── BACEN Validators ──────────────────────────────────────────────────
    ExternalMetadata(
        name="rc18_bacen_validador_scr3040",
        system_type=SystemType.OTHER,
        entity_type="PROCESS",
        description=(
            "Validador oficial BACEN para SCR Doc 3040 (Validador3040). "
            "Aplica criticas sintaticas, semanticas e inter-documentais conforme "
            "Manual de Criticas BCB. Resultado auditado pelo Databricks em "
            "silver.criticas_results."
        ),
        url="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040",
        columns=["arquivo_xml", "resultado", "cnt_criticas", "criticas_detalhes", "dt_validacao", "versao_validador"],
        properties={
            "tool":           "Validador3040 — ferramenta oficial BCB",
            "critical_pass":  "mandatorio — arquivo rejeitado se qualquer critica ERRO",
            "r18_compliance": "Validacao obrigatoria antes de envio ao STA/CADIP",
        },
    ),
    ExternalMetadata(
        name="rc18_bacen_validador_scr3050",
        system_type=SystemType.OTHER,
        entity_type="PROCESS",
        description=(
            "Validador oficial BACEN para SCR Doc 3050 (ValidadorMDR). "
            "Valida arquivos TXB/XML V11 contra XSD oficial e aplica criticas de "
            "integridade e equivalencia 3040 <-> 3050."
        ),
        url="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3050",
        columns=["arquivo_txb", "resultado", "cnt_erros", "cnt_alertas", "dt_validacao", "versao_xsd"],
        properties={
            "tool":           "ValidadorMDR — ferramenta oficial BCB",
            "version":        "TXB V11 / Schema_TXB_V11.xsd",
            "r18_compliance": "Validacao obrigatoria antes de envio ao STA/CADIP",
        },
    ),
    # ── STA / CADIP ───────────────────────────────────────────────────────
    ExternalMetadata(
        name="rc18_sta_cadip_doc3040",
        system_type=SystemType.OTHER,
        entity_type="DATASET",
        description=(
            "Dataset de submissao do SCR Doc 3040 no sistema STA/CADIP do BACEN. "
            "Representa o conjunto de XMLs validados e transmitidos para o BCB "
            "conforme calendario de envio. Destino final da cadeia R.18 para operacoes detalhadas."
        ),
        url="https://www.bcb.gov.br/acessoinformacao/legenda_sistemas_informacoes#STA",
        columns=["cd_protocolo_bcb", "dt_envio", "dt_competencia", "cnt_arquivos", "vlr_total_carteira", "status_processamento_bcb"],
        properties={
            "system":         "STA — Sistema de Transferencia de Arquivos BCB",
            "channel":        "CADIP — Coleta Automatizada de Dados de Instituicoes",
            "frequency":      "Mensal — ate D util especificado no calendario BCB",
            "r18_compliance": "Destino final obrigatorio SCR Doc 3040",
            "retention":      "5 anos — exigencia R.18 Art. 6",
        },
    ),
    ExternalMetadata(
        name="rc18_sta_cadip_doc3050",
        system_type=SystemType.OTHER,
        entity_type="DATASET",
        description=(
            "Dataset de submissao do SCR Doc 3050 no sistema STA/CADIP do BACEN. "
            "Representa os arquivos TXB/XML V11 validados e transmitidos "
            "para posicoes agregadas de carteira. Destino final da cadeia R.18."
        ),
        url="https://www.bcb.gov.br/acessoinformacao/legenda_sistemas_informacoes#STA",
        columns=["cd_protocolo_bcb", "dt_envio", "dt_competencia", "cnt_registros", "vlr_carteira_total", "status_processamento_bcb"],
        properties={
            "system":         "STA — Sistema de Transferencia de Arquivos BCB",
            "channel":        "CADIP — Coleta Automatizada de Dados de Instituicoes",
            "frequency":      "Semanal e mensal — calendario BCB D util",
            "r18_compliance": "Destino final obrigatorio SCR Doc 3050",
            "retention":      "5 anos — exigencia R.18 Art. 6",
        },
    ),
]

created = []
for obj in OBJECTS:
    try:
        result = w.external_metadata.create_external_metadata(obj)
        created.append(result.name)
        print(f"  OK  {result.name}  ({obj.system_type.value}, {obj.entity_type})")
    except Exception as e:
        print(f"  ERR {obj.name}: {e}")

print(f"\nCreated {len(created)}/{len(OBJECTS)} external metadata objects")

# COMMAND ----------

# MAGIC %md ## 3 — Create External Lineage Relationships

# COMMAND ----------

RELATIONSHIPS = [
    # Oracle sources -> Informatica SCR3040 extractor
    dict(
        source=ext_obj("rc18_oracle_tb_operacoes_credito"),
        target=ext_obj("rc18_etl_scr3040_extractor"),
        columns=[
            col("CD_CNPJ_IF",        "cnpj_if"),
            col("CD_MODALIDADE",     "modalidade"),
            col("TP_CLIENTE",        "tipo_cliente"),
            col("CD_CLIENTE",        "cd_cliente"),
            col("NR_CONTRATO",       "nr_contrato"),
            col("CD_IPOC",           "ipoc"),
            col("VLR_CONTABIL_BRL",  "vlr_contabil"),
            col("VLR_PROVISIONADO_BRL","vlr_provisionado"),
            col("DT_CONTRATACAO",    "dt_contratacao"),
            col("DT_VENCIMENTO",     "dt_vencimento"),
            col("CD_TIPO_RISCO",     "tipo_risco"),
            col("CD_CONTA_COSIF",    "cod_conta_cosif"),
        ],
        properties={"transform": "CDC extract + XML serialization — Informatica mapping m_OP_CREDITO_TO_3040"},
    ),
    dict(
        source=ext_obj("rc18_oracle_tb_garantias"),
        target=ext_obj("rc18_etl_scr3040_extractor"),
        columns=[
            col("CD_IPOC",          "ipoc"),
            col("CD_SEQ_GARANTIA",  "seq_garantia"),
            col("CD_TIPO_GARANTIA", "tipo_garantia"),
            col("VLR_GARANTIA",     "vlr_garantia"),
            col("VLR_EXCUTAVEL",    "vlr_executavel"),
        ],
        properties={"transform": "JOIN com TB_OPERACOES via CD_IPOC"},
    ),
    dict(
        source=ext_obj("rc18_oracle_tb_contratantes"),
        target=ext_obj("rc18_etl_scr3040_extractor"),
        columns=[
            col("TP_CLIENTE",        "tipo_cliente"),
            col("CD_CLIENTE",        "cd_cliente"),
            col("CD_CNPJ_CPF",       "cnpj_cpf"),
            col("CD_SEG_PORTE",      "seg_porte"),
            col("CD_ATIVIDADE_ECON", "atividade_econ"),
        ],
        properties={"transform": "Lookup para enriquecer campo contratante no Doc 3040"},
    ),
    dict(
        source=ext_obj("rc18_oracle_tb_cessoes_fidc"),
        target=ext_obj("rc18_etl_scr3040_extractor"),
        columns=[
            col("CD_IPOC",              "ipoc"),
            col("DT_CESSAO",            "dt_cessao"),
            col("VLR_CESSAO",           "vlr_cessao"),
            col("CD_CNPJ_CEDENTE",      "cnpj_cedente"),
            col("CD_CNPJ_CESSIONARIO",  "cnpj_cessionario"),
        ],
        properties={"transform": "LEFT JOIN — somente operacoes cedidas tem registro"},
    ),
    dict(
        source=ext_obj("rc18_db2_clientes_credito"),
        target=ext_obj("rc18_etl_scr3040_extractor"),
        columns=[
            col("CD_CLIENTE", "cd_cliente"),
            col("CD_AGENCIA", "cd_agencia"),
            col("CD_SCORING", "cd_scoring"),
        ],
        properties={"transform": "Lookup DB2 via DRDA bridge — complementa cadastro Oracle"},
    ),
    # DB2 sources -> Informatica SCR3050 aggregator
    dict(
        source=ext_obj("rc18_db2_historico_scr"),
        target=ext_obj("rc18_etl_scr3050_aggregator"),
        columns=[
            col("CD_CNPJ_IF",       "cnpj_if"),
            col("CD_PERIODO",       "periodo"),
            col("CD_MODALIDADE",    "modalidade"),
            col("VLR_CARTEIRA",     "vlr_carteira"),
            col("VLR_INADIMPLENCIA","vlr_inadimplencia"),
            col("CD_QUALIDADE",     "qualidade"),
            col("NR_OPERACOES",     "cnt_operacoes"),
        ],
        properties={"transform": "Agregacao mensal por modalidade COSIF — agg_3050"},
    ),
    dict(
        source=ext_obj("rc18_db2_plano_contas_cosif"),
        target=ext_obj("rc18_etl_scr3050_aggregator"),
        columns=[
            col("CD_CONTA_COSIF", "cosif"),
            col("CD_GRUPO",       "grupo_cosif"),
            col("CD_NATUREZA",    "natureza"),
        ],
        properties={"transform": "Lookup COSIF para derivacao de modalidade 3050"},
    ),
    # Informatica ETL -> Databricks Bronze (the key BYOL boundary)
    dict(
        source=ext_obj("rc18_etl_scr3040_extractor"),
        target=uc_obj(bronze_schema, "raw_3040_doc"),
        columns=[
            col("ipoc",         "header.CD_IPOC"),
            col("cnpj_if",      "header.CD_CNPJ_IF"),
            col("modalidade",   "header.CD_MODALIDADE"),
            col("vlr_contabil", "operacoes[0].VLR_CONTABIL"),
            col("tipo_risco",   "operacoes[0].TP_RISCO"),
            col("vlr_garantia", "garantias[0].VLR_GARANTIA"),
        ],
        properties={
            "mechanism":    "XML drop ao volume landing -> Auto Loader (cloudFiles) -> Delta table",
            "trigger":      "Triggered streaming — batch diario apos ETL",
            "r18_boundary": "ENTRADA Databricks — ponto de controle de qualidade R.18",
        },
    ),
    dict(
        source=ext_obj("rc18_etl_scr3050_aggregator"),
        target=uc_obj(bronze_schema, "raw_3050_doc"),
        columns=[
            col("cnpj_if",      "header.CD_CNPJ_IF"),
            col("periodo",      "header.DT_REFERENCIA"),
            col("modalidade",   "registros[0].MODALIDADE"),
            col("vlr_carteira", "registros[0].VLR_CARTEIRA"),
            col("cosif",        "registros[0].CD_CONTA_COSIF"),
        ],
        properties={
            "mechanism":    "TXB/XML drop -> Auto Loader (binaryFile+lxml UDF) -> Delta",
            "trigger":      "Triggered streaming — batch semanal/mensal apos ETL",
            "r18_boundary": "ENTRADA Databricks — ponto de controle de qualidade R.18",
        },
    ),
    # Databricks Gold -> BACEN Validators (the other BYOL boundary)
    dict(
        source=uc_obj(gold_schema, "posicao_mensal_3040"),
        target=ext_obj("rc18_bacen_validador_scr3040"),
        columns=[
            col("cnpj_if",       "CD_CNPJ_IF"),
            col("ipoc",          "CD_IPOC"),
            col("modalidade",    "CD_MODALIDADE"),
            col("vlr_contabil",  "VLR_CONTABIL"),
        ],
        properties={
            "mechanism":    "Exportacao XML a partir de Gold -> Validador3040",
            "quality_gate": "Apenas registros com criticas_results.resultado=APROVADO exportados",
            "r18_boundary": "SAIDA Databricks — validacao regulatoria pre-envio BACEN",
        },
    ),
    dict(
        source=uc_obj(gold_schema, "posicao_3050"),
        target=ext_obj("rc18_bacen_validador_scr3050"),
        columns=[
            col("cnpj_if",      "CD_CNPJ_IF"),
            col("periodo",      "DT_REFERENCIA"),
            col("modalidade",   "MODALIDADE"),
            col("vlr_carteira", "VLR_CARTEIRA"),
        ],
        properties={
            "mechanism":    "Exportacao TXB/XML a partir de Gold -> ValidadorMDR",
            "quality_gate": "quality_scorecard.pct_conforme >= 95% obrigatorio",
            "r18_boundary": "SAIDA Databricks — validacao regulatoria pre-envio BACEN",
        },
    ),
    # BACEN Validators -> STA/CADIP (final delivery)
    dict(
        source=ext_obj("rc18_bacen_validador_scr3040"),
        target=ext_obj("rc18_sta_cadip_doc3040"),
        properties={
            "mechanism":     "SFTP/HTTPS transmissao para portal STA BCB",
            "precondition":  "Zero criticas de ERRO no Validador3040",
            "r18_compliance":"Submissao final obrigatoria — prazo calendario BCB",
        },
    ),
    dict(
        source=ext_obj("rc18_bacen_validador_scr3050"),
        target=ext_obj("rc18_sta_cadip_doc3050"),
        properties={
            "mechanism":     "SFTP/HTTPS transmissao para portal STA BCB",
            "precondition":  "Zero criticas de ERRO no ValidadorMDR",
            "r18_compliance":"Submissao final obrigatoria — prazo calendario BCB",
        },
    ),
]

created_rels = []
for i, rel in enumerate(RELATIONSHIPS):
    req = CreateRequestExternalLineage(
        source=rel["source"],
        target=rel["target"],
        columns=rel.get("columns"),
        properties=rel.get("properties"),
    )
    try:
        result = w.external_lineage.create_external_lineage_relationship(req)
        created_rels.append(result.id)
        src = (rel["source"].external_metadata.name if rel["source"].external_metadata
               else rel["source"].table.name)
        tgt = (rel["target"].external_metadata.name if rel["target"].external_metadata
               else rel["target"].table.name)
        print(f"  OK  {src}  ->  {tgt}")
    except Exception as e:
        print(f"  ERR relationship {i+1}: {e}")

print(f"\nCreated {len(created_rels)}/{len(RELATIONSHIPS)} lineage relationships")

# COMMAND ----------

# MAGIC %md ## 4 — Verify

# COMMAND ----------

print("External metadata objects (rc18_*):")
all_meta = list(w.external_metadata.list_external_metadata())
rc18 = sorted([m for m in all_meta if m.name and m.name.startswith("rc18_")], key=lambda x: x.name)
for m in rc18:
    print(f"  {m.name:48s}  {m.system_type.value if m.system_type else 'n/a':20s}  {m.entity_type}")

print(f"\nTotal: {len(rc18)} objects")

# COMMAND ----------

print("\nLineage relationships for bronze/gold tables:")
for schema, table in [
    (bronze_schema, "raw_3040_doc"),
    (bronze_schema, "raw_3050_doc"),
    (gold_schema,   "posicao_mensal_3040"),
    (gold_schema,   "posicao_3050"),
]:
    obj = ExternalLineageObject(table=ExternalLineageTable(name=fq(schema, table)))
    try:
        up   = list(w.external_lineage.list_external_lineage_relationships(obj, LineageDirection.UPSTREAM))
        down = list(w.external_lineage.list_external_lineage_relationships(obj, LineageDirection.DOWNSTREAM))
        print(f"  {fq(schema, table)}: {len(up)} upstream / {len(down)} downstream BYOL edges")
    except Exception as e:
        print(f"  {fq(schema, table)}: {e}")

print("\nBYOL setup complete. Open the RC18 app > Lineage to see the end-to-end graph.")
