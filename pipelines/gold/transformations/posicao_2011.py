# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição CADOC 2011 (DDR — grão DIÁRIO preservado)
# MAGIC
# MAGIC Único CADOC diário. Preserva o grão diário e marca `is_ultima_do_mes`
# MAGIC (fechamento — uma data-base por `cnpj_if`/mês), para o dashboard escolher
# MAGIC entre série diária e fechamento sem um modo próprio no seletor mensal.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_2011.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_2011",
    comment="Posição CADOC 2011 (DDR, diário) — passthrough de silver.scr2011_contas + flag is_ultima_do_mes (posição de fechamento do mês) + timestamp de gold.",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_2011():
    contas = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr2011_contas")
    ultima = (
        contas.groupBy("cnpj_if", "data_base_month")
        .agg(F.max("dt_base").alias("_dt_ultima"))
    )
    return (
        contas.join(ultima, on=["cnpj_if", "data_base_month"], how="left")
        .withColumn("is_ultima_do_mes", F.col("dt_base") == F.col("_dt_ultima"))
        .drop("_dt_ultima")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )
