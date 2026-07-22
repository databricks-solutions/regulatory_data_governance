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


import uuid
import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
GOLD_SCHEMA = spark.conf.get("gold_schema", "gold")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"
_TOLERANCIA_PCT = 0.10  # batimento COSIF (N01): divergências acima disso bloqueiam


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


# ── Posição CADOC 4010 (Balancete COSIF — passthrough curado) ────────────────

@dlt.table(
    name="posicao_4010",
    comment="Posição CADOC 4010 — passthrough de silver.scr4010_saldos (Balancete COSIF) + timestamp de gold.",
    table_properties={
        "quality": "gold",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def posicao_4010():
    return (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
        .withColumn("_gold_timestamp", F.current_timestamp())
    )


# ── Batimento inter-CADOC: SCR 3040 × COSIF 4010 ─────────────────────────────
# Dimensão VIII (Consistência). Mesma lógica do notebook clássico
# (pipelines/classical/gold/posicao_mensal.py). Mapeamento rubrica↔filtro
# REPRESENTATIVO (subconjunto T/M) — simulação, não o batimento COSIF completo.

@dlt.table(
    name="reconciliacao_cosif",
    comment="Batimento SCR 3040 × COSIF Doc 4010 (crítica N01). Uma linha por regra (T/M) com vlr_scr, vlr_cosif, diferença e status APROVADO/ALERTA/BLOQUEADO. Evidência da dimensão VIII (Consistência).",
    table_properties={"quality": "gold"},
    partition_cols=["dt_base"],
)
def reconciliacao_cosif():
    ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
    venc = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
        .select("cnpj_if", "dt_base", "ipoc", "total_saldo", "total_limites")
    )
    ops_venc = ops.select("cnpj_if", "dt_base", "mod", "ipoc").join(
        venc, on=["cnpj_if", "dt_base", "ipoc"], how="left"
    )

    regras = [
        r.asDict()
        for r in spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.cosif_contas")
        .filter(F.col("is_ativo")).collect()
    ]
    scr_rows = []
    for reg in regras:
        pred = reg.get("predicado_3040") or "true"
        scr_rows.append(
            ops_venc.filter(F.expr(pred))
            .groupBy("cnpj_if", F.date_format("dt_base", "yyyy-MM").alias("dt_base"))
            .agg(F.round(F.coalesce(F.sum(reg["coluna_saldo_3040"]), F.lit(0.0)), 2).alias("vlr_scr"))
            .withColumn("grupo_reconciliacao", F.lit(reg["grupo_reconciliacao"]))
            .withColumn("tipo_regra", F.lit(reg["tipo_regra"]))
            .withColumn("descricao_regra", F.lit(reg["descricao"]))
            .withColumn("modalidade_3040", F.lit(reg.get("modalidade_3040")))
            .withColumn("cosif_conta", F.lit(reg["cosif_conta"]))
        )
    scr_por_regra = scr_rows[0]
    for extra in scr_rows[1:]:
        scr_por_regra = scr_por_regra.unionByName(extra)

    cosif = (
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
        .select(
            "cnpj_if",
            F.col("dt_base_mes").alias("dt_base"),
            "cosif_conta",
            F.abs(F.col("saldo_liquido")).cast("decimal(17,2)").alias("vlr_cosif"),
        )
    )
    return (
        scr_por_regra.join(cosif, on=["cnpj_if", "dt_base", "cosif_conta"], how="left")
        .withColumn("vlr_cosif", F.coalesce(F.col("vlr_cosif"), F.lit(0.0)).cast("decimal(17,2)"))
        .withColumn("vlr_scr", F.col("vlr_scr").cast("decimal(17,2)"))
        .withColumn("vlr_diferenca", (F.col("vlr_scr") - F.col("vlr_cosif")).cast("decimal(17,2)"))
        .withColumn(
            "pct_diferenca",
            F.when(F.col("vlr_cosif") == 0, F.lit(None))
             .otherwise(F.round(F.abs(F.col("vlr_diferenca")) / F.abs(F.col("vlr_cosif")) * 100, 4))
             .cast("decimal(8,4)"),
        )
        .withColumn("tolerancia_pct", F.lit(_TOLERANCIA_PCT).cast("decimal(8,4)"))
        .withColumn(
            "status",
            F.when(F.col("pct_diferenca").isNull() | (F.col("pct_diferenca") == 0), F.lit("APROVADO"))
             .when(F.col("pct_diferenca") <= F.col("tolerancia_pct"), F.lit("ALERTA"))
             .otherwise(F.lit("BLOQUEADO")),
        )
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("rec_timestamp", F.current_timestamp())
        .select(
            "cnpj_if", "dt_base", "tipo_regra",
            F.col("grupo_reconciliacao").alias("codigo_regra"),
            "descricao_regra", "modalidade_3040", "cosif_conta",
            "vlr_scr", "vlr_cosif", "vlr_diferenca", "pct_diferenca",
            "tolerancia_pct", "status", "pipeline_run_id", "rec_timestamp",
        )
    )


# ── Estado de processamento (data-base corrente) ─────────────────────────────
# O app usa este valor para preencher o seletor de Data-Base com o ÚLTIMO CADOC
# processado, em vez de uma lista hardcoded. Gravado aqui (no pipeline gold, que
# escreve no schema gold) porque cada pipeline DLT escreve em UM único schema —
# não podemos escrever em reference/ daqui. Uma única linha, recalculada a cada
# run como o MAX(dt_base) observado nas posições 3040/3050/4010.

@dlt.table(
    name="processing_state",
    comment="Estado de processamento do pipeline gold — data-base do último CADOC processado (MAX dt_base 3040/3050/4010). Consumido pelo app para o seletor de Data-Base.",
    table_properties={"quality": "gold"},
)
def processing_state():
    # dlt.read (não spark.table) para tabelas do MESMO pipeline: garante que o
    # DLT ordene este cálculo DEPOIS de posicao_3040/3050/4010 materializarem.
    p3040 = dlt.read("posicao_3040").select("dt_base")
    p3050 = dlt.read("posicao_3050").select("dt_base")
    p4010 = dlt.read("posicao_4010").select("dt_base")
    return (
        p3040.unionByName(p3050).unionByName(p4010)
        .agg(F.max("dt_base").alias("current_data_base"))
        .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
        .withColumn("updated_at", F.current_timestamp())
    )
