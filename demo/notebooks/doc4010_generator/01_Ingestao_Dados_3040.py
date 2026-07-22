# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Ingestão dos Microdados do 3040
# MAGIC
# MAGIC Consome as tabelas finais do gerador 3040 (`f_3040_operacoes` + `f_3040_vencimentos`)
# MAGIC e produz uma tabela denormalizada `stg_4010_microdados` com 1 linha por
# MAGIC operação, contendo o **saldo** (soma dos buckets de vencimento) e os campos
# MAGIC de filtro (`mod`, `natu_op`). **Nenhum dado novo é gerado** — o 4010 é uma
# MAGIC camada de agregação contábil sobre o 3040 (mesma Regra de Ouro do 3050).

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Plano_Contas

# COMMAND ----------

from pyspark.sql import functions as F

df_ops = spark.table(SRC_PREFIX_3040 + "operacoes")
df_venc = spark.table(SRC_PREFIX_3040 + "vencimentos")

print(f"Operações 3040: {df_ops.count()}")
print(f"Vencimentos 3040: {df_venc.count()}")
assert df_ops.count() > 0, (
    f"Nenhuma operação em {SRC_PREFIX_3040}operacoes. "
    f"Rode primeiro o job `scr3040_generator` (task transformacao_e_regras)."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Saldo por operação (soma dos buckets de vencimento)
# MAGIC A soma de todos os vértices `v*` é o saldo devedor total da operação — a
# MAGIC "perna SCR" do batimento. Também derivamos `total_limites` (buckets v20/v40)
# MAGIC para a rubrica de créditos a liberar/limites (T06).

# COMMAND ----------

cols_v = [c for c in df_venc.columns if c.startswith("v") and c[1:].isdigit()]
cols_limite = [c for c in ("v20", "v40") if c in df_venc.columns]
cols_saldo = [c for c in cols_v if c not in cols_limite]

df_venc_agg = df_venc.select(
    "op_id",
    sum(F.coalesce(F.col(c), F.lit(0.0)) for c in cols_saldo).alias("total_saldo_venc"),
    (sum(F.coalesce(F.col(c), F.lit(0.0)) for c in cols_limite)
     if cols_limite else F.lit(0.0)).alias("total_limites"),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Denormalização (operação × saldo)

# COMMAND ----------

df_micro = (
    df_ops.select("op_id", "cli_cd", "mod", "natu_op")
    .join(df_venc_agg, on="op_id", how="left")
    .withColumn("total_saldo_venc", F.coalesce(F.col("total_saldo_venc"), F.lit(0.0)))
    .withColumn("total_limites", F.coalesce(F.col("total_limites"), F.lit(0.0)))
    # `total_saldo` genérico para o filtro T01 (total de créditos ativos).
    .withColumn("total_saldo", F.col("total_saldo_venc"))
    .withColumn("dt_base", F.lit(DT_BASE))
    .withColumn("cnpj_if", F.lit(CNPJ_IF))
)

fqn_micro = f"{CATALOG}.{SCHEMA}.stg_4010_microdados"
df_micro.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn_micro)
print(f"✓ {fqn_micro}: {df_micro.count()} operações | saldo total = "
      f"{df_micro.agg(F.sum('total_saldo_venc')).first()[0]:,.2f}")
