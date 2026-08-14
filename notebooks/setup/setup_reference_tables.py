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
  -- Domínios adicionais consumidos pelos checks DQX (via views v_dom_3040_*).
  -- Ficam em dominios (fonte única) porque o DQX Studio NÃO aceita literais string
  -- na expression do check (o parse_json inline os corrompe) — o filtro documento/
  -- campo vive DENTRO da view, e o check faz `col IN (SELECT valor_codigo FROM view)`.
  ('3040', 'Autorzc', 'S', 'Autoriza consulta ao SCR', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'Autorzc', 'N', 'Não autoriza consulta ao SCR', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCtrl', '01', 'Controle da União', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCtrl', '02', 'Controle de estados/municípios', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCtrl', '03', 'Controle privado nacional', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'TpCtrl', '04', 'Controle privado estrangeiro', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '0', 'Porte PF - faixa 0', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '1', 'Porte PF - faixa 1', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '2', 'Porte PF - faixa 2', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '3', 'Porte PF - faixa 3', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '4', 'Porte PF - faixa 4', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '5', 'Porte PF - faixa 5', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '6', 'Porte PF - faixa 6', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '7', 'Porte PF - faixa 7', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPF', '8', 'Porte PF - faixa 8', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPJ', '0', 'Porte PJ - faixa 0', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPJ', '1', 'Porte PJ - faixa 1', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPJ', '2', 'Porte PJ - faixa 2', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPJ', '3', 'Porte PJ - faixa 3', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3040', 'PorteCliPJ', '4', 'Porte PJ - faixa 4', 'Anexo 1', 'V1', '2000-01-01', true),
  ('3050', 'encargo', 'pre', 'Prefixado', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'flu', 'Pós-fixado flutuante', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'vc', 'Variação cambial', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'ipca', 'IPCA', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'igpm', 'IGP-M', NULL, 'V11', '2025-11-07', true),
  ('3050', 'encargo', 'ind', 'Indexador genérico', NULL, 'V11', '2025-11-07', true),
  ('3050', 'segmento', 'pesJuridica', 'Pessoa Jurídica', NULL, 'V11', '2025-11-07', true),
  ('3050', 'segmento', 'pesFisica', 'Pessoa Física', NULL, 'V11', '2025-11-07', true),
  -- Status bloqueante da reconciliação COSIF (consumido por v_recon_status_bloqueante).
  ('4010', 'ReconStatusBloqueante', 'BLOQUEADO', 'Divergência de batimento acima da tolerância', NULL, 'V1', '2000-01-01', true),
  -- Tipo de remessa do leiaute XML COSIF (§3.1.2.e das Instruções 4010/4016).
  ('4010', 'tipoRemessa', 'I', 'Inclusão — primeira remessa do documento para a data-base', NULL, 'XMLv1', '2025-01-01', true),
  ('4010', 'tipoRemessa', 'S', 'Substituição — troca documento já aceito pelo BCB', NULL, 'XMLv1', '2025-01-01', true),
  ('4016', 'tipoRemessa', 'I', 'Inclusão — primeira remessa do documento para a data-base', NULL, 'XMLv1', '2025-01-01', true),
  ('4016', 'tipoRemessa', 'S', 'Substituição — troca documento já aceito pelo BCB', NULL, 'XMLv1', '2025-01-01', true),
  -- Grupos COSIF VEDADOS no Doc 4016: como o Balanço Patrimonial Analítico
  -- representa a posição APÓS a apuração do resultado do exercício, não se espera
  -- a presença das contas dos grupos 7 e 8 (§3.2.2.a das Instruções 4010/4016).
  ('4016', 'GrupoVedado', '7', 'Receitas — não esperadas no Balanço (posição após apuração do resultado)', NULL, 'XMLv1', '2025-01-01', true),
  ('4016', 'GrupoVedado', '8', 'Despesas — não esperadas no Balanço (posição após apuração do resultado)', NULL, 'XMLv1', '2025-01-01', true)
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1b. Views de domínio para os checks DQX
# MAGIC
# MAGIC O DQX Studio grava cada check via `parse_json('<json inline>')`; literais
# MAGIC string na `expression` são corrompidos nesse caminho (aspas simples são
# MAGIC engolidas no round-trip; aspas duplas quebram o parse). A saída robusta é
# MAGIC manter a `expression` **sem literais string**: o filtro `documento`/`campo`
# MAGIC vive nestas views, e o check faz apenas
# MAGIC `col IN (SELECT valor_codigo FROM {CATALOG}.reference.v_dom_3040_*)`.

# COMMAND ----------

# Uma view por campo de domínio consumido pelos checks (filtro documento/campo
# encapsulado aqui, fora do check). Nomes estáveis: v_dom_3040_<campo> em snake.
for _campo, _view in [
    ("NatuOp", "v_dom_3040_natuop"),
    ("Mod", "v_dom_3040_mod"),
    ("TpCli", "v_dom_3040_tpcli"),
    ("Autorzc", "v_dom_3040_autorzc"),
    ("TpCtrl", "v_dom_3040_tpctrl"),
    ("PorteCliPF", "v_dom_3040_portecli_pf"),
    ("PorteCliPJ", "v_dom_3040_portecli_pj"),
]:
    spark.sql(f"""
        CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.{_view} AS
        SELECT valor_codigo
        FROM {CATALOG}.{SCHEMA}.dominios
        WHERE documento = '3040' AND campo = '{_campo}' AND is_current
    """)

# Status que BLOQUEIAM a remessa na reconciliação COSIF (check usa NOT IN).
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_recon_status_bloqueante AS
    SELECT valor_codigo
    FROM {CATALOG}.{SCHEMA}.dominios
    WHERE documento = '4010' AND campo = 'ReconStatusBloqueante' AND is_current
""")

# Tipo de remessa aceito no leiaute XML COSIF — vale para 4010 e 4016.
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_dom_cosif_tiporemessa AS
    SELECT DISTINCT valor_codigo
    FROM {CATALOG}.{SCHEMA}.dominios
    WHERE documento IN ('4010', '4016') AND campo = 'tipoRemessa' AND is_current
""")

# Grupos COSIF vedados no Doc 4016 (7 = Receitas, 8 = Despesas). `valor_codigo`
# já sai como INT para casar com `silver.scr4016_saldos.grupo_cosif` sem CAST no
# check — mantendo a expression da DQX livre de literais e de conversões.
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_dom_4016_grupo_vedado AS
    SELECT CAST(valor_codigo AS INT) AS valor_codigo
    FROM {CATALOG}.{SCHEMA}.dominios
    WHERE documento = '4016' AND campo = 'GrupoVedado' AND is_current
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
# autoritativas vivem em `dq_quality_rules` da DQX Studio e são criadas via a
# própria Studio (Motor de Regras) — o RC18 não semeia mais regras. O CREATE
# acima é preservado para compatibilidade com dashboards/notebooks legados.

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

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Vínculo de Regras DQX ↔ CADOC + Dimensão R.18
# MAGIC
# MAGIC Três tabelas MUTÁVEIS escritas pelo app (schema `governance`, como
# MAGIC `incidents`) que substituem o vínculo hard-coded regra→documento→dimensão:
# MAGIC
# MAGIC - `cadoc_documentos` — registro de CADOCs (3040/3050 semeados; novos via UI).
# MAGIC - `cadoc_tabelas`    — CADOC → tabelas silver (1:N). Substitui o prefixo
# MAGIC   `silver.scr3040_` hard-coded em `validation.py`/`reference.py`.
# MAGIC - `regra_vinculos`   — regra DQX → CADOC + dimensão R.18. Guarda **tanto**
# MAGIC   `rule_id` (estável) quanto `check_name` (chave de junção com as métricas de
# MAGIC   execução da DQX), corrigindo o drop silencioso de regras criadas sem `name`.
# MAGIC
# MAGIC Populadas pela tela `/linking` do app (CRUD via `routers/linking.py`). Toda
# MAGIC leitura filtra `is_ativo = true` (soft delete). `regra_vinculos` NÃO é semeada
# MAGIC — as 4 regras iniciais continuam resolvendo por `rc18_rule_meta.RC18_RULE_META`.

# COMMAND ----------

# 8.1 — CADOC registry. `documento` é a chave natural (unicidade garantida no app
# via pré-check + 409; Delta não impõe PK). DEFAULT em is_ativo exige allowColumnDefaults.
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.governance.cadoc_documentos (
    documento        STRING NOT NULL,
    nome             STRING NOT NULL,
    descricao        STRING,
    leiaute_versao   STRING,
    is_ativo         BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMP,
    created_by       STRING,
    updated_at       TIMESTAMP,
    updated_by       STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.logRetentionDuration'        = 'interval 1825 days'
)
""")

# Seed 3040/3050 (idempotente: só insere se ainda não existir a linha).
spark.sql(f"""
INSERT INTO {CATALOG}.governance.cadoc_documentos
  (documento, nome, descricao, leiaute_versao, is_ativo, created_at, created_by, updated_at, updated_by)
SELECT * FROM (
  SELECT '3040' AS documento, 'SCR 3040 - Operações de crédito individualizadas' AS nome,
         'Documento SCR 3040 — operações de crédito detalhadas (130+ campos, IPOC).' AS descricao,
         'V1' AS leiaute_versao, true AS is_ativo,
         current_timestamp() AS created_at, 'setup:seed' AS created_by,
         current_timestamp() AS updated_at, 'setup:seed' AS updated_by
  UNION ALL
  SELECT '3050', 'SCR 3050 - Estoque mensal agregado',
         'Documento SCR 3050 — dados agregados de crédito (TXB/XML, leiaute versionado).',
         'V11', true, current_timestamp(), 'setup:seed', current_timestamp(), 'setup:seed'
  UNION ALL
  SELECT '4010', 'COSIF 4010 - Balancete Patrimonial Analítico',
         'Documento contábil COSIF 4010 — balancete analítico mensal (uma conta COSIF por saldo). Leiaute XML obrigatório desde a data-base jan/2025 (IN BCB 469/2024); envio via STA com o código ACOS010. Perna contábil do batimento inter-CADOC com o SCR 3040.',
         'XMLv1', true, current_timestamp(), 'setup:seed', current_timestamp(), 'setup:seed'
  UNION ALL
  SELECT '4016', 'COSIF 4016 - Balanço Patrimonial Analítico',
         'Documento contábil COSIF 4016 — balanço analítico SEMESTRAL (datas-base junho e dezembro), posição após a apuração do resultado do exercício, sem as contas dos grupos 7 (Receitas) e 8 (Despesas). Mesmo leiaute XML do 4010; envio via STA com o código ACOS016.',
         'XMLv1', true, current_timestamp(), 'setup:seed', current_timestamp(), 'setup:seed'
) src
WHERE NOT EXISTS (
  SELECT 1 FROM {CATALOG}.governance.cadoc_documentos d WHERE d.documento = src.documento
)
""")

# COMMAND ----------

# 8.2 — CADOC → tabelas silver (1:N). Chave natural (documento, table_fqn).
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.governance.cadoc_tabelas (
    documento    STRING NOT NULL,
    table_fqn    STRING NOT NULL,
    is_ativo     BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMP,
    created_by   STRING,
    updated_at   TIMESTAMP,
    updated_by   STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.logRetentionDuration'        = 'interval 1825 days'
)
""")

# Seed com as tabelas silver canônicas (ver resources/uc_assets.yml). FQN completo
# ({CATALOG}.silver.<t>) porque é a forma que aparece em dq_validation_runs.source_table_fqn.
_SILVER_SEED = [
    ("3040", "scr3040_operacoes"),
    ("3040", "scr3040_clientes"),
    ("3040", "scr3040_garantias"),
    ("3040", "scr3040_vencimentos"),
    ("3040", "scr3040_cont_4966"),
    ("3050", "scr3050"),
    ("4010", "scr4010_saldos"),
    ("4016", "scr4016_saldos"),
]
_values = ",\n  ".join(
    f"('{doc}', '{CATALOG}.silver.{t}')" for doc, t in _SILVER_SEED
)
spark.sql(f"""
INSERT INTO {CATALOG}.governance.cadoc_tabelas
  (documento, table_fqn, is_ativo, created_at, created_by, updated_at, updated_by)
SELECT src.documento, src.table_fqn, true,
       current_timestamp(), 'setup:seed', current_timestamp(), 'setup:seed'
FROM (VALUES
  {_values}
) AS src(documento, table_fqn)
WHERE NOT EXISTS (
  SELECT 1 FROM {CATALOG}.governance.cadoc_tabelas t
  WHERE t.documento = src.documento AND t.table_fqn = src.table_fqn
)
""")

# COMMAND ----------

# 8.3 — Vínculo regra DQX → CADOC + dimensão. `vinculo_id` = uuid gerado pelo app.
# Chave única lógica: (table_fqn, check_name). `rule_id` guardado para proveniência
# e para reconciliar quando o check_name derivar (regra sem `name` explícito).
# NÃO semeado — populado exclusivamente pela tela /linking.
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.governance.regra_vinculos (
    vinculo_id         STRING NOT NULL,
    check_name         STRING NOT NULL,
    rule_id            STRING,
    table_fqn          STRING NOT NULL,
    documento          STRING,
    dimensao_r18       INT,
    critica_id         STRING,
    nivel_verificacao  INT,
    descricao          STRING,
    is_ativo           BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMP,
    created_by         STRING,
    updated_at         TIMESTAMP,
    updated_by         STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.logRetentionDuration'        = 'interval 1825 days'
)
""")

print(f"CADOC linking tables ready at {CATALOG}.governance.(cadoc_documentos, cadoc_tabelas, regra_vinculos)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Contas COSIF para batimento inter-CADOC (SCR 3040 × Doc 4010)
# MAGIC
# MAGIC `reference.cosif_contas` (ver docs/spec/03_data_model.md §5.7) define QUAIS contas
# MAGIC do Balancete COSIF (Documento 4010) correspondem a cada regra de reconciliação
# MAGIC (T = totais, M = por modalidade) e como a "perna SCR" do batimento é montada
# MAGIC (predicado sobre a modalidade do 3040). Consumida pelo gold `reconciliacao_cosif`.
# MAGIC
# MAGIC ⚠️ SIMULAÇÃO: subconjunto REPRESENTATIVO de regras T/M com terminologia COSIF
# MAGIC padrão — não o mapa COSIF completo do BACEN nem o leiaute byte-exato do 4010.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.cosif_contas (
    cosif_sk             BIGINT GENERATED ALWAYS AS IDENTITY,
    cosif_conta          STRING NOT NULL,
    descricao            STRING NOT NULL,
    grupo_reconciliacao  STRING NOT NULL,   -- T01, T06, M01, M02, ...
    tipo_regra           STRING NOT NULL,   -- 'T' (totais) | 'M' (modalidade)
    predicado_3040       STRING,            -- expressão SQL sobre a operação silver 3040
    coluna_saldo_3040    STRING NOT NULL,   -- total_saldo | total_limites
    modalidade_3040      STRING,            -- Mod correspondente (apenas tipo 'M')
    sinal_soma           INT NOT NULL,      -- +1 soma | -1 subtrai na reconciliação
    nivel_conta          INT NOT NULL,      -- nível hierárquico COSIF (1-8)
    is_ativo             BOOLEAN NOT NULL DEFAULT true
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'supported',
    'delta.logRetentionDuration'        = 'interval 1825 days'
)
""")

# Seed idempotente (subconjunto representativo alinhado ao gerador do 4010).
spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.cosif_contas
  (cosif_conta, descricao, grupo_reconciliacao, tipo_regra, predicado_3040, coluna_saldo_3040, modalidade_3040, sinal_soma, nivel_conta, is_ativo)
SELECT * FROM (
  -- cosif_conta no formato POSICIONAL oficial: 10 dígitos, só numéricos (leiaute
  -- Doc 4010 registro de dados, campo "Código de conta" N(010)). Casa com
  -- silver.scr4010_saldos.codigo_conta produzido pelo parser posicional.
  SELECT '0031000000' AS cosif_conta, 'Total de créditos - carteira ativa' AS descricao, 'T01' AS grupo_reconciliacao, 'T' AS tipo_regra, 'total_saldo > 0' AS predicado_3040, 'total_saldo' AS coluna_saldo_3040, CAST(NULL AS STRING) AS modalidade_3040, 1 AS sinal_soma, 3 AS nivel_conta, true AS is_ativo
  UNION ALL SELECT '0030980004','Créditos a liberar e limites','T06','T','total_limites > 0','total_limites',NULL,1,4,true
  UNION ALL SELECT '0016110001','Adiantamentos a depositantes','M01','M',"mod = '0101'",'total_saldo','0101',1,5,true
  UNION ALL SELECT '0016120008','Empréstimos (capital de giro)','M02','M',"mod IN ('0201','0202')",'total_saldo','0201',1,5,true
  UNION ALL SELECT '0016130005','Títulos descontados','M03','M',"mod = '0301'",'total_saldo','0301',1,5,true
  UNION ALL SELECT '0016210004','Financiamentos','M04','M',"mod IN ('0401','0402')",'total_saldo','0401',1,5,true
  UNION ALL SELECT '0018100002','Crédito pessoal / outros créditos','M13','M',"mod = '0204'",'total_saldo','0204',1,5,true
) src
WHERE NOT EXISTS (
  SELECT 1 FROM {CATALOG}.{SCHEMA}.cosif_contas c
  WHERE c.cosif_conta = src.cosif_conta AND c.grupo_reconciliacao = src.grupo_reconciliacao
)
""")

print(f"COSIF reconciliation map ready at {CATALOG}.{SCHEMA}.cosif_contas")
