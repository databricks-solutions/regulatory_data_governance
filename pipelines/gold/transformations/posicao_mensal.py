# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição Mensal SCR 3040 e Posição 3050
# MAGIC
# MAGIC Builds two gold-layer "position" tables ready for the Databricks App, dashboards
# MAGIC and downstream consumers:
# MAGIC
# MAGIC | Table | Source | One row per |
# MAGIC |---|---|---|
# MAGIC | `posicao_mensal_3040` | silver `operacoes_validadas` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos` | `<Op>` per `(cnpj_if, dt_base)` with Res. 4966 contábil + total_saldo |
# MAGIC | `posicao_3050` | silver `scr3050_diario` ∪ `scr3050_mensal` | `(cnpj_if, dt_base, dt_referencia, periodo, carteira, segmento, encargo, modalidade)` |

# COMMAND ----------


import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")


# ── Posição Mensal SCR 3040 ───────────────────────────────────────────────────

@dlt.table(
    name="posicao_mensal_3040",
    comment="Posição mensal SCR 3040 — uma linha por <Op> validada, enriquecida com Res. 4966 e total de vértices",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_mensal_3040():
    ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.operacoes_validadas")
    cont = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_cont_4966")
        .select(
            "cnpj_if", "dt_base", "ipoc",
            "clas_at_fin", "est_inst_fin", "cart_prov_min",
            "vlr_cont_br", "tje", "rend_mes",
            "estagio_motivo", "estagio_dt_alocacao",
        )
    )
    venc = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
        .select(
            "cnpj_if", "dt_base", "ipoc",
            F.col("total_saldo").alias("total_saldo_vencimentos"),
            "total_a_vencer", "total_vencido", "total_prejuizo",
            "total_limites", "total_coobrigacoes",
        )
    )

    return (
        ops
        .join(cont, ["cnpj_if", "dt_base", "ipoc"], "left")
        .join(venc, ["cnpj_if", "dt_base", "ipoc"], "left")
        .select(
            "cnpj_if", "dt_base", "remessa", "parte",
            "cli_tp", "cli_cd", "ipoc", "contrt", "det_cli",
            "natu_op", "mod", "mod_3050_equiv", "segmento_3050_equiv",
            "origem_rec", "indx", "perc_indx", "var_camb",
            "dt_contr", "dt_venc_op", "tax_eft", "prov_consttd",
            "carac_especial", "dia_atraso",
            # Res. 4966 contábil
            "clas_at_fin", "est_inst_fin", "cart_prov_min",
            "vlr_cont_br", "tje", "rend_mes",
            "estagio_motivo", "estagio_dt_alocacao",
            # Vértices
            "total_saldo_vencimentos", "total_a_vencer", "total_vencido",
            "total_prejuizo", "total_limites", "total_coobrigacoes",
            F.col("validation_run_id").alias("pipeline_run_id"),
            F.current_timestamp().alias("_gold_timestamp"),
        )
    )


# ── Posição SCR 3050 (diário + mensal unificados) ────────────────────────────

@dlt.table(
    name="posicao_3050",
    comment="Posição SCR 3050 unificada — diário e mensal num mesmo schema, prontos para dashboard",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
def posicao_3050():
    diario = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_diario")
        .select(
            "cnpj_if", "dt_base", "dt_referencia", "ind_remessa",
            F.lit("diario").alias("periodo"),
            "carteira", "segmento", "encargo", "modalidade",
            "vlr_concessoes", "tx_med_juros",
            "tx_med_enc_fiscais", "tx_med_enc_operacionais",
            "prz_dec_med_concessoes", "sld_car_ativa",
            F.lit(None).cast("decimal(18,0)").alias("sld_bai_prejuizo"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate14"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate60"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ate90"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_maior90"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_total"),
            F.lit(None).cast("integer").alias("prz_med_carteira"),
            "leiaute_versao",
        )
    )
    mensal = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_mensal")
        .select(
            "cnpj_if", "dt_base", "dt_referencia", "ind_remessa",
            F.lit("mensal").alias("periodo"),
            "carteira", "segmento", "encargo", "modalidade",
            F.lit(None).cast("decimal(18,0)").alias("vlr_concessoes"),
            F.lit(None).cast("decimal(8,2)").alias("tx_med_juros"),
            F.lit(None).cast("decimal(8,2)").alias("tx_med_enc_fiscais"),
            F.lit(None).cast("decimal(8,2)").alias("tx_med_enc_operacionais"),
            F.lit(None).cast("integer").alias("prz_dec_med_concessoes"),
            F.lit(None).cast("decimal(18,0)").alias("sld_car_ativa"),
            "sld_bai_prejuizo", "sld_car_ate14", "sld_car_ate60",
            "sld_car_ate90", "sld_car_maior90", "sld_car_total",
            "prz_med_carteira", "leiaute_versao",
        )
    )

    return (
        diario.unionByName(mensal)
        .withColumn("_gold_timestamp", F.current_timestamp())
    )
