# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Críticas Summary Views
# MAGIC Aggregated views of validation results for dashboard consumption.
# MAGIC These tables power the "Monitor de Críticas" dashboard and the
# MAGIC governance irregularity tracking.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
QUALITY_SCHEMA = spark.conf.get("quality_schema", "quality")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="qualidade_dimensoes_mensal",
    comment="View agregada: score por dimensão R.18 por data-base — fonte para API /dashboard/kpis e /quality/dimensions",
    table_properties={"quality": "gold"},
    partition_cols=["dt_base"],
)
def qualidade_dimensoes_mensal():
    """Denormalized view joining governance scorecard with dimension metadata for the API."""
    gov = dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.governance_status_qualidade_mensal")

    return (
        gov
        .groupBy("dt_base", "dimensao_id", "dimensao_nome")
        .agg(
            F.avg("score_pct").alias("score_pct"),
            F.first("meta_pct").alias("meta_pct"),
            F.first("status").alias("status"),
            F.first("metrica_principal").alias("metrica_principal"),
            F.first("documento").alias("documento"),
            F.sum("total_registros").alias("total_registros"),
            F.sum("registros_conformes").alias("registros_conformes"),
            F.sum("registros_nao_conformes").alias("registros_nao_conformes"),
        )
    )


@dlt.table(
    name="violacoes_log",
    comment="View da tabela de violações com campos para a API /governance/irregularities e /dashboard/alerts",
    table_properties={"quality": "gold"},
    partition_cols=["dt_base"],
)
def violacoes_log():
    """Pass-through from governance_violacoes_log for API consumption."""
    return dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.governance_violacoes_log")


