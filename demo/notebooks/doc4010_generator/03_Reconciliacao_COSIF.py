# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Reconciliação SCR 3040 × COSIF 4010 (`gold.reconciliacao_cosif`)
# MAGIC
# MAGIC Materializa a tabela de batimento definida em
# MAGIC `docs/spec/03_data_model.md §4.3`. Uma linha por rubrica: valor SCR
# MAGIC (agregado do 3040) × valor COSIF (saldo do 4010) → diferença, % e status.
# MAGIC
# MAGIC É esta tabela que o check DQX `reconciliacao_cosif.yml` avalia (crítica
# MAGIC N01, dimensão 8 — Consistência). O `status` segue a tolerância configurada:
# MAGIC - **APROVADO**: |pct_diferenca| == 0
# MAGIC - **ALERTA**:   0 < |pct_diferenca| <= tolerancia_pct
# MAGIC - **BLOQUEADO**: |pct_diferenca| > tolerancia_pct
# MAGIC
# MAGIC Grava em `gold` (schema de curadoria). No bundle demo o schema `gold` pode
# MAGIC não existir; criamos se necessário.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Plano_Contas

# COMMAND ----------

from pyspark.sql import functions as F

dbutils.widgets.text("gold_schema", "gold", "Schema gold (reconciliação)")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{GOLD_SCHEMA}")

micro = spark.table(f"{CATALOG}.{SCHEMA}.stg_4010_microdados")
saldos = spark.table(f"{CATALOG}.{SCHEMA}.f_4010_saldos")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Perna SCR por rubrica (recalculada a partir do filtro)
# MAGIC Recomputamos o saldo SCR aqui para a reconciliação ser auto-contida
# MAGIC (o notebook 02 já garantiu que COSIF == SCR exceto nas divergências).

# COMMAND ----------

def _scr_por_regra():
    linhas = []
    for tipo, codigo, conta, desc, mod3040, filtro in PLANO_CONTAS_COSIF:
        col = "total_limites" if codigo == "T06" else "total_saldo_venc"
        s = micro.filter(F.expr(filtro)).agg(F.sum(col).alias("s")).first()["s"] or 0.0
        linhas.append((codigo, round(float(s), 2)))
    return {c: v for c, v in linhas}

scr_map = _scr_por_regra()
scr_df = spark.createDataFrame(
    [(k, v) for k, v in scr_map.items()], ["codigo_regra", "vlr_scr"]
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Monta a reconciliação (schema da spec §4.3)

# COMMAND ----------

rec = (
    saldos.alias("c")
    .join(scr_df.alias("s"), on="codigo_regra", how="left")
    .withColumn("vlr_scr", F.coalesce(F.col("vlr_scr"), F.lit(0.0)).cast("decimal(17,2)"))
    .withColumnRenamed("saldo_cosif", "vlr_cosif")
    .withColumn("descricao_regra", F.col("cosif_descricao"))
    .withColumn("contas_cosif_utilizadas", F.col("contas_agregadas"))
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
    .withColumn("pipeline_run_id", F.lit(f"doc4010_gen_{DT_BASE}"))
    .withColumn("rec_timestamp", F.current_timestamp())
    .select(
        "cnpj_if", "dt_base", "tipo_regra", "codigo_regra", "descricao_regra",
        "modalidade_3040", "cosif_conta", "contas_cosif_utilizadas",
        "vlr_scr", "vlr_cosif", "vlr_diferenca", "pct_diferenca",
        "tolerancia_pct", "status", "pipeline_run_id", "rec_timestamp",
    )
)

fqn = f"{CATALOG}.{GOLD_SCHEMA}.reconciliacao_cosif"
(rec.write.mode("overwrite").option("overwriteSchema", "true")
    .partitionBy("dt_base").saveAsTable(fqn))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumo do batimento

# COMMAND ----------

resumo = rec.groupBy("status").count().collect()
print(f"✓ {fqn}")
for r in sorted(resumo, key=lambda x: x["status"]):
    print(f"  {r['status']:10} : {r['count']}")
display(rec.orderBy(F.col("status").desc(), "codigo_regra"))
