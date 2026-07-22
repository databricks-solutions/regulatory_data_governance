# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Motor de Saldos COSIF (agregação + injeção de divergências)
# MAGIC
# MAGIC Para cada rubrica do plano de contas (notebook 00), soma as operações 3040
# MAGIC que a ela mapeiam (via `filtro_3040`) → **saldo SCR**. O **saldo COSIF** é,
# MAGIC por construção, igual ao saldo SCR — EXCETO em ~5% das rubricas, onde
# MAGIC injetamos um desvio controlado para o batimento ter o que detectar.
# MAGIC
# MAGIC Produz `f_4010_saldos` (staging, padrão dos geradores) — uma linha por
# MAGIC rubrica COSIF, com `saldo_cosif` + `contas_agregadas`.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Plano_Contas

# COMMAND ----------

import random
from pyspark.sql import functions as F, types as T

random.seed(SEED)
micro = spark.table(f"{CATALOG}.{SCHEMA}.stg_4010_microdados")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Saldo SCR por rubrica
# MAGIC Cada rubrica: `SUM(<COL_SALDO_3040 relevante>)` sobre as operações que
# MAGIC satisfazem `filtro_3040`. T01 usa `total_saldo`; T06 usa `total_limites`.

# COMMAND ----------

def _saldo_scr(filtro_sql: str, codigo: str) -> float:
    col = "total_limites" if codigo == "T06" else "total_saldo_venc"
    row = micro.filter(F.expr(filtro_sql)).agg(F.sum(col).alias("s")).first()
    return float(row["s"] or 0.0)

# Quais rubricas recebem divergência injetada (~PCT_DIVERGENCIA das linhas).
n_div = max(1, round(len(PLANO_CONTAS_COSIF) * PCT_DIVERGENCIA)) if PCT_DIVERGENCIA > 0 else 0
idx_divergentes = set(random.sample(range(len(PLANO_CONTAS_COSIF)), n_div)) if n_div else set()

registros = []
for i, (tipo, codigo, conta, desc, mod3040, filtro) in enumerate(PLANO_CONTAS_COSIF):
    saldo_scr = round(_saldo_scr(filtro, codigo), 2)
    if i in idx_divergentes:
        # desvio controlado entre 0,5% e 3% (acima da tolerância) — para ALERTA/BLOQUEADO
        desvio = random.uniform(0.005, 0.03) * random.choice([-1, 1])
        saldo_cosif = round(saldo_scr * (1 + desvio), 2)
        injetado = True
    else:
        saldo_cosif = saldo_scr  # fecha por construção
        injetado = False
    registros.append((tipo, codigo, conta, desc, mod3040, saldo_cosif, [conta], injetado))
    tag = "  ⚠ DIVERGÊNCIA" if injetado else ""
    print(f"  {codigo:5} {conta:14} scr={saldo_scr:>15,.2f}  cosif={saldo_cosif:>15,.2f}{tag}")

print(f"\nRubricas com divergência injetada: {sorted(PLANO_CONTAS_COSIF[i][1] for i in idx_divergentes)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Materializa `f_4010_saldos`
# MAGIC Saldos COSIF — a "perna contábil" do batimento. É esta tabela que o
# MAGIC notebook 03 e a reconciliação (gold.reconciliacao_cosif) consomem.

# COMMAND ----------

schema_out = T.StructType([
    T.StructField("tipo_regra", T.StringType()),
    T.StructField("codigo_regra", T.StringType()),
    T.StructField("cosif_conta", T.StringType()),
    T.StructField("cosif_descricao", T.StringType()),
    T.StructField("modalidade_3040", T.StringType()),
    T.StructField("saldo_cosif", T.DecimalType(17, 2)),
    T.StructField("contas_agregadas", T.ArrayType(T.StringType())),
    T.StructField("_divergencia_injetada", T.BooleanType()),
])
df_saldos = (
    spark.createDataFrame(registros, schema_out)
    .withColumn("cnpj_if", F.lit(CNPJ_IF))
    .withColumn("dt_base", F.lit(DT_BASE))
    .withColumn("_gerado_em", F.current_timestamp())
)
fqn = f"{CATALOG}.{SCHEMA}.f_4010_saldos"
df_saldos.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
print(f"✓ {fqn}: {df_saldos.count()} rubricas COSIF")
