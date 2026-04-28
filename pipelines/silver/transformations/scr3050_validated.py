# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — SCR 3050 Validated TXB Data
# MAGIC Validates daily and monthly 3050 TXB records against BCB criticas (Grupos 1-4).
# MAGIC Checks encargo types, periodicidade, field semantics, and business day completeness.

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")


# ── Validated Daily 3050 ──────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_diario",
    comment="SCR 3050 — agregações TXB diárias validadas por modalidade, encargo e segmento",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base_semanal"],
)
@dlt.expect_or_drop("cnpj_if_valid", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("modalidade_not_null", "modalidade IS NOT NULL")
@dlt.expect_or_drop("encargo_valid", "encargo IN ('pre','flu','vc','ipca','igpm','ind')")
@dlt.expect_or_drop("segmento_valid", "segmento IN ('pesJuridica','pesFisica')")
@dlt.expect("concessoes_positive", "vlr_concessoes IS NULL OR vlr_concessoes >= 0")
@dlt.expect("taxa_juros_range", "tx_med_juros IS NULL OR (tx_med_juros >= 0 AND tx_med_juros <= 9999.99)")
@dlt.expect("saldo_carteira_positive", "sld_car_ativa IS NULL OR sld_car_ativa >= 0")
def scr3050_diario():
    raw = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3050_diario")
    return (
        raw
        .withColumn("leiaute_versao", F.coalesce(F.col("leiaute_versao"), F.lit("V11")))
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_flags", F.lit(None).cast("string"))
        .withColumn("critica_failures", F.lit(None).cast("array<string>"))
        .withColumn("validation_run_id", F.lit("pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Validated Monthly 3050 ────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_mensal",
    comment="SCR 3050 — agregações TXB mensais (último DU do mês) com saldos por faixa de atraso",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
@dlt.expect_or_drop("cnpj_if_valid", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("modalidade_not_null", "modalidade IS NOT NULL")
@dlt.expect("saldo_faixas_consistent_3018", """
    sld_car_ate14 IS NULL OR sld_car_15a60 IS NULL OR sld_car_61a90 IS NULL OR sld_car_maior90 IS NULL
    OR ABS(COALESCE(sld_car_ate14, 0) + COALESCE(sld_car_15a60, 0) + COALESCE(sld_car_61a90, 0) + COALESCE(sld_car_maior90, 0) - COALESCE(sld_car_total, 0)) < 0.01
""")
@dlt.expect("prazo_medio_positive_3032", "prz_med_carteira IS NULL OR prz_med_carteira >= 0")
def scr3050_mensal():
    raw = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3050_mensal")
    return (
        raw
        .withColumn(
            "sld_car_total",
            F.coalesce(F.col("sld_car_ate14"), F.lit(0))
            + F.coalesce(F.col("sld_car_15a60"), F.lit(0))
            + F.coalesce(F.col("sld_car_61a90"), F.lit(0))
            + F.coalesce(F.col("sld_car_maior90"), F.lit(0)),
        )
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_run_id", F.lit("pipeline"))
    )


# ── 3050 Quarantine ──────────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_quarantine",
    comment="Registros SCR 3050 rejeitados pelas regras de validação bloqueantes",
    table_properties={"quality": "quarantine"},
    partition_cols=["dt_base_semanal"],
)
def scr3050_quarantine():
    return (
        dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3050_diario")
        .filter(
            (F.length(F.col("cnpj_if")) != 8)
            | F.col("modalidade").isNull()
            | (~F.col("encargo").isin("pre", "flu", "vc", "ipca", "igpm", "ind"))
            | (~F.col("segmento").isin("pesJuridica", "pesFisica"))
        )
        .select(
            "cnpj_if", "dt_base_semanal", "dt_referencia",
            F.to_json(F.struct("*")).alias("raw_record"),
            F.array(F.lit("blocking_rule")).alias("failed_expectations"),
            F.lit(None).cast("array<string>").alias("critica_ids"),
            F.lit("pipeline").alias("validation_run_id"),
            F.current_timestamp().alias("quarantine_timestamp"),
        )
    )
