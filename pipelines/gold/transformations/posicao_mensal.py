# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição SCR 3040 e Posição 3050
# MAGIC
# MAGIC Two gold-layer "position" tables ready for the Databricks App, dashboards
# MAGIC and downstream consumers:
# MAGIC
# MAGIC | Table | Source | One row per |
# MAGIC |---|---|---|
# MAGIC | `posicao_3040` | silver `scr3040_operacoes` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos` | `<Op>` per `(cnpj_if, dt_base)` with Res. 4966 contábil + total_saldo |
# MAGIC | `posicao_3050` | silver `scr3050` (passthrough + `_gold_timestamp`) | `(cnpj_if, dt_base, dt_referencia, periodicidade, carteira, segmento, encargo, modalidade)` |
# MAGIC
# MAGIC Note: `posicao_3050` is a deliberately thin passthrough — the silver table
# MAGIC already carries diário+mensal in a unified schema (column `periodicidade`),
# MAGIC so gold only adds the timestamp columns required for downstream audit.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")


# ── Posição SCR 3040 ──────────────────────────────────────────────────────────

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
    # Pure ELT passthrough — silver é puro normalizado (sem DQX inline). Quality
    # é gerenciada externamente pelo DQX Studio; gold simplesmente promove os
    # registros silver para as posições que App/dashboards consomem.
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


# ── Posição SCR 3050 (passthrough do silver unificado) ───────────────────────

@dlt.table(
    name="posicao_3050",
    comment="Posição SCR 3050 — passthrough de silver.scr3050 (diário+mensal já unificados via periodicidade), adicionando timestamp de gold",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_referencia"],
)
def posicao_3050():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )


# ── Estado de processamento (data-base corrente) ─────────────────────────────
# O app usa este valor para preencher o seletor de Data-Base com o ÚLTIMO CADOC
# processado, em vez de uma lista hardcoded. Gravado aqui (no pipeline gold, que
# escreve no schema gold) porque cada pipeline DLT escreve em UM único schema —
# não podemos escrever em reference/ daqui. Uma única linha, recalculada a cada
# run como o MAX(dt_base) observado nas posições 3040/3050.

@dlt.table(
    name="processing_state",
    comment="Estado de processamento do pipeline gold — data-base do último CADOC processado (MAX dt_base 3040/3050). Consumido pelo app para o seletor de Data-Base.",
    table_properties={"quality": "gold"},
)
def processing_state():
    # dlt.read (não spark.table) para tabelas do MESMO pipeline: garante que o
    # DLT ordene este cálculo DEPOIS de posicao_3040/3050 materializarem.
    p3040 = dlt.read("posicao_3040").select("dt_base")
    p3050 = dlt.read("posicao_3050").select("dt_base")
    return (
        p3040.unionByName(p3050)
        .agg(F.max("dt_base").alias("current_data_base"))
        .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
        .withColumn("updated_at", F.current_timestamp())
    )
