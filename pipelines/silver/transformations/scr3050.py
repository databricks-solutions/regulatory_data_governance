# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — SCR 3050 / DocTXB (XML-derived)
# MAGIC
# MAGIC Reads `bronze.raw_3050_doc` and explodes the parsed `<diario>` + `<mensal>`
# MAGIC arrays into a SINGLE silver table, `scr3050`. Cada linha carrega as quatro
# MAGIC dimensões BACEN resolvidas a partir da hierarquia de elementos do XML +
# MAGIC `periodicidade ∈ {diario, mensal}` para que os mesmos consumidores
# MAGIC downstream funcionem com um schema único.
# MAGIC
# MAGIC Pure ELT — bronze→silver. Quality é gerenciada externamente pelo DQX
# MAGIC Studio (Databricks App externa embarcada via iframe na rota `/rules`).

# COMMAND ----------


import uuid

import dlt
from pyspark.sql import functions as F


SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

# UUID logical-run identifier carimbado em cada linha de `scr3050` via
# `pipeline_run_id`. Útil para customers correlacionarem qual execução do
# pipeline produziu um lote específico (debug + auditoria).
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"


# ── Build do DataFrame de entrada ────────────────────────────────────────────


def _bronze():
    return dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3050_doc")


def _explode(period: str):
    """Explode either `diario` or `mensal` array, propagating header attrs."""
    return (
        _bronze()
        .select(
            F.col("file_name"),
            F.col("file_path"),
            F.col("header.cnpj_if").alias("cnpj_if"),
            F.col("header.dt_base").alias("dt_base"),
            F.col("header.ind_remessa").alias("ind_remessa"),
            F.col("header.dt_referencia").alias("dt_referencia"),
            F.col("header.nm_contato").alias("nm_contato"),
            F.col("header.tel_contato").alias("tel_contato"),
            F.lit(period).alias("periodicidade"),
            F.explode(F.col(period)).alias("rec"),
        )
    )


def _build_scr3050_df():
    """Reconstrói o DataFrame normalizado (diário + mensal) com schema unificado."""
    diario = (
        _explode("diario")
        .select(
            "file_name", "cnpj_if", "dt_base", "ind_remessa", "dt_referencia", "periodicidade",
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            # diário-only metrics
            F.col("rec.tx_med_juros").alias("tx_med_juros"),
            F.col("rec.tx_med_enc_fiscais").alias("tx_med_enc_fiscais"),
            F.col("rec.tx_med_enc_operacionais").alias("tx_med_enc_operacionais"),
            F.col("rec.vlr_concessoes").alias("vlr_concessoes"),
            F.col("rec.prz_dec_med_concessoes").alias("prz_dec_med_concessoes"),
            F.col("rec.sld_car_ativa").alias("sld_car_ativa"),
            # mensal-only metrics → null on diário rows
            F.lit(None).cast("decimal(18,0)").alias("sld_bai_prejuizo"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate14"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate60"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate90"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_maior90"),
            F.lit(None).cast("integer").alias("prz_med_carteira"),
        )
    )

    mensal = (
        _explode("mensal")
        .select(
            "file_name", "cnpj_if", "dt_base", "ind_remessa", "dt_referencia", "periodicidade",
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            # diário-only metrics → null on mensal rows
            F.lit(None).cast("decimal(8,2)").alias("tx_med_juros"),
            F.lit(None).cast("decimal(8,2)").alias("tx_med_enc_fiscais"),
            F.lit(None).cast("decimal(8,2)").alias("tx_med_enc_operacionais"),
            F.lit(None).cast("decimal(18,0)").alias("vlr_concessoes"),
            F.lit(None).cast("integer").alias("prz_dec_med_concessoes"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ativa"),
            # mensal-only metrics
            F.col("rec.sld_bai_prejuizo").alias("sld_bai_prejuizo"),
            F.col("rec.sld_car_ate14").alias("sld_car_ate14"),
            F.col("rec.sld_car_ate60").alias("sld_car_ate60"),
            F.col("rec.sld_car_ate90").alias("sld_car_ate90"),
            F.col("rec.sld_car_maior90").alias("sld_car_maior90"),
            F.col("rec.prz_med_carteira").alias("prz_med_carteira"),
        )
    )

    return (
        diario.unionByName(mensal)
        .withColumn(
            "sld_car_total",
            F.when(
                F.col("periodicidade") == "mensal",
                F.coalesce(F.col("sld_car_ate14"), F.lit(0))
                + F.coalesce(F.col("sld_car_ate60"), F.lit(0))
                + F.coalesce(F.col("sld_car_ate90"), F.lit(0))
                + F.coalesce(F.col("sld_car_maior90"), F.lit(0)),
            ).otherwise(F.lit(None).cast("decimal(18,0)")),
        )
        .withColumn("leiaute_versao", F.lit("V11"))
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Tabela única scr3050 ─────────────────────────────────────────────────────


@dlt.table(
    name="scr3050",
    comment=(
        "SCR 3050 unificado — 1 linha por (carteira, segmento, encargo, modalidade) "
        "com periodicidade='diario'|'mensal'; colunas exclusivas de cada periodicidade "
        "ficam nulas na outra."
    ),
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
def scr3050():
    return _build_scr3050_df()
