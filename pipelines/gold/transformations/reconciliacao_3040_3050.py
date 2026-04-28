# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Reconciliation: SCR 3040 vs 3050 and 3040 vs COSIF
# MAGIC Cross-document reconciliation using modality equivalence mapping.
# MAGIC Also includes COSIF Doc 4010 batimento rules (T02-T10, M01-M18).

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze") if "source_schema" in spark.conf else "bronze"

TOLERANCE_PCT_3040_3050 = 0.5  # 0.5% tolerance for 3040 vs 3050
TOLERANCE_PCT_COSIF = 0.1  # 0.1% tolerance for COSIF batimento


# ── 3040 vs 3050 Reconciliation ──────────────────────────────────────────────

@dlt.table(
    name="reconciliacao_3040_3050",
    comment="Reconciliação cruzada SCR 3040 (individual) vs SCR 3050 (agregado) por modalidade equivalente",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def reconciliacao_3040_3050():
    # Aggregate 3040 saldo by mod_3050_equiv (using equivalence mapping)
    pos_3040 = dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.posicao_mensal_3040")

    saldo_3040 = (
        pos_3040
        .filter(F.col("mod_3050_equiv").isNotNull())
        .groupBy("cnpj_if", "dt_base", "mod_3050_equiv")
        .agg(F.sum("vlr_contr").alias("saldo_3040"))
    )

    # Aggregate 3050 by modalidade on last DU of month
    calendar = spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.bcb_calendar")
    ultimo_du = (
        calendar
        .filter((F.col("is_dia_util") == True) & (F.col("is_ultimo_du_mes") == True))
        .select(F.col("data").alias("dt_referencia"))
    )

    diario_3050 = dlt.read(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_diario")
    saldo_3050 = (
        diario_3050
        .join(ultimo_du, on="dt_referencia", how="inner")
        .groupBy("cnpj_if", F.date_format("dt_referencia", "yyyy-MM").alias("dt_base"), "modalidade")
        .agg(F.sum("sld_car_ativa").alias("saldo_3050_rmill"))
    )

    # Equivalence mapping
    equiv = spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.modalidades_equivalencia").select(
        "mod_3040", "modalidade_3050", "segmento_3050",
    )

    # Join and compute divergences
    recon = (
        saldo_3040
        .join(
            saldo_3050,
            (saldo_3040.cnpj_if == saldo_3050.cnpj_if)
            & (saldo_3040.dt_base == saldo_3050.dt_base)
            & (saldo_3040.mod_3050_equiv == saldo_3050.modalidade),
            "full_outer",
        )
        .select(
            F.coalesce(saldo_3040.cnpj_if, saldo_3050.cnpj_if).alias("cnpj_if"),
            F.coalesce(saldo_3040.dt_base, saldo_3050.dt_base).alias("dt_base"),
            F.lit(None).cast("date").alias("dt_referencia_3050"),
            F.lit("").alias("modalidade_3040"),
            F.coalesce(saldo_3040.mod_3050_equiv, saldo_3050.modalidade).alias("modalidade_3050"),
            F.lit("").alias("segmento_3050"),
            F.coalesce(F.col("saldo_3040"), F.lit(0)).alias("saldo_3040"),
            F.coalesce(F.col("saldo_3050_rmill"), F.lit(0)).alias("saldo_3050_rmill"),
            (F.coalesce(F.col("saldo_3050_rmill"), F.lit(0)) * 1000).alias("saldo_3050_reais"),
        )
        .withColumn(
            "diferenca_absoluta",
            F.abs(F.col("saldo_3040") - F.col("saldo_3050_reais")),
        )
        .withColumn(
            "diferenca_percentual",
            F.when(
                F.col("saldo_3040") > 0,
                F.round(F.col("diferenca_absoluta") / F.col("saldo_3040") * 100, 4),
            ).otherwise(0),
        )
        .withColumn("tolerancia_pct", F.lit(TOLERANCE_PCT_3040_3050))
        .withColumn(
            "status",
            F.when(F.col("diferenca_percentual") <= 0.1, "APROVADO")
            .when(F.col("diferenca_percentual") <= TOLERANCE_PCT_3040_3050, "ALERTA")
            .otherwise("BLOQUEADO"),
        )
        .withColumn("equivalencia_regra_especial", F.lit(None).cast("string"))
        .withColumn("pipeline_run_id", F.lit("pipeline"))
        .withColumn("rec_timestamp", F.current_timestamp())
    )

    return recon


# ── 3040 vs COSIF Reconciliation ─────────────────────────────────────────────

@dlt.table(
    name="reconciliacao_cosif",
    comment="Reconciliação SCR 3040 vs Balancete COSIF (Doc 4010) — regras T02-T10 e M01-M18",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def reconciliacao_cosif():
    pos_3040 = dlt.read(f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.posicao_mensal_3040")
    cosif = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_cosif_saldos")
    cosif_contas = spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.cosif_contas")

    # Aggregate 3040 saldo by COSIF account
    saldo_3040_by_cosif = (
        pos_3040
        .filter(F.col("cosif").isNotNull())
        .groupBy("cnpj_if", "dt_base", "cosif")
        .agg(F.sum("vlr_contr").alias("vlr_scr"))
    )

    # Get COSIF balances
    saldo_cosif = (
        cosif
        .select("cnpj_if", "dt_base", "cosif_conta", "saldo_liquido")
    )

    # Join with reconciliation rule mappings
    recon_rules = (
        cosif_contas
        .select("cosif_conta", "grupo_reconciliacao", "descricao", "sinal_soma")
    )

    # Build reconciliation by joining SCR → COSIF per rule
    joined = (
        saldo_3040_by_cosif
        .join(
            recon_rules,
            saldo_3040_by_cosif.cosif == recon_rules.cosif_conta,
            "inner",
        )
        .join(
            saldo_cosif,
            (saldo_3040_by_cosif.cnpj_if == saldo_cosif.cnpj_if)
            & (saldo_3040_by_cosif.dt_base == saldo_cosif.dt_base)
            & (recon_rules.cosif_conta == saldo_cosif.cosif_conta),
            "left",
        )
    )

    return (
        joined
        .groupBy(
            saldo_3040_by_cosif.cnpj_if.alias("cnpj_if"),
            saldo_3040_by_cosif.dt_base.alias("dt_base"),
            "grupo_reconciliacao",
        )
        .agg(
            F.first("descricao").alias("descricao_regra"),
            F.sum("vlr_scr").alias("vlr_scr"),
            F.sum(F.coalesce(F.col("saldo_liquido"), F.lit(0)) * F.col("sinal_soma")).alias("vlr_cosif"),
        )
        .withColumn(
            "tipo_regra",
            F.when(F.col("grupo_reconciliacao").startswith("T"), "T").otherwise("M"),
        )
        .withColumn("codigo_regra", F.col("grupo_reconciliacao"))
        .withColumn("modalidade_3040", F.lit(None).cast("string"))
        .withColumn("cosif_conta", F.lit(None).cast("string"))
        .withColumn("contas_cosif_utilizadas", F.lit(None).cast("array<string>"))
        .withColumn("vlr_diferenca", F.abs(F.col("vlr_scr") - F.col("vlr_cosif")))
        .withColumn(
            "pct_diferenca",
            F.when(F.col("vlr_cosif") != 0, F.round(F.col("vlr_diferenca") / F.abs(F.col("vlr_cosif")) * 100, 4))
            .otherwise(0),
        )
        .withColumn("tolerancia_pct", F.lit(TOLERANCE_PCT_COSIF))
        .withColumn(
            "status",
            F.when(F.col("pct_diferenca") <= 0.01, "APROVADO")
            .when(F.col("pct_diferenca") <= TOLERANCE_PCT_COSIF, "ALERTA")
            .otherwise("BLOQUEADO"),
        )
        .withColumn("pipeline_run_id", F.lit("pipeline"))
        .withColumn("rec_timestamp", F.current_timestamp())
    )
