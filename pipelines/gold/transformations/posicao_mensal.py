# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição Mensal SCR 3040
# MAGIC Builds the monthly position snapshot from validated silver operations, enriched with
# MAGIC maturity vertex totals and reconciliation status. This table is the source for XML
# MAGIC generation and the Databricks App dashboard.

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")


@dlt.table(
    name="posicao_mensal_3040",
    comment="Posição mensal SCR 3040 — validada e reconciliada, pronta para geração XML",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_mensal_3040():
    ops = dlt.read(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.operacoes_validadas")
    venc = dlt.read(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos").select(
        "cnpj_if", "dt_base", "contrt", "ipoc", "total_saldo",
    )

    # Join operations with maturity vertex totals
    joined = ops.join(
        venc.withColumnRenamed("total_saldo", "total_saldo_vencimentos"),
        on=["cnpj_if", "dt_base", "contrt"],
        how="left",
    )

    return (
        joined
        .filter(F.col("is_valid") == True)
        .select(
            "cnpj_if",
            "dt_base",
            F.lit(1).alias("remessa"),
            F.lit(1).alias("parte"),
            "cli_tp",
            "cli_cd",
            "ipoc",
            "contrt",
            "natu_op",
            "mod",
            "mod_3050_equiv",
            "cosif",
            "prov_consttd",
            "vlr_contr",
            "tax_eft",
            "dt_venc_op",
            "dt_contr",
            "class_op",
            "total_saldo_vencimentos",
            F.lit(None).cast("string").alias("reconciliacao_cosif_status"),
            F.lit(None).cast("string").alias("reconciliacao_3050_status"),
            F.col("validation_run_id").alias("pipeline_run_id"),
            F.current_timestamp().alias("_gold_timestamp"),
        )
    )


@dlt.table(
    name="posicao_diaria_3050",
    comment="SCR 3050 — dados TXB diários e semanais reconciliados, prontos para geração XML/TXB",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base_semanal"],
)
def posicao_diaria_3050():
    diario = dlt.read(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_diario")
    mensal = dlt.read(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_mensal")

    # BCB calendar for business day counts
    calendar = spark.table(f"{SOURCE_CATALOG}.reference.bcb_calendar")

    # Count business days per week from calendar
    weekly_du = (
        calendar
        .filter(F.col("is_dia_util") == True)
        .groupBy("dt_base_semanal")
        .agg(F.count("*").alias("dias_uteis_count"))
    )

    daily_enriched = (
        diario
        .filter(F.col("is_valid") == True)
        .join(weekly_du, on="dt_base_semanal", how="left")
        .select(
            "cnpj_if",
            "dt_base_semanal",
            F.coalesce(F.col("ind_remessa"), F.lit(1)).alias("ind_remessa"),
            "dt_referencia",
            "modalidade",
            "encargo",
            "segmento",
            "sub_modalidade",
            F.lit("diario").alias("tipo_periodo"),
            "vlr_concessoes",
            "tx_med_juros",
            "sld_car_ativa",
            "sld_cedido",
            "sld_adquirido",
            F.lit(None).cast("decimal(15,3)").alias("sld_bai_prejuizo"),
            F.lit(None).cast("decimal(15,3)").alias("sld_car_total_atraso"),
            "leiaute_versao",
            "dias_uteis_count",
            F.lit(None).cast("string").alias("reconciliacao_3040_status"),
            F.current_timestamp().alias("_gold_timestamp"),
        )
    )

    # Monthly data: last DU of each month
    monthly_enriched = (
        mensal
        .filter(F.col("is_valid") == True)
        .select(
            "cnpj_if",
            F.col("dt_referencia").alias("dt_base_semanal"),
            F.lit(1).alias("ind_remessa"),
            "dt_referencia",
            "modalidade",
            "encargo",
            "segmento",
            "sub_modalidade",
            F.lit("mensal").alias("tipo_periodo"),
            F.lit(None).cast("decimal(15,3)").alias("vlr_concessoes"),
            F.lit(None).cast("decimal(8,4)").alias("tx_med_juros"),
            F.lit(None).cast("decimal(15,3)").alias("sld_car_ativa"),
            F.lit(None).cast("decimal(15,3)").alias("sld_cedido"),
            F.lit(None).cast("decimal(15,3)").alias("sld_adquirido"),
            "sld_bai_prejuizo",
            "sld_car_total",
            F.lit("V11").alias("leiaute_versao"),
            F.lit(None).cast("int").alias("dias_uteis_count"),
            F.lit(None).cast("string").alias("reconciliacao_3040_status"),
            F.current_timestamp().alias("_gold_timestamp"),
        )
    )

    return daily_enriched.unionByName(monthly_enriched, allowMissingColumns=True)
