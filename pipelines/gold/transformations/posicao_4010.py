# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição CADOC 4010 (Balancete COSIF)
# MAGIC
# MAGIC Passthrough de `silver.scr4010_saldos` (Balancete, MENSAL) + timestamp.
# MAGIC Uma linha por conta COSIF.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_4010.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_4010",
    comment="Posição CADOC 4010 — passthrough de silver.scr4010_saldos (Balancete COSIF) + timestamp de gold.",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_4010():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )
