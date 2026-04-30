# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — SCR 3050 / DocTXB Validated (XML-derived)
# MAGIC
# MAGIC Reads `bronze.raw_3050_doc` and explodes the parsed `<diario>` and `<mensal>`
# MAGIC arrays into normalized rows. Each row has the four BACEN dimensions resolved
# MAGIC from the XML element-name hierarchy:
# MAGIC
# MAGIC | Dimension | XML level | Sample values |
# MAGIC |---|---|---|
# MAGIC | `carteira` | `<crdLivre>`/`<crdDirec>` | crdLivre, crdDirec |
# MAGIC | `segmento` | `<pesJuridica>`/`<pesFisica>` | pesJuridica, pesFisica |
# MAGIC | `encargo` | `<pre>`/`<flu>`/`<vc>`/`<ipca>`/`<igpm>`/`<ind>` | pre, flu, vc, ipca, igpm, ind |
# MAGIC | `modalidade` | leaf element | capGirPrzAte365, financiamentos, etc. |
# MAGIC
# MAGIC Daily rows carry `tx_med_juros`, `vlr_concessoes`, `sld_car_ativa` etc.
# MAGIC Monthly rows carry `sld_bai_prejuizo`, `sld_car_ate14/60/90/maior90`,
# MAGIC `prz_med_carteira`. Validation expectations enforce BACEN domains and
# MAGIC saldo-faixas consistency (Crítica 3018).

# COMMAND ----------


import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

ENCARGO_DOMAIN = ("pre", "flu", "vc", "ipca", "igpm", "ind")
SEGMENTO_DOMAIN = ("pesJuridica", "pesFisica")
CARTEIRA_DOMAIN = ("crdLivre", "crdDirec")


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
            F.explode(F.col(period)).alias("rec"),
        )
    )


# ── 3050 Diário ───────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_diario",
    comment="SCR 3050 diário — uma linha por (carteira, segmento, encargo, modalidade); valores em <diario>",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
@dlt.expect_or_drop("cnpj_if_valid", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("modalidade_not_null", "modalidade IS NOT NULL")
@dlt.expect_or_drop("encargo_valid", f"encargo IN {ENCARGO_DOMAIN}")
@dlt.expect_or_drop("segmento_valid", f"segmento IN {SEGMENTO_DOMAIN}")
@dlt.expect_or_drop("carteira_valid", f"carteira IN {CARTEIRA_DOMAIN}")
@dlt.expect("concessoes_positive", "vlr_concessoes IS NULL OR vlr_concessoes >= 0")
@dlt.expect("taxa_juros_range", "tx_med_juros IS NULL OR (tx_med_juros >= 0 AND tx_med_juros <= 9999.99)")
@dlt.expect("saldo_carteira_positive", "sld_car_ativa IS NULL OR sld_car_ativa >= 0")
@dlt.expect("przdec_positive", "prz_dec_med_concessoes IS NULL OR prz_dec_med_concessoes >= 0")
def scr3050_diario():
    return (
        _explode("diario")
        .select(
            "file_name", "cnpj_if", "dt_base", "ind_remessa", "dt_referencia",
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            F.col("rec.tx_med_juros").alias("tx_med_juros"),
            F.col("rec.tx_med_enc_fiscais").alias("tx_med_enc_fiscais"),
            F.col("rec.tx_med_enc_operacionais").alias("tx_med_enc_operacionais"),
            F.col("rec.vlr_concessoes").alias("vlr_concessoes"),
            F.col("rec.prz_dec_med_concessoes").alias("prz_dec_med_concessoes"),
            F.col("rec.sld_car_ativa").alias("sld_car_ativa"),
        )
        .withColumn("leiaute_versao", F.lit("V11"))
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── 3050 Mensal ───────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_mensal",
    comment="SCR 3050 mensal (último DU do mês) — saldos por faixa de atraso, baixa para prejuízo, prazo médio",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
@dlt.expect_or_drop("cnpj_if_valid", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("modalidade_not_null", "modalidade IS NOT NULL")
@dlt.expect_or_drop("encargo_valid", f"encargo IN {ENCARGO_DOMAIN}")
@dlt.expect_or_drop("segmento_valid", f"segmento IN {SEGMENTO_DOMAIN}")
@dlt.expect("saldo_faixas_consistente_3018", """
    ABS(
      COALESCE(sld_car_ate14,0) + COALESCE(sld_car_ate60,0)
      + COALESCE(sld_car_ate90,0) + COALESCE(sld_car_maior90,0)
      - COALESCE(sld_car_total,0)
    ) < 0.01
""")
@dlt.expect("prazo_medio_positive_3032", "prz_med_carteira IS NULL OR prz_med_carteira >= 0")
@dlt.expect("sld_bai_prejuizo_positive", "sld_bai_prejuizo IS NULL OR sld_bai_prejuizo >= 0")
def scr3050_mensal():
    return (
        _explode("mensal")
        .select(
            "file_name", "cnpj_if", "dt_base", "ind_remessa", "dt_referencia",
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            F.col("rec.sld_bai_prejuizo").alias("sld_bai_prejuizo"),
            F.col("rec.sld_car_ate14").alias("sld_car_ate14"),
            F.col("rec.sld_car_ate60").alias("sld_car_ate60"),
            F.col("rec.sld_car_ate90").alias("sld_car_ate90"),
            F.col("rec.sld_car_maior90").alias("sld_car_maior90"),
            F.col("rec.prz_med_carteira").alias("prz_med_carteira"),
        )
        .withColumn(
            "sld_car_total",
            F.coalesce(F.col("sld_car_ate14"), F.lit(0))
            + F.coalesce(F.col("sld_car_ate60"), F.lit(0))
            + F.coalesce(F.col("sld_car_ate90"), F.lit(0))
            + F.coalesce(F.col("sld_car_maior90"), F.lit(0)),
        )
        .withColumn("leiaute_versao", F.lit("V11"))
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── 3050 Quarentena ──────────────────────────────────────────────────────────

@dlt.table(
    name="scr3050_quarantine",
    comment="Registros SCR 3050 (diário ou mensal) rejeitados por regras bloqueantes",
    table_properties={"quality": "quarantine"},
    partition_cols=["dt_referencia"],
)
def scr3050_quarantine():
    diario = (
        _explode("diario")
        .select(
            "file_name", "cnpj_if", "dt_base", "dt_referencia",
            F.lit("diario").alias("periodo"),
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            F.to_json(F.col("rec")).alias("raw_record"),
        )
    )
    mensal = (
        _explode("mensal")
        .select(
            "file_name", "cnpj_if", "dt_base", "dt_referencia",
            F.lit("mensal").alias("periodo"),
            F.col("rec.carteira").alias("carteira"),
            F.col("rec.segmento").alias("segmento"),
            F.col("rec.encargo").alias("encargo"),
            F.col("rec.modalidade").alias("modalidade"),
            F.to_json(F.col("rec")).alias("raw_record"),
        )
    )
    union = diario.unionByName(mensal)
    return (
        union
        .filter(
            (F.length("cnpj_if") != 8)
            | F.col("modalidade").isNull()
            | (~F.col("encargo").isin(*ENCARGO_DOMAIN))
            | (~F.col("segmento").isin(*SEGMENTO_DOMAIN))
            | (~F.col("carteira").isin(*CARTEIRA_DOMAIN))
        )
        .select(
            "file_name", "cnpj_if", "dt_base", "dt_referencia", "periodo",
            "carteira", "segmento", "encargo", "modalidade", "raw_record",
            F.array(F.lit("blocking_rule")).alias("failed_expectations"),
            F.lit(None).cast("array<string>").alias("critica_ids"),
            F.lit("dlt_pipeline").alias("validation_run_id"),
            F.current_timestamp().alias("quarantine_timestamp"),
        )
    )
