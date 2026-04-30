# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Governance Quality Scorecard (Monthly)
# MAGIC Aggregates per-run quality scores into the monthly governance scorecard
# MAGIC (`governance_status_qualidade_mensal`) used by the R.18 compliance dashboard.
# MAGIC Also maintains the violations log for the semi-annual report.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F, Window

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
QUALITY_SCHEMA = spark.conf.get("quality_schema", "quality")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")


@dlt.table(
    name="governance_status_qualidade_mensal",
    comment="Pontuação mensal das 12 dimensões R.18 — base para dashboard Conformidade e relatório semestral",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def governance_status_qualidade_mensal():
    """Aggregate latest quality scores per dimension per data-base."""
    scorecard = dlt.read(f"{SOURCE_CATALOG}.{QUALITY_SCHEMA}.quality_scorecard")

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
    name="governance_violacoes_log",
    comment="Log de todas as violações de qualidade — histórico para relatório semestral R.18 Art. 3",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def governance_violacoes_log():
    """Build violations log from criticas_results with failures."""
    criticas = dlt.read(f"{SOURCE_CATALOG}.{QUALITY_SCHEMA}.criticas_results")

    # Only log failures (REPROVADO) and alerts (ALERTA)
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
