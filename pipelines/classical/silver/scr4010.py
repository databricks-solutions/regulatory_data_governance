# Databricks notebook source
# MAGIC %md
# MAGIC # Silver CLÁSSICO — CADOC 4010 (Balancete COSIF)
# MAGIC
# MAGIC Normaliza `bronze.raw_cosif_saldos` → `silver.scr4010_saldos` (tipagem
# MAGIC final, `dt_base` como DATE do 1º dia do mês, dedupe por conta). Produz a
# MAGIC MESMA tabela/contrato que o pipeline DLT
# MAGIC `pipelines/silver/transformations/scr4010.py` — só muda o I/O
# MAGIC (`saveAsTable(overwrite)` vs `@dlt.table`).
# MAGIC
# MAGIC ELT puro — sem qualidade inline (delegada à DQX Studio / gold batimento).

# COMMAND ----------

import uuid
from pyspark.sql import functions as F, Window

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("silver_schema", "silver")

CATALOG = dbutils.widgets.get("catalog")
BRONZE_SCHEMA = dbutils.widgets.get("bronze_schema")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")

_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.raw_cosif_saldos")

# dedupe por (cnpj_if, dt_base, cosif_conta) — mantém a ingestão mais recente.
_dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "cosif_conta").orderBy(F.col("_ingestion_timestamp").desc())
scr4010 = (
    bronze
    .withColumn("_rn", F.row_number().over(_dedupe_w))
    .filter(F.col("_rn") == 1)
    .select(
        "cnpj_if",
        # dt_base vira DATE (1º dia do mês) para casar com o particionamento das
        # demais silver e permitir joins temporais.
        F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
        F.col("dt_base").alias("dt_base_mes"),   # preserva o AAAA-MM textual
        "cosif_conta", "cosif_descricao",
        F.coalesce(F.col("saldo_credor"), F.lit(0)).cast("decimal(17,2)").alias("saldo_credor"),
        F.coalesce(F.col("saldo_devedor"), F.lit(0)).cast("decimal(17,2)").alias("saldo_devedor"),
        F.coalesce(F.col("saldo_liquido"), F.lit(0)).cast("decimal(17,2)").alias("saldo_liquido"),
        "tp_conta",
        F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
        F.current_timestamp().alias("_silver_timestamp"),
    )
)

fqn = f"{CATALOG}.{SILVER_SCHEMA}.scr4010_saldos"
(scr4010.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true").partitionBy("dt_base").saveAsTable(fqn))
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
