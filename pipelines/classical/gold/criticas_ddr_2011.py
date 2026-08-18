# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Críticas intra-DDR (Doc 2011) → `gold.criticas_ddr_2011`
# MAGIC
# MAGIC Das 11 críticas vigentes, só estas duas confrontam o próprio DDR (as
# MAGIC outras 9 batem contra os docs 2060/DRM e 2061/DLO, fora do escopo):
# MAGIC
# MAGIC | Crítica | Tipo | Regra |
# MAGIC |---|---|---|
# MAGIC | 4693 | E | 161000 (vendidas no PL) >= 181000 (excesso de hedge no exterior) |
# MAGIC | 4751 | I | chaves duplicadas entre posição e moeda nos detalhamentos |
# MAGIC
# MAGIC São de grão AGREGADO e a `sql_expression` do DQX roda linha a linha, então
# MAGIC materializamos com `status` e o check só olha o status — mesmo padrão da N01
# MAGIC em `reconciliacao_cosif`. Ver `docs/ddr2011/README.md`.
# MAGIC
# MAGIC Lê a SILVER, não `gold.posicao_2011` → paralelo à posição.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/criticas_ddr_2011.py`.

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")

CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")

_CRIT_OK = "OK"
_CRIT_BLOQUEADO = "BLOQUEADO"

# COMMAND ----------

contas = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr2011_contas")
detalhamentos = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr2011_detalhamentos")

# 4693 — soma de 161000 vs soma de 181000 na mesma data-base.
por_data = (
    contas.groupBy("cnpj_if", "dt_base", "data_base_month")
    .agg(
        F.sum(F.when(F.col("codigo_conta") == "161000", F.col("valor_conta")))
         .alias("vlr_esquerdo"),
        F.sum(F.when(F.col("codigo_conta") == "181000", F.col("valor_conta")))
         .alias("vlr_direito"),
    )
)
c4693 = por_data.select(
    "cnpj_if", "dt_base", "data_base_month",
    F.lit("4693").alias("critica_id"),
    F.lit("E").alias("tipo_critica"),
    F.lit(
        "Somatorio das Posicoes Vendidas no Patrimonio Liquido (161000) inferior ao "
        "Excesso da Posicao Vendida para Hedge em Participacoes no Exterior (181000)."
    ).alias("descricao_critica"),
    F.col("vlr_esquerdo").cast("decimal(17,2)").alias("vlr_esquerdo"),
    F.col("vlr_direito").cast("decimal(17,2)").alias("vlr_direito"),
    F.lit(None).cast("bigint").alias("qtd_ocorrencias"),
    # Sem uma das duas contas na remessa não há o que confrontar → OK.
    F.when(
        F.col("vlr_esquerdo").isNull() | F.col("vlr_direito").isNull(), F.lit(_CRIT_OK)
    ).when(
        F.col("vlr_esquerdo") < F.col("vlr_direito"), F.lit(_CRIT_BLOQUEADO)
    ).otherwise(F.lit(_CRIT_OK)).alias("status"),
)

# 4751 — a chave (conta, país, moeda, posição) não pode repetir na data-base.
# `count(*) - count(distinct)` = linhas excedentes, o que o BCB reporta.
dup = (
    detalhamentos.groupBy("cnpj_if", "dt_base", "data_base_month")
    .agg(
        (
            F.count(F.lit(1))
            - F.countDistinct(
                F.concat_ws(
                    "|",
                    F.col("codigo_conta"),
                    F.coalesce(F.col("pais"), F.lit("")),
                    F.coalesce(F.col("moeda"), F.lit("")),
                    F.coalesce(F.col("posicao_pais_exterior"), F.lit("")),
                )
            )
        ).alias("qtd_ocorrencias")
    )
)
c4751 = dup.select(
    "cnpj_if", "dt_base", "data_base_month",
    F.lit("4751").alias("critica_id"),
    F.lit("I").alias("tipo_critica"),
    F.lit("Chaves duplicadas entre posicao e moeda nos detalhamentos do DDR.")
     .alias("descricao_critica"),
    F.lit(None).cast("decimal(17,2)").alias("vlr_esquerdo"),
    F.lit(None).cast("decimal(17,2)").alias("vlr_direito"),
    F.col("qtd_ocorrencias").cast("bigint").alias("qtd_ocorrencias"),
    F.when(F.col("qtd_ocorrencias") > 0, F.lit(_CRIT_BLOQUEADO))
     .otherwise(F.lit(_CRIT_OK)).alias("status"),
)

fqn = f"{CATALOG}.{GOLD_SCHEMA}.criticas_ddr_2011"
(
    c4693.unionByName(c4751)
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn)
)
spark.sql(f"ALTER TABLE {fqn} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
