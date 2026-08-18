# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição SCR 3050
# MAGIC
# MAGIC Passthrough fino: a silver já unifica diário+mensal (coluna
# MAGIC `periodicidade`), então o gold só acrescenta o timestamp de auditoria.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_3050.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_3050",
    comment="Posição SCR 3050 — passthrough de silver.scr3050 (diário+mensal já unificados via periodicidade), adicionando timestamp de gold",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
def posicao_3050():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )
