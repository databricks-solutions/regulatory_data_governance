# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Governance Quality Scorecard + Violações (Monthly)
# MAGIC
# MAGIC Aggregates per-run quality scores into the monthly governance scorecard
# MAGIC consumed by the App and dashboards. Two tables only:
# MAGIC
# MAGIC | Table | Source | Consumed by |
# MAGIC |---|---|---|
# MAGIC | `qualidade_dimensoes_mensal` | silver `quality_scorecard` ⨝ reference `dimensoes_r18` | App `/quality/dimensions`, dashboards |
# MAGIC | `violacoes_log` | silver `criticas_results` (failures + alerts) | App `/governance/irregularities`, semi-annual report |
# MAGIC
# MAGIC Each `qualidade_dimensoes_mensal` row carries the latest score for a
# MAGIC `(dt_base, documento, dimensao_id)` combination plus dimension-name metadata
# MAGIC and a VERDE/AMARELO/VERMELHO status — the table is directly the contract the
# MAGIC App reads, no intermediate `governance_*` view needed.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F, Window

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
# quality_scorecard / criticas_results live in the silver pipeline (DLT
# pipelines target a single schema). Read them via spark.table() — dlt.read()
# only works for tables defined in THIS pipeline.
QUALITY_SOURCE_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")


@dlt.table(
    name="qualidade_dimensoes_mensal",
    comment="Pontuação mensal das 12 dimensões R.18 — base para App /quality/dimensions, dashboard Conformidade e relatório semestral",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def qualidade_dimensoes_mensal():
    """Latest quality score per dimension per data-base, joined with dimension metadata."""
    scorecard = spark.table(f"{SOURCE_CATALOG}.{QUALITY_SOURCE_SCHEMA}.quality_scorecard")

    # Get the latest run per dimension per dt_base
    latest = (
        scorecard
        .withColumn(
            "rn",
            F.row_number().over(
                Window.partitionBy("dt_base", "dimensao_id")
                .orderBy(F.col("run_timestamp").desc())
            ),
        )
        .filter(F.col("rn") == 1)
        .drop("rn")
    )

    # Enrich with dimension names from reference
    dims = spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.dimensoes_r18").select(
        F.col("dimensao_id").alias("dim_id"),
        "nome",
        "metrica_implementacao",
        "meta_padrao_pct",
    )

    return (
        latest
        .join(dims, latest.dimensao_id == dims.dim_id, "left")
        .select(
            "dt_base",
            F.coalesce(F.col("documento"), F.lit("3040")).alias("documento"),
            "dimensao_id",
            F.coalesce(F.col("nome"), F.lit("")).alias("dimensao_nome"),
            F.coalesce(F.col("metrica_implementacao"), F.lit("")).alias("metrica_principal"),
            (F.col("score_pct") / 100).alias("valor_metrica"),
            "score_pct",
            F.coalesce(F.col("meta_padrao_pct"), F.col("meta_pct")).alias("meta_pct"),
            F.when(F.col("score_pct") >= F.col("meta_pct"), "VERDE")
            .when(F.col("score_pct") >= F.col("meta_pct") - 5, "AMARELO")
            .otherwise("VERMELHO")
            .alias("status"),
            "total_registros",
            "registros_conformes",
            "registros_nao_conformes",
            F.lit(None).cast("string").alias("observacoes"),
            F.col("run_id").alias("pipeline_run_id"),
            F.current_timestamp().alias("calc_timestamp"),
        )
    )


@dlt.table(
    name="violacoes_log",
    comment="Log de violações de qualidade (REPROVADO + ALERTA) — base para App /governance/irregularities e relatório semestral R.18 Art. 3",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def violacoes_log():
    """Build violations log from criticas_results, filtering to failures + alerts."""
    criticas = spark.table(f"{SOURCE_CATALOG}.{QUALITY_SOURCE_SCHEMA}.criticas_results")

    return (
        criticas
        .filter(F.col("status").isin("REPROVADO", "ALERTA"))
        .select(
            F.col("run_id").alias("pipeline_run_id"),
            "dt_base",
            "documento",
            F.lit("").alias("tabela_origem"),
            F.col("critica_descricao").alias("expectation_name"),
            "critica_id",
            "dimension_r18",
            F.when(F.col("status") == "REPROVADO", "BLOQUEANTE").otherwise("ALERTA").alias("severidade"),
            F.col("registros_nao_conformes").alias("registros_afetados"),
            F.col("registros_avaliados").alias("total_registros"),
            (100 - F.col("taxa_conformidade_pct")).alias("taxa_violacao_pct"),
            F.col("sample_falhas").alias("amostra_valores"),
            F.when(F.col("status") == "REPROVADO", "QUARANTINE").otherwise("WARN").alias("acao_tomada"),
            F.lit("ABERTA").alias("status_resolucao"),
            F.lit(None).cast("string").alias("responsavel_resolucao"),
            F.lit(None).cast("timestamp").alias("dt_resolucao"),
            F.current_timestamp().alias("log_timestamp"),
        )
    )
