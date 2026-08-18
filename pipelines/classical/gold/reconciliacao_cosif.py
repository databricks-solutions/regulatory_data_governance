# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Batimento SCR 3040 × COSIF 4010 → `gold.reconciliacao_cosif`
# MAGIC
# MAGIC Dimensão VIII (Consistência), crítica N01. Para cada regra em
# MAGIC `reference.cosif_contas`, soma o saldo do 3040 (via `predicado_3040`) e
# MAGIC compara ao saldo COSIF do 4010. Status APROVADO / ALERTA / BLOQUEADO
# MAGIC conforme a tolerância. Schema em `docs/spec/03_data_model.md` §4.3.
# MAGIC
# MAGIC Lê a SILVER dos dois CADOCs → paralelo às tasks de posição.
# MAGIC
# MAGIC ⚠️ Mapeamento rubrica↔filtro REPRESENTATIVO (subconjunto T/M) — simulação,
# MAGIC não o batimento COSIF completo do BACEN.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/reconciliacao_cosif.py`.

# COMMAND ----------

import uuid

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")
dbutils.widgets.text("reference_schema", "reference")

CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")
REFERENCE_SCHEMA = dbutils.widgets.get("reference_schema")

# UUID lógico do run — carimbado em reconciliacao_cosif.pipeline_run_id (auditoria).
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

TOLERANCIA_PCT = 0.10  # % — divergências acima disso bloqueiam a remessa (N01)

# COMMAND ----------

# Silver INEXISTENTE = CADOC fora deste deployment → sai sem falhar a run. Tabela
# VAZIA é outro caso: segue normal e produz o batimento com zeros.
_pernas = {
    "3040": f"{CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes",
    "4010": f"{CATALOG}.{SILVER_SCHEMA}.scr4010_saldos",
}
_ausentes = [f"{doc} ({t})" for doc, t in _pernas.items() if not spark.catalog.tableExists(t)]
if _ausentes:
    _msg = (
        "BATIMENTO NÃO EXECUTADO — perna(s) ausente(s): " + ", ".join(_ausentes)
        + ". A crítica N01 NÃO foi avaliada nesta execução."
    )
    print(f"[SKIP] {_msg}")
    dbutils.notebook.exit(_msg)

# COMMAND ----------

# Perna SCR: saldo do 3040 por rubrica (operacoes ⨝ vencimentos), agregado
# conforme o predicado de cada conta COSIF (reference.cosif_contas).
_ops = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
_venc = (
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
    .select("cnpj_if", "dt_base", "ipoc", "total_saldo", "total_limites")
)
_ops_venc = _ops.select("cnpj_if", "dt_base", "mod", "ipoc").join(
    _venc, on=["cnpj_if", "dt_base", "ipoc"], how="left"
)

_regras = [
    r.asDict()
    for r in spark.table(f"{CATALOG}.{REFERENCE_SCHEMA}.cosif_contas")
    .filter(F.col("is_ativo")).collect()
]

_scr_rows = []
for reg in _regras:
    saldo_col = reg["coluna_saldo_3040"]              # total_saldo | total_limites
    pred = reg.get("predicado_3040") or "true"
    agg = (
        _ops_venc.filter(F.expr(pred))
        .groupBy("cnpj_if", F.date_format("dt_base", "yyyy-MM").alias("dt_base"))
        .agg(F.round(F.coalesce(F.sum(saldo_col), F.lit(0.0)), 2).alias("vlr_scr"))
        .withColumn("grupo_reconciliacao", F.lit(reg["grupo_reconciliacao"]))
        .withColumn("tipo_regra", F.lit(reg["tipo_regra"]))
        .withColumn("descricao_regra", F.lit(reg["descricao"]))
        .withColumn("modalidade_3040", F.lit(reg.get("modalidade_3040")))
        .withColumn("cosif_conta", F.lit(reg["cosif_conta"]))
    )
    _scr_rows.append(agg)

scr_por_regra = _scr_rows[0]
for extra in _scr_rows[1:]:
    scr_por_regra = scr_por_regra.unionByName(extra)

# Perna COSIF: saldo (absoluto) por conta do 4010. Junta por codigo_conta
# (10 dígitos, formato oficial) = reference.cosif_contas.cosif_conta.
cosif = (
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
    .select(
        "cnpj_if",
        F.col("dt_base_mes").alias("dt_base"),
        F.col("codigo_conta").alias("cosif_conta"),
        F.abs(F.col("saldo")).cast("decimal(17,2)").alias("vlr_cosif"),
    )
)

recon = (
    scr_por_regra.alias("s")
    .join(cosif.alias("c"), on=["cnpj_if", "dt_base", "cosif_conta"], how="left")
    .withColumn("vlr_cosif", F.coalesce(F.col("vlr_cosif"), F.lit(0.0)).cast("decimal(17,2)"))
    .withColumn("vlr_scr", F.col("vlr_scr").cast("decimal(17,2)"))
    .withColumn("vlr_diferenca", (F.col("vlr_scr") - F.col("vlr_cosif")).cast("decimal(17,2)"))
    .withColumn(
        "pct_diferenca",
        F.when(F.col("vlr_cosif") == 0, F.lit(None))
         .otherwise(F.round(F.abs(F.col("vlr_diferenca")) / F.abs(F.col("vlr_cosif")) * 100, 4))
         .cast("decimal(8,4)"),
    )
    .withColumn("tolerancia_pct", F.lit(TOLERANCIA_PCT).cast("decimal(8,4)"))
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

fqn = f"{CATALOG}.{GOLD_SCHEMA}.reconciliacao_cosif"
(recon.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .partitionBy("dt_base").saveAsTable(fqn))
spark.sql(f"ALTER TABLE {fqn} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
