# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição CADOC 4016 (Balanço Patrimonial Analítico)
# MAGIC
# MAGIC Passthrough de `silver.scr4016_saldos` + timestamp. Documento SEMESTRAL
# MAGIC (jun/dez), por isso NÃO entra no `processing_state` — ver a nota lá.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_4016.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_4016",
    comment="Posição CADOC 4016 — passthrough de silver.scr4016_saldos (Balanço Patrimonial Analítico, semestral) + timestamp de gold.",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_4016():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4016_saldos")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )
