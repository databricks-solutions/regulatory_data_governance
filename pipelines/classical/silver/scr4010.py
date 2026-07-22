# Databricks notebook source
# MAGIC %md
# MAGIC # Silver CLÁSSICO — CADOC 4010 (Balancete COSIF)
# MAGIC
# MAGIC Normaliza `bronze.raw_cosif_saldos` → `silver.scr4010_saldos`. Alinhado ao
# MAGIC leiaute oficial: `codigo_conta` (10 dígitos do plano COSIF) + `saldo`
# MAGIC assinado (valor absoluto × sinal do leiaute). `dt_base` vira DATE (1º dia
# MAGIC do mês). Dedupe por (cnpj_if, dt_base, codigo_conta). MESMA tabela/contrato
# MAGIC que o pipeline DLT `pipelines/silver/transformations/scr4010.py`.

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

_dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "codigo_conta").orderBy(F.col("_ingestion_timestamp").desc())
scr4010 = (
    bronze
    .withColumn("_rn", F.row_number().over(_dedupe_w))
    .filter(F.col("_rn") == 1)
    .select(
        "cnpj_if",
        F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
        F.col("dt_base").alias("dt_base_mes"),          # preserva AAAA-MM textual
        "codigo_conta",                                  # conta COSIF 10 dígitos (oficial)
        F.col("saldo").cast("decimal(17,2)").alias("saldo"),   # já assinado no bronze
        "sinal",
        F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
        F.current_timestamp().alias("_silver_timestamp"),
    )
)

fqn = f"{CATALOG}.{SILVER_SCHEMA}.scr4010_saldos"
(scr4010.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true").partitionBy("dt_base").saveAsTable(fqn))
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
