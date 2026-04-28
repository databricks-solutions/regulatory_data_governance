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
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = "reference"

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

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.validation_rules
  (critica_id, documento, leiaute_versao, grupo, descricao, expressao_sql, campo_alvo, severidade, acao_dlt, dimensao_r18, artigo_r18, mensagem_erro, dt_vigencia_ini, is_active, updated_at)
VALUES
  ('S10_001', '3040', 'V1', 'sintatica', 'Campo DtContr obrigatório', 'dt_contr IS NOT NULL', 'dt_contr', 'BLOQUEANTE', 'expect_or_drop', 'VI', 'Art.2,§2,VI', 'DtContr ausente', '2000-01-01', true, current_timestamp()),
  ('S10_002', '3040', 'V1', 'sintatica', 'CNPJ IF deve ter 8 dígitos', 'LENGTH(cnpj_if) = 8', 'cnpj_if', 'BLOQUEANTE', 'expect_or_drop', 'VI', 'Art.2,§2,VI', 'CNPJ IF inválido', '2000-01-01', true, current_timestamp()),
  ('SEM_014', '3040', 'V1', 'semantica', 'IPOC componentes vs campos da operação', 'ipoc_is_consistent = true', 'ipoc', 'BLOQUEANTE', 'expect', 'II', 'Art.2,§2,II', 'Componentes IPOC divergentes', '2000-01-01', true, current_timestamp()),
  ('SEM_020', '3040', 'V1', 'semantica', 'DtVencOp >= DtContr', 'dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr', 'dt_venc_op', 'BLOQUEANTE', 'expect_or_drop', 'VIII', 'Art.2,§2,VIII', 'Vencimento anterior à contratação', '2000-01-01', true, current_timestamp()),
  ('SEM_001', '3040', 'V1', 'semantica', 'Classificação de risco válida', "class_op IS NULL OR class_op IN ('AA','A','B','C','D','E','F','G','H')", 'class_op', 'ALERTA', 'expect', 'II', 'Art.2,§2,II', 'Classificação inválida', '2000-01-01', true, current_timestamp()),
  ('INT_001', '3040', 'V1', 'inter_documento', 'Saldo 3040 vs COSIF dentro de 0.1%', 'ABS(vlr_scr - vlr_cosif) / vlr_cosif < 0.001', NULL, 'ALERTA', 'expect', 'VIII', 'Art.2,§2,VIII', 'Divergência 3040 vs COSIF', '2000-01-01', true, current_timestamp()),
  ('CR1_001', '3050', 'V11', 'sintatica', 'Encargo obrigatório', 'encargo IS NOT NULL', 'encargo', 'BLOQUEANTE', 'expect_or_drop', 'VI', 'Art.2,§2,VI', 'Encargo ausente', '2025-11-07', true, current_timestamp()),
  ('CR2_001', '3050', 'V11', 'sintatica', 'Periodicidade válida', "tipo_periodo IN ('diario','mensal')", 'tipo_periodo', 'BLOQUEANTE', 'expect_or_drop', 'XI', 'Art.2,§2,XI', 'Periodicidade inválida', '2025-11-07', true, current_timestamp()),
  ('CR4_001', '3050', 'V11', 'semantica', 'Valor concessão positivo', 'vlr_concessoes IS NULL OR vlr_concessoes >= 0', 'vlr_concessoes', 'BLOQUEANTE', 'expect_or_drop', 'II', 'Art.2,§2,II', 'Concessão negativa', '2025-11-07', true, current_timestamp())
""")

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

# Generate date sequence
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

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.dimensoes_r18 VALUES
  ('I', 'Acessibilidade', 'Condições para obter informações, incluindo local, forma, prazos e tratamento PcD', 'Art.2,§2,I', 'SLA de atendimento + cobertura catálogo', 95.00, 'UC catálogo + AI/BI Dashboards', 'Governance', 'acess_', 'gauge_sla', true),
  ('II', 'Acurácia', 'Medida em que a informação reflete a realidade de forma precisa', 'Art.2,§2,II', 'Taxa rejeição BCB + reconciliação pré-envio', 95.00, 'DLT Expectations + reconciliação gold', 'Silver', 'acur_', 'gauge_accuracy', true),
  ('III', 'Atualidade', 'Intervalo entre a ocorrência e a disponibilização da informação', 'Art.2,§2,III', 'Latência média CDC fonte→bronze', 95.00, 'Auto Loader + Lakeflow Connect', 'Bronze', 'atual_', 'gauge_latency', true),
  ('IV', 'Completude', 'Abrangência dos dados em relação ao esperado', 'Art.2,§2,IV', 'Campos obrigatórios preenchidos', 95.00, 'DLT Expectations NOT NULL', 'Silver', 'compl_', 'gauge_completeness', true),
  ('V', 'Confidencialidade', 'Controle de acesso segundo autorizações e legislação vigente', 'Art.2,§2,V', 'Acessos não autorizados = 0', 100.00, 'UC ACLs + Row/Column Security + Audit Logs', 'Governance', 'conf_', 'gauge_security', true),
  ('VI', 'Conformidade', 'Aderência a regras, padrões e leiautes normativos', 'Art.2,§2,VI', 'Taxa de conformidade com críticas BCB', 95.00, 'DLT Expectations parametrizadas', 'Silver', 'conform_', 'gauge_compliance', true),
  ('VII', 'Confiabilidade', 'Nível de confiança nos dados em função de processos e controles', 'Art.2,§2,VII', 'Uptime pipeline + taxa sucesso', 90.00, 'DLT monitoring + Job alerts', 'Bronze', 'confiab_', 'gauge_reliability', true),
  ('VIII', 'Consistência', 'Coerência entre dados de diferentes fontes e documentos', 'Art.2,§2,VIII', 'Reconciliação 3040 vs 3050 vs COSIF', 90.00, 'Gold reconciliation tables', 'Gold', 'consist_', 'gauge_consistency', true),
  ('IX', 'Efetividade', 'Capacidade da informação de produzir resultados pretendidos', 'Art.2,§2,IX', 'Utilização dos dados + KPIs processo', 85.00, 'AI/BI Dashboards + usage tracking', 'Governance', 'efet_', 'gauge_effectiveness', false),
  ('X', 'Rastreabilidade', 'Capacidade de rastrear origem, transformações e destino do dado', 'Art.2,§2,X', 'Cobertura de lineage UC + external', 90.00, 'UC System Tables + External Lineage API', 'Governance', 'rastr_', 'gauge_traceability', true),
  ('XI', 'Tempestividade', 'Disponibilização dentro dos prazos estabelecidos', 'Art.2,§2,XI', 'Envios no prazo BCB', 95.00, 'BCB calendar + submission tracking', 'Gold', 'temp_', 'gauge_timeliness', true),
  ('XII', 'Unicidade', 'Ausência de registros duplicados ou redundantes', 'Art.2,§2,XII', 'Taxa de duplicatas (IPOC + dt_base)', 95.00, 'DLT Expectations DISTINCT + dedup', 'Silver', 'unic_', 'gauge_uniqueness', true)
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

# MAGIC %md
# MAGIC ## 7. COSIF Account Codes

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.cosif_contas (
    cosif_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    cosif_conta STRING NOT NULL,
    descricao STRING NOT NULL,
    grupo_reconciliacao STRING NOT NULL,
    tipo_operacao_3040 STRING,
    sinal_soma INT NOT NULL,
    nivel_conta INT NOT NULL
)
""")

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.cosif_contas (cosif_conta, descricao, grupo_reconciliacao, tipo_operacao_3040, sinal_soma, nivel_conta) VALUES
  ('1610008', 'Títulos Descontados', 'T02', '0301', 1, 3),
  ('1620001', 'Empréstimos', 'T03', '0201', 1, 3),
  ('1630004', 'Financiamentos', 'T04', '0401', 1, 3),
  ('1640007', 'Financiamentos Rurais e Agroindustriais', 'T05', '0501', 1, 3),
  ('1650000', 'Financiamentos Imobiliários', 'T06', '0401', 1, 3),
  ('1690009', 'Outros Créditos', 'T10', NULL, 1, 3)
""")

# COMMAND ----------

print("Reference tables setup complete.")
