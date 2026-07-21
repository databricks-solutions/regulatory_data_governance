# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição SCR 3040 e 3050 (sem DLT/SDP)
# MAGIC
# MAGIC Versão **clássica** (job + notebook PySpark) do gold. Produz as MESMAS
# MAGIC tabelas que o pipeline DLT (`pipelines/gold/transformations/posicao_mensal.py`):
# MAGIC
# MAGIC | Table | Source | One row per |
# MAGIC |---|---|---|
# MAGIC | `posicao_3040` | silver `scr3040_operacoes` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos` | `<Op>` por `(cnpj_if, dt_base)` |
# MAGIC | `posicao_3050` | silver `scr3050` (passthrough + `_gold_timestamp`) | dimensão 3050 |
# MAGIC | `processing_state` | posicao_3040/3050 (MAX dt_base) | 1 linha (seletor Data-Base do app) |
# MAGIC
# MAGIC Muda só o I/O: `@dlt.table`→`saveAsTable(overwrite)` e a dependência
# MAGIC same-pipeline (`dlt.read`) de `processing_state` vira leitura sequencial
# MAGIC via `spark.table` (as posições já foram materializadas acima neste run).

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")

SOURCE_CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")


def _gold_fqn(table_name):
    return f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.{table_name}"


# COMMAND ----------
# MAGIC %md
# MAGIC ## Posição SCR 3040
# MAGIC Pure ELT passthrough — silver é puro normalizado (sem DQX inline). Quality
# MAGIC é gerenciada externamente pelo DQX Studio; gold apenas promove os
# MAGIC registros silver para as posições que App/dashboards consomem.

# COMMAND ----------

ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
cont = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_cont_4966")
    .select(
        "cnpj_if", "dt_base", "ipoc",
        "clas_at_fin", "est_inst_fin", "cart_prov_min",
        "vlr_cont_br", "tje", "rend_mes",
        "estagio_motivo", "estagio_dt_alocacao",
    )
)
venc = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
    .select(
        "cnpj_if", "dt_base", "ipoc",
        F.col("total_saldo").alias("total_saldo_vencimentos"),
        "total_a_vencer", "total_vencido", "total_prejuizo",
        "total_limites", "total_coobrigacoes",
    )
)

posicao_3040 = (
    ops
    .join(cont, ["cnpj_if", "dt_base", "ipoc"], "left")
    .join(venc, ["cnpj_if", "dt_base", "ipoc"], "left")
    .select(
        "cnpj_if", "dt_base", "remessa", "parte",
        "cli_tp", "cli_cd", "ipoc", "contrt", "det_cli",
        "natu_op", "mod", "mod_3050_equiv", "segmento_3050_equiv",
        "origem_rec", "indx", "perc_indx", "var_camb",
        "dt_contr", "dt_venc_op", "tax_eft", "prov_consttd",
        "carac_especial", "dia_atraso",
        # Res. 4966 contábil
        "clas_at_fin", "est_inst_fin", "cart_prov_min",
        "vlr_cont_br", "tje", "rend_mes",
        "estagio_motivo", "estagio_dt_alocacao",
        # Vértices
        "total_saldo_vencimentos", "total_a_vencer", "total_vencido",
        "total_prejuizo", "total_limites", "total_coobrigacoes",
        "pipeline_run_id",
        F.current_timestamp().alias("_gold_timestamp"),
    )
)

fqn_3040 = _gold_fqn("posicao_3040")
(
    posicao_3040.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_3040)
)
spark.sql(
    f"ALTER TABLE {fqn_3040} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn_3040}: {spark.table(fqn_3040).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Posição SCR 3050 (passthrough do silver unificado)

# COMMAND ----------

fqn_3050 = _gold_fqn("posicao_3050")
(
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_referencia")
    .saveAsTable(fqn_3050)
)
spark.sql(
    f"ALTER TABLE {fqn_3050} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn_3050}: {spark.table(fqn_3050).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Estado de processamento (data-base corrente)
# MAGIC O app usa este valor para preencher o seletor de Data-Base com o ÚLTIMO
# MAGIC CADOC processado (MAX dt_base observado nas posições 3040/3050). Uma única
# MAGIC linha, recalculada a cada run. No modo clássico lemos as posições já
# MAGIC materializadas acima via `spark.table` (equivalente ao `dlt.read`
# MAGIC same-pipeline do modo DLT).

# COMMAND ----------

p3040 = spark.table(fqn_3040).select("dt_base")
p3050 = spark.table(fqn_3050).select("dt_base")

processing_state = (
    p3040.unionByName(p3050)
    .agg(F.max("dt_base").alias("current_data_base"))
    .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
    .withColumn("updated_at", F.current_timestamp())
)

fqn_state = _gold_fqn("processing_state")
(
    processing_state.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(fqn_state)
)
spark.sql(f"ALTER TABLE {fqn_state} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn_state}: {spark.table(fqn_state).count()} linha(s)")
