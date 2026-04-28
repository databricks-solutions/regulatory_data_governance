# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Críticas Summary Views
# MAGIC Aggregated views of validation results for dashboard consumption.
# MAGIC These tables power the "Monitor de Críticas" dashboard and the
# MAGIC governance irregularity tracking.

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


@dlt.table(
    name="quality_reconciliation_results",
    comment="Sumário dos resultados de reconciliação para a API /reconciliation/summary",
    table_properties={"quality": "gold"},
    partition_cols=["dt_base"],
    schema=f"{SOURCE_CATALOG}.{QUALITY_SCHEMA}",
)
def quality_reconciliation_results():
    """Aggregate reconciliation results for the API."""
    recon_3040_3050 = dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.reconciliacao_3040_3050")
    recon_cosif = dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.reconciliacao_cosif")

    # Summarize 3040 vs 3050
    summary_3040_3050 = (
        recon_3040_3050
        .groupBy("cnpj_if", "dt_base")
        .agg(
            F.count("*").alias("total_regras"),
            F.count(F.when(F.col("status") == "APROVADO", True)).alias("regras_aprovadas"),
            F.count(F.when(F.col("status") == "ALERTA", True)).alias("regras_alerta"),
            F.count(F.when(F.col("status") == "BLOQUEADO", True)).alias("regras_bloqueadas"),
            F.max("diferenca_percentual").alias("divergencia_maxima_pct"),
        )
        .withColumn("tipo_reconciliacao", F.lit("3040_vs_3050"))
        .withColumn(
            "status_geral",
            F.when(F.col("regras_bloqueadas") > 0, "BLOQUEADO")
            .when(F.col("regras_alerta") > 0, "ALERTA")
            .otherwise("APROVADO"),
        )
        .withColumn("status_envio", F.when(F.col("regras_bloqueadas") == 0, "LIBERADO").otherwise("BLOQUEADO"))
        .withColumn("run_timestamp", F.current_timestamp())
    )

    # Summarize COSIF
    summary_cosif = (
        recon_cosif
        .groupBy("cnpj_if", "dt_base")
        .agg(
            F.count("*").alias("total_regras"),
            F.count(F.when(F.col("status") == "APROVADO", True)).alias("regras_aprovadas"),
            F.count(F.when(F.col("status") == "ALERTA", True)).alias("regras_alerta"),
            F.count(F.when(F.col("status") == "BLOQUEADO", True)).alias("regras_bloqueadas"),
            F.max("pct_diferenca").alias("divergencia_maxima_pct"),
        )
        .withColumn("tipo_reconciliacao", F.lit("3040_vs_cosif"))
        .withColumn(
            "status_geral",
            F.when(F.col("regras_bloqueadas") > 0, "BLOQUEADO")
            .when(F.col("regras_alerta") > 0, "ALERTA")
            .otherwise("APROVADO"),
        )
        .withColumn("status_envio", F.when(F.col("regras_bloqueadas") == 0, "LIBERADO").otherwise("BLOQUEADO"))
        .withColumn("run_timestamp", F.current_timestamp())
    )

    return summary_3040_3050.unionByName(summary_cosif, allowMissingColumns=True)
