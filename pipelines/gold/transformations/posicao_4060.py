# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição CADOC 4060 (Balancete Patrimonial Analítico do Conglomerado Prudencial)
# MAGIC
# MAGIC A "posição" do 4060 é o bloco **`consolidadoPrudencial`** — é o número que
# MAGIC representa o conglomerado, resultado da regra de formação do documento.
# MAGIC Os demais blocos (posição país/exterior e as assemelhadas) são as parcelas
# MAGIC que o compõem e ficam em `silver.scr4060_saldos_*`.
# MAGIC
# MAGIC `saldo` é apelidado a partir de `saldo_consolidado` para deixar esta
# MAGIC tabela comparável com outras posições (4010, etc) — é o que permite o
# MAGIC batimento inter-CADOC sem tratar caso especial.
# MAGIC
# MAGIC O 4060 é **MENSAL**, então ENTRA em `gold.processing_state` (ao contrário
# MAGIC do 4066, que é semestral).
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_4060.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_4060",
    comment="Posição CADOC 4060 — Balancete Patrimonial Analítico do Conglomerado Prudencial, bloco consolidadoPrudencial, mensal.",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_4060():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4060_saldos_consolidado")
        .filter(F.col("bloco") == "consolidadoPrudencial")
        .withColumn("saldo", F.col("saldo_consolidado"))
        .withColumn("_gold_timestamp", F.current_timestamp())
    )

# MAGIC %md
# MAGIC ## Equivalente ao clássico `pipelines/classical/gold/posicao_4060.py`
