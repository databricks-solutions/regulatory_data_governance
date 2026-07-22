# Databricks notebook source
# MAGIC %md
# MAGIC # Silver DLT/SDP — CADOC 4010 (Balancete COSIF)
# MAGIC
# MAGIC MESMA tabela `scr4010_saldos` e contrato que o clássico
# MAGIC `pipelines/classical/silver/scr4010.py`. Alinhado ao leiaute oficial
# MAGIC (codigo_conta 10 dígitos + saldo assinado).

# COMMAND ----------

import uuid
import dlt
from pyspark.sql import functions as F, Window


SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")

_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"


@dlt.table(
    name="scr4010_saldos",
    comment="Silver — Balancete COSIF (Doc 4010) normalizado. codigo_conta (10 díg COSIF) + saldo assinado. Base da 'perna COSIF' do batimento inter-CADOC.",
    partition_cols=["dt_base"],
)
def scr4010_saldos():
    bronze = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_cosif_saldos")
    dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "codigo_conta").orderBy(F.col("_ingestion_timestamp").desc())
    return (
        bronze
        .withColumn("_rn", F.row_number().over(dedupe_w))
        .filter(F.col("_rn") == 1)
        .select(
            "cnpj_if",
            F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
            F.col("dt_base").alias("dt_base_mes"),
            "codigo_conta",
            F.col("saldo").cast("decimal(17,2)").alias("saldo"),
            "sinal",
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )
