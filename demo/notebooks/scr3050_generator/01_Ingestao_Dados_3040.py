# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Ingestão dos Microdados do 3040
# MAGIC
# MAGIC Consome as tabelas finais produzidas pelo `SCR_Doc3040_Generator/02_Transformacao_e_Regras.py`
# MAGIC (namespace `{CATALOG}.{SCHEMA}.f_3040_*`). **Nenhum microdado novo é gerado aqui** —
# MAGIC o 3050 é estritamente uma camada de consumo e agregação sobre o 3040 (Regra de Ouro #1).
# MAGIC
# MAGIC | Tabela 3040 consumida     | Uso no 3050                                           |
# MAGIC |---------------------------|-------------------------------------------------------|
# MAGIC | `f_3040_clientes`         | `tp` → segmento (pesFisica/pesJuridica)              |
# MAGIC | `f_3040_operacoes`        | `mod` → modalidade; `indx` → encargo; `vlr_op`, `tax_eft`, `dt_contr`, `dt_venc_op` |
# MAGIC | `f_3040_vencimentos`      | Buckets v110..v180 → saldo a vencer                  |
# MAGIC
# MAGIC O resultado é uma única tabela denormalizada `stg_3050_microdados_from_3040`
# MAGIC com 1 linha por operação — pronta para o motor de agregação do notebook 02.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Equivalencia

# COMMAND ----------

from pyspark.sql import functions as F

# Leitura das tabelas 3040 finais. Parâmetro SRC_PREFIX_3040 vem do widget (00).
df_cli = spark.table(SRC_PREFIX_3040 + "clientes")
df_ops = spark.table(SRC_PREFIX_3040 + "operacoes")
df_venc = spark.table(SRC_PREFIX_3040 + "vencimentos")

print(f"Clientes 3040: {df_cli.count()}")
print(f"Operações 3040: {df_ops.count()}")
print(f"Vencimentos 3040: {df_venc.count()}")

# Sanity check — se zero, o pipeline do 3040 não rodou ou escreveu em outro schema.
assert df_ops.count() > 0, (
    f"Nenhuma operação encontrada em {SRC_PREFIX_3040}operacoes. "
    f"Rode primeiro o job `scr3040_generator` (task transformacao_e_regras)."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Join operações × clientes × vencimentos
# MAGIC Produz um DataFrame denormalizado com todos os atributos necessários para
# MAGIC derivar `(modalidade_3050, segmento_3050, encargo_3050)` no notebook 02.

# COMMAND ----------

# Reduz df_cli às colunas que alimentam o 3050 — `tp` (Anexo 11) e `porte_cli` (Anexo 13)
df_cli_slim = df_cli.select(
    F.col("cli_cd"),
    F.col("tp").alias("cli_tp"),
    F.col("porte_cli"),
)

# Soma dos buckets a vencer → saldo devedor total da operação
# (equivalente ao `vlr_op` do 3040, mas derivado do <Venc> que é a fonte canônica
# para a massa aberta por prazo).
cols_v = [c for c in df_venc.columns if c.startswith("v")]
df_venc_sum = df_venc.select(
    "op_id",
    sum(F.coalesce(F.col(c), F.lit(0.0)) for c in cols_v).alias("saldo_por_venc"),
    *cols_v,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Denormalização final
# MAGIC Colunas relevantes para a agregação do 3050:
# MAGIC - **Chaves 3050:** `cli_tp` (→segmento), `mod` (→modalidade), `indx`/`var_camb` (→encargo).
# MAGIC - **Métricas:** `vlr_op`, `tax_eft`, `dt_contr`, `dt_venc_op`.
# MAGIC - **Prazo contratual remanescente:** `dt_venc_op − dt_base` (p/ prazo médio §6.3).
# MAGIC - **Faixas de atraso:** derivadas dos buckets `v1xx` (todas consideradas a vencer no MVP).

# COMMAND ----------

dt_base_col = F.to_date(F.lit(DT_BASE + "-01"))

df_micro = (
    df_ops
    .join(df_cli_slim, on="cli_cd", how="inner")
    .join(df_venc_sum, on="op_id", how="left")
    .withColumn("dt_base_mes", dt_base_col)
    .withColumn(
        "prazo_remanescente_dias",
        F.datediff(F.col("dt_venc_op"), dt_base_col),
    )
    # Saldo ativo = max(saldo_por_venc, vlr_op) — no MVP do 3040 eles coincidem,
    # mas usamos a soma dos buckets como fonte canônica para evitar drift.
    .withColumn(
        "saldo_ativo",
        F.coalesce(F.col("saldo_por_venc"), F.col("vlr_op")),
    )
    # Concessões no mês: operações com dt_contr dentro do mês corrente.
    .withColumn(
        "is_concessao_mes",
        F.date_format(F.col("dt_contr"), "yyyy-MM") == F.lit(DT_BASE),
    )
    .select(
        "cli_cd", "cli_tp", "porte_cli",
        "op_id", "contrt", "ipoc",
        "mod", "natu_op", "origem_rec", "indx", "var_camb", "carac_especial",
        "dt_contr", "dt_venc_op", "prazo_remanescente_dias",
        F.col("tax_eft").alias("taxa_juros_am"),        # taxa efetiva mensal
        F.col("vlr_op").alias("vlr_op_3040"),
        "saldo_ativo", "saldo_por_venc", "is_concessao_mes",
    )
)

print(f"Microdados denormalizados: {df_micro.count()} operações.")
df_micro.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persistência staging para o notebook 02

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

stg_table = f"{CATALOG}.{SCHEMA}.stg_3050_microdados_from_3040"
(df_micro.write
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(stg_table))

print(f"Staging gravado: {stg_table} ({df_micro.count()} linhas)")

# Controle de consistência 3040 vs fonte consumida — registrado para auditoria.
total_3040 = df_ops.agg(F.sum("vlr_op").alias("s")).collect()[0]["s"]
total_3050_src = df_micro.agg(F.sum("saldo_ativo").alias("s")).collect()[0]["s"]
print(f"[Consistência 3040→3050] Saldo total 3040={total_3040:.2f} | fonte 3050={total_3050_src:.2f}")
