# Databricks notebook source
# MAGIC %md
# MAGIC # Setup Reference Tables
# MAGIC Seeds all reference tables in `<catalog>.reference` with BCB domain data, validation
# MAGIC rules, calendar, modality equivalence, dimension definitions, and layout versions.
# MAGIC Run ONCE after catalog/schema creation.
# MAGIC
# MAGIC Override the target catalog by setting the `catalog` widget or
# MAGIC `spark.conf.set("catalog", "<your_catalog>")` before running.

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Reference Schema")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Domínios (Valid Domain Values)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.dominios (
    dominio_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    documento STRING NOT NULL,
    campo STRING NOT NULL,
    valor_codigo STRING NOT NULL,
    valor_descricao STRING NOT NULL,
    anexo_referencia STRING,
    leiaute_versao STRING NOT NULL,
    dt_vigencia_ini DATE NOT NULL,
    dt_vigencia_fim DATE,
    is_current BOOLEAN NOT NULL,
    observacoes STRING
)
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# Insert key domain values
spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.dominios (documento, campo, valor_codigo, valor_descricao, anexo_referencia, leiaute_versao, dt_vigencia_ini, is_current)
VALUES
  ('3040', 'TpCli', '1', 'CPF (Pessoa Física)', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCli', '2', 'CNPJ base (8 dígitos)', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCli', '3', 'CEI', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCli', '4', 'Não residente', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCli', '5', 'CNPJ completo (14 dígitos)', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCli', '6', 'Código BCB', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'NatuOp', '01', 'Normal (titular)', 'Anexo 2', 'V1', '2000-01-01', true),
  ('3040', 'NatuOp', '04', 'Cessionária', 'Anexo 2', 'V1', '2000-01-01', true),
  ('3040', 'NatuOp', '11', 'Cedente com coobrigação', 'Anexo 2', 'V1', '2000-01-01', true),
  ('3040', 'NatuOp', '12', 'Cedente sem coobrigação', 'Anexo 2', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0101', 'Adiantamento a depositantes', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0201', 'Empréstimos - Capital de giro até 365 dias', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0202', 'Empréstimos - Capital de giro acima 365 dias', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0204', 'Empréstimos - Crédito pessoal não consignado', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0301', 'Títulos descontados', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0401', 'Financiamento imobiliário - SFH', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'Mod', '0402', 'Financiamento imobiliário - SFI', 'Anexo 3', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'AA', 'Risco mínimo', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'A', 'Risco muito baixo', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'B', 'Risco baixo', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'C', 'Risco médio-baixo', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'D', 'Risco médio', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'E', 'Risco médio-alto', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'F', 'Risco alto', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'G', 'Risco muito alto', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3040', 'ClassOp', 'H', 'Risco máximo (perda)', 'Anexo 5', 'V1', '2000-01-01', true),
  ('3050', 'encargo', 'pre', 'Prefixado', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'flu', 'Pós-fixado flutuante', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'vc', 'Variação cambial', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'ipca', 'IPCA', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'igpm', 'IGP-M', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'ind', 'Indexador genérico', NULL, 'V11', '2025-11-07', true),
  ('3050', 'segmento', 'pesJuridica', 'Pessoa Jurídica', NULL, 'V11', '2025-11-07', true),
  ('3050', 'segmento', 'pesFisica', 'Pessoa Física', NULL, 'V11', '2025-11-07', true)
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Validation Rules (Críticas)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.validation_rules (
    critica_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    critica_id STRING NOT NULL,
    documento STRING NOT NULL,
    leiaute_versao STRING NOT NULL,
    grupo STRING,
    descricao STRING NOT NULL,
    expressao_sql STRING NOT NULL,
    campo_alvo STRING,
    severidade STRING NOT NULL,
    acao_dlt STRING NOT NULL,
    dimensao_r18 STRING,
    artigo_r18 STRING,
    mensagem_erro STRING,
    dt_vigencia_ini DATE NOT NULL,
    dt_vigencia_fim DATE,
    is_active BOOLEAN NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# Tabela `validation_rules` mantida apenas como esqueleto: as regras DQX
# canônicas vivem em `${catalog}.quality.dqx_checks`, semeada pelo job
# `seed_dqx_checks` a partir de `pipelines/silver/dqx_checks/*.yml`. Novas
# regras devem ser criadas via DQX Studio (Motor de Regras). O CREATE acima é
# preservado para compatibilidade com dashboards/notebooks legados.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. BCB Calendar (2025-2030)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.bcb_calendar (
    data DATE NOT NULL,
    is_dia_util BOOLEAN NOT NULL,
    is_feriado_nacional BOOLEAN NOT NULL,
    is_ponto_facultativo BOOLEAN NOT NULL,
    nm_feriado STRING,
    is_primeiro_du_mes BOOLEAN NOT NULL,
    is_ultimo_du_mes BOOLEAN NOT NULL,
    is_ultimo_du_semana BOOLEAN NOT NULL,
    semana_bcb_num INT,
    dt_base_semanal DATE,
    dias_corridos_ate_fim_mes INT,
    prazo_envio_3050 DATE,
    ano INT NOT NULL
)
PARTITIONED BY (ano)
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# Generate calendar using PySpark (2025-2030)
from pyspark.sql import functions as F
from pyspark.sql.types import DateType
import datetime

start = datetime.date(2025, 1, 1)
end = datetime.date(2030, 12, 31)
dates = []
d = start
while d <= end:
    dates.append((d,))
    d += datetime.timedelta(days=1)

cal_df = spark.createDataFrame(dates, ["data"])

# Brazilian national holidays (approximate — complete list should be loaded from BCB)
feriados_fixos = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (12, 25): "Natal",
}

cal_enriched = (
    cal_df
    .withColumn("ano", F.year("data"))
    .withColumn("mes", F.month("data"))
    .withColumn("dia", F.dayofmonth("data"))
    .withColumn("dow", F.dayofweek("data"))  # 1=Sunday, 7=Saturday
    .withColumn("is_weekend", (F.col("dow") == 1) | (F.col("dow") == 7))
    .withColumn("is_feriado_nacional", F.lit(False))  # Simplified; real implementation checks lookup
    .withColumn("is_ponto_facultativo", F.lit(False))
    .withColumn("nm_feriado", F.lit(None).cast("string"))
    .withColumn("is_dia_util", ~F.col("is_weekend") & ~F.col("is_feriado_nacional"))
    .withColumn("is_primeiro_du_mes", F.lit(False))
    .withColumn("is_ultimo_du_mes", F.lit(False))
    .withColumn("is_ultimo_du_semana", F.lit(False))
    .withColumn("semana_bcb_num", F.weekofyear("data"))
    .withColumn("dt_base_semanal", F.lit(None).cast("date"))
    .withColumn("dias_corridos_ate_fim_mes", F.datediff(F.last_day("data"), F.col("data")))
    .withColumn("prazo_envio_3050", F.lit(None).cast("date"))
    .select(
        "data", "is_dia_util", "is_feriado_nacional", "is_ponto_facultativo", "nm_feriado",
        "is_primeiro_du_mes", "is_ultimo_du_mes", "is_ultimo_du_semana",
        "semana_bcb_num", "dt_base_semanal", "dias_corridos_ate_fim_mes", "prazo_envio_3050", "ano",
    )
)

cal_enriched.write.mode("overwrite").insertInto(f"{CATALOG}.{SCHEMA}.bcb_calendar")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Modalidades Equivalência (3040 ↔ 3050)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.modalidades_equivalencia (
    equiv_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    mod_3040 STRING NOT NULL,
    mod_3040_descricao STRING NOT NULL,
    modalidade_3050 STRING NOT NULL,
    segmento_3050 STRING NOT NULL,
    encargo_3050 STRING,
    regra_especial STRING,
    tem_regra_especial BOOLEAN NOT NULL,
    submod_0202_pf_se_pj BOOLEAN NOT NULL DEFAULT false,
    submod_natu4_pf_se_pj BOOLEAN NOT NULL DEFAULT false,
    pagina_equivalencia INT,
    observacoes STRING
)
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported'
)
""")

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.modalidades_equivalencia
  (mod_3040, mod_3040_descricao, modalidade_3050, segmento_3050, encargo_3050, tem_regra_especial)
VALUES
  ('0201', 'Empréstimos - Capital de giro até 365 dias', 'capitalDeGiro', 'pesJuridica', 'pre', false),
  ('0202', 'Empréstimos - Capital de giro acima 365 dias', 'capitalDeGiro', 'pesJuridica', 'pre', false),
  ('0204', 'Crédito pessoal não consignado', 'crdPessoal', 'pesFisica', 'pre', false),
  ('0301', 'Títulos descontados', 'descDuplicatas', 'pesJuridica', 'pre', false),
  ('0401', 'Financiamento imobiliário - SFH', 'aquisicaoImovel', 'pesFisica', 'flu', false),
  ('0402', 'Financiamento imobiliário - SFI', 'aquisicaoImovel', 'pesFisica', 'flu', false)
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Dimensões R.18 (12 Quality Dimensions)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.dimensoes_r18 (
    dimensao_id STRING NOT NULL,
    nome STRING NOT NULL,
    definicao_regulatoria STRING NOT NULL,
    artigo_r18 STRING NOT NULL,
    metrica_implementacao STRING NOT NULL,
    meta_padrao_pct DECIMAL(5,2) NOT NULL,
    capacidade_databricks STRING NOT NULL,
    nivel_implementacao STRING NOT NULL,
    expectation_prefix STRING,
    dashboard_widget STRING,
    is_implementado_mvp BOOLEAN NOT NULL
)
""")

# Canonical 12 dimensions from R.18 Art. 2, §2 — see docs/spec/01_requirements.md §1.2.
spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.dimensoes_r18 VALUES
  ('I', 'Acessibilidade', 'Condições para obter informações, incluindo local, forma, prazos e tratamento PcD', 'Art.2,§2,I', 'SLA de atendimento BCB + catálogo acessível a não-técnicos', 95.00, 'UC Data Catalog + AI/BI Dashboards', 'Governance', 'acess_', 'gauge_sla', true),
  ('II', 'Acurácia', 'Medida em que a informação reflete a realidade de forma precisa, conforme metodologia', 'Art.2,§2,II', 'Taxa rejeição BCB ≤ 5%; reconciliação pré-envio aprovada', 95.00, 'DLT Expectations + reconciliação gold', 'Silver', 'acur_', 'gauge_accuracy', true),
  ('III', 'Adaptabilidade', 'Capacidade de gerar informações em formato que atenda diversas demandas e mudanças regulamentares', 'Art.2,§2,III', 'Adaptação V10→V11 dentro do prazo; plano de contingência testado', 90.00, 'SCD Tipo 2 leiaute_versoes + DR test logs', 'Reference', 'adapt_', 'gauge_adaptability', true),
  ('IV', 'Clareza', 'Apresentação concisa, compreensível, atendendo às necessidades do usuário', 'Art.2,§2,IV', 'Dicionário com descrições em linguagem de negócio; onboarding ≤ 2 sem.', 95.00, 'UC COMMENT ON COLUMN coverage', 'Governance', 'clar_', 'gauge_clarity', true),
  ('V', 'Comparabilidade', 'Capacidade de identificar semelhanças e diferenças entre períodos ou domínios', 'Art.2,§2,V', 'Histórico de leiautes versionado; metadados de versão em cada registro', 95.00, 'Delta Time Travel + SCD Tipo 2', 'Silver', 'comp_', 'gauge_comparability', true),
  ('VI', 'Completude', 'Capacidade de atender integralmente os aspectos requeridos', 'Art.2,§2,VI', 'Zero rejeições por campos obrigatórios; reconciliação de universo', 95.00, 'DLT expect_or_drop + universe count checks', 'Silver', 'compl_', 'gauge_completeness', true),
  ('VII', 'Confiabilidade', 'Ausência de desvio relevante nos dados revisados vs valor inicial', 'Art.2,§2,VII', 'Dados intermediários imutáveis; taxa de retrabalho < 10%', 90.00, 'Delta ACID + append-only audit', 'Silver', 'confiab_', 'gauge_reliability', true),
  ('VIII', 'Consistência', 'Informações padronizadas e livres de contradições, mesmo de fontes diferentes', 'Art.2,§2,VIII', 'Reconciliação 3040 vs 3050 vs COSIF; divergências bloqueiam envio', 90.00, 'Gold reconciliation tables', 'Gold', 'consist_', 'gauge_consistency', true),
  ('IX', 'Integridade', 'Garantia de autenticidade e ausência de modificação não autorizada', 'Art.2,§2,IX', 'RBAC com menor privilégio; audit log inalterável; segregação gerar/aprovar', 100.00, 'UC RBAC + Audit Logs + SoD matrix', 'Governance', 'integr_', 'gauge_integrity', true),
  ('X', 'Rastreabilidade', 'Condições para rastrear a informação desde a origem até a disponibilização ao usuário final', 'Art.2,§2,X', 'Lineage end-to-end ≥ 95%; demonstração em auditoria em < 30 min', 90.00, 'UC System Tables + External Lineage API', 'Governance', 'rastr_', 'gauge_traceability', true),
  ('XI', 'Relevância', 'Capacidade de fornecer informações úteis que influenciem tomada de decisões', 'Art.2,§2,XI', 'Relatório semestral apresentado ao CA com ata; indicadores revisados pela diretoria', 85.00, 'Semi-annual report + CA meeting evidence', 'Governance', 'relev_', 'gauge_relevance', false),
  ('XII', 'Tempestividade', 'Fornecimento em tempo hábil, no prazo estabelecido', 'Art.2,§2,XII', 'Histórico de cumprimento ≥ 95%; envio com ≥ 2 dias úteis de antecedência', 95.00, 'BCB calendar + submission tracking', 'Gold', 'temp_', 'gauge_timeliness', true)
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Layout Versions

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.leiaute_versoes (
    leiaute_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    documento STRING NOT NULL,
    versao STRING NOT NULL,
    dt_vigencia_ini DATE NOT NULL,
    dt_vigencia_fim DATE,
    is_current BOOLEAN NOT NULL,
    xsd_path STRING,
    criticas_count INT,
    modalidades_novas ARRAY<STRING>,
    modalidades_removidas ARRAY<STRING>,
    criticas_novas ARRAY<STRING>,
    changelog STRING,
    dt_publicacao_bcb DATE
)
""")

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.leiaute_versoes (documento, versao, dt_vigencia_ini, is_current, criticas_count, changelog, dt_publicacao_bcb) VALUES
  ('3050', 'V11', '2025-11-07', true, 130, 'Adição de sub-modalidades crédito pessoal não consignado', '2025-10-15'),
  ('3050', 'V10', '2025-07-01', false, 125, 'Versão anterior', '2025-06-01'),
  ('3050_dominios', 'V10', '2025-11-07', true, NULL, 'Domínios atualizados para V11', '2025-10-15'),
  ('3050_criticas', 'V11', '2025-11-07', true, 130, 'Críticas V11', '2025-10-15'),
  ('3040', 'V1', '2000-01-01', true, 60, 'Versão única do SCR 3040', NULL)
""")

# COMMAND ----------

print("Reference tables setup complete.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Governance — Incidents log (R.18 Art.2 §3)
# MAGIC
# MAGIC Tabela criada vazia no catálogo RC18 (schema `governance` — declarado em
# MAGIC `resources/uc_assets.yml`). Populada pelo POST /governance/incidents do
# MAGIC app + futuro auto-emit job pós-silver (spec 08 §4.1).

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.governance.incidents (
    incident_id           STRING,
    critica_id            STRING,
    run_config_name       STRING,
    dt_base               DATE,
    check_name            STRING,
    rule_fingerprint      STRING,
    first_seen_run_id     STRING,
    last_seen_run_id      STRING,
    affected_records      BIGINT,
    total_records         BIGINT,
    taxa_violacao_pct     DOUBLE,
    documento             STRING,
    dimensao_r18          STRING,
    artigo_r18            STRING,
    nivel_verificacao     STRING,
    severidade            STRING,
    mensagem              STRING,
    status                STRING,
    owner                 STRING,
    detected_at           TIMESTAMP,
    detected_by           STRING,
    assigned_at           TIMESTAMP,
    responded_at          TIMESTAMP,
    responded_by          STRING,
    escalated_at          TIMESTAMP,
    escalated_to          STRING,
    resolved_at           TIMESTAMP,
    resolved_by           STRING,
    validated_at          TIMESTAMP,
    validated_by          STRING,
    reopened_at           TIMESTAMP,
    root_cause            STRING,
    remedial_action       STRING,
    impact                STRING,
    bcb_communication_required BOOLEAN,
    included_in_report    STRING,
    timeline              ARRAY<STRUCT<
                            timestamp:   TIMESTAMP,
                            event_type:  STRING,
                            actor:       STRING,
                            description: STRING
                          >>,
    created_at            TIMESTAMP,
    updated_at            TIMESTAMP
)
USING DELTA
PARTITIONED BY (dt_base)
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.logRetentionDuration'        = 'interval 1825 days'
)
""")

print(f"Governance incidents table ready at {CATALOG}.governance.incidents")
