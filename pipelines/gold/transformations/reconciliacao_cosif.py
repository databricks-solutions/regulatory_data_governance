# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Batimento inter-CADOC: SCR 3040 × COSIF 4010
# MAGIC
# MAGIC Dimensão VIII (Consistência), crítica N01. Para cada regra em
# MAGIC `reference.cosif_contas`, soma o saldo do 3040 (via `predicado_3040`) e
# MAGIC compara ao saldo COSIF do 4010. Status APROVADO / ALERTA / BLOQUEADO
# MAGIC conforme a tolerância. Lê a SILVER dos dois CADOCs.
# MAGIC
# MAGIC ⚠️ Mapeamento rubrica↔filtro REPRESENTATIVO (subconjunto T/M) — simulação,
# MAGIC não o batimento COSIF completo do BACEN.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/reconciliacao_cosif.py`,
# MAGIC menos a tolerância a silver ausente: uma `@dlt.table` tem de devolver
# MAGIC DataFrame, e devolver vazio apagaria a tabela. Em SDP é all-or-nothing.

# COMMAND ----------

import uuid

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"
_TOLERANCIA_PCT = 0.10  # % — divergências acima disso bloqueiam a remessa (N01)


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
            F.col("codigo_conta").alias("cosif_conta"),
            F.abs(F.col("saldo")).cast("decimal(17,2)").alias("vlr_cosif"),
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
