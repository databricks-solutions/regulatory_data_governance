# Databricks notebook source
# MAGIC %md
# MAGIC # Silver DLT/SDP — CADOC 4010 (Balancete COSIF)
# MAGIC
# MAGIC Versão declarativa. Produz a MESMA tabela `scr4010_saldos` e o mesmo
# MAGIC contrato que o notebook clássico `pipelines/classical/silver/scr4010.py`.
# MAGIC ELT puro (qualidade externa na DQX Studio / gold batimento).

# COMMAND ----------

import uuid
import dlt
from pyspark.sql import functions as F, Window


SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")

_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"


@dlt.table(
    name="scr4010_saldos",
    comment="Silver — Balancete COSIF (Doc 4010) normalizado por conta. dt_base DATE, dedupe por (cnpj_if, dt_base, cosif_conta). Base da 'perna COSIF' do batimento inter-CADOC.",
    partition_cols=["dt_base"],
)
def scr4010_saldos():
    bronze = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_cosif_saldos")
    dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "cosif_conta").orderBy(F.col("_ingestion_timestamp").desc())
    return (
        bronze
        .withColumn("_rn", F.row_number().over(dedupe_w))
        .filter(F.col("_rn") == 1)
        .select(
            "cnpj_if",
            F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
            F.col("dt_base").alias("dt_base_mes"),
            "cosif_conta", "cosif_descricao",
            F.coalesce(F.col("saldo_credor"), F.lit(0)).cast("decimal(17,2)").alias("saldo_credor"),
            F.coalesce(F.col("saldo_devedor"), F.lit(0)).cast("decimal(17,2)").alias("saldo_devedor"),
            F.coalesce(F.col("saldo_liquido"), F.lit(0)).cast("decimal(17,2)").alias("saldo_liquido"),
            "tp_conta",
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )
