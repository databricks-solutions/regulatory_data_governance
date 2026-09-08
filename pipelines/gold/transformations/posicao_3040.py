# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição SCR 3040
# MAGIC
# MAGIC Uma linha por `<Op>` em `(cnpj_if, dt_base)`:
# MAGIC `scr3040_operacoes` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos`.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/posicao_3040.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")


@dlt.table(
    name="posicao_3040",
    comment="Posição SCR 3040 — uma linha por <Op> validada, enriquecida com Res. 4966 e total de vértices",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_3040():
    # Pure ELT — quality é externa (DQX Studio), não há coluna de qualidade aqui.
    ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
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
            "pipeline_run_id",
            F.current_timestamp().alias("_gold_timestamp"),
        )
    )
