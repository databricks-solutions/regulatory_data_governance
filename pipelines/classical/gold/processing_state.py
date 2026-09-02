# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Estado de processamento → `gold.processing_state`
# MAGIC
# MAGIC Uma linha. Alimenta o seletor de Data-Base do app
# MAGIC (`GET /dashboard/data-bases`), que é **mensal e compartilhado** — não há
# MAGIC data-base por documento.
# MAGIC
# MAGIC Cada CADOC contribui com o **mês** da sua data-base; o mês vigente é o maior
# MAGIC deles e `current_data_base` é o maior `dt_base` dentro dele. É essa redução
# MAGIC que acomoda o **DDR (diário)** sem tratamento especial: suas várias datas no
# MAGIC mês colapsam. Sendo remetido todo dia útil, normalmente é o DDR que define o
# MAGIC mês vigente — correto para um mês em andamento.
# MAGIC
# MAGIC ⚠️ `posicao_4016` fica FORA: semestral (jun/dez), empurraria o seletor para
# MAGIC um mês sem posição dos demais CADOCs.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/processing_state.py`.

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("gold_schema", "gold")

CATALOG = dbutils.widgets.get("catalog")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")

# Posições que definem o ciclo MENSAL. `posicao_4016` não entra (ver o cabeçalho).
_CADOCS_MENSAIS = [
    "posicao_3040",
    "posicao_3050",
    "posicao_4010",
    # O 4060 é MENSAL, então entra. O 4016 continua FORA: é semestral e
    # empurraria o seletor para um mês sem posição dos demais CADOCs.
    "posicao_4060",
    "posicao_2011",
]

# COMMAND ----------

# Só as posições que EXISTEM contribuem: um deployment pode ter só um subconjunto
# dos CADOCs ativo, e aí a posição ausente é falta de escopo, não erro.
contribuicoes = None
for nome in _CADOCS_MENSAIS:
    fqn_posicao = f"{CATALOG}.{GOLD_SCHEMA}.{nome}"
    if not spark.catalog.tableExists(fqn_posicao):
        print(f"[SKIP] {fqn_posicao} não existe — CADOC fora deste deployment.")
        continue
    parcela = spark.table(fqn_posicao).select("dt_base")
    contribuicoes = parcela if contribuicoes is None else contribuicoes.unionByName(parcela)
    print(f"  + {fqn_posicao}")

if contribuicoes is None:
    raise RuntimeError(
        f"Nenhuma posição mensal existe em {CATALOG}.{GOLD_SCHEMA} "
        f"({', '.join(_CADOCS_MENSAIS)}) — rode ao menos uma task de posição antes."
    )

contribuicoes = contribuicoes.withColumn("_mes", F.trunc(F.col("dt_base"), "month"))
mes_vigente = contribuicoes.agg(F.max("_mes").alias("_mes_vigente"))

processing_state = (
    contribuicoes.join(
        F.broadcast(mes_vigente),
        contribuicoes["_mes"] == F.col("_mes_vigente"),
    )
    .agg(F.max("dt_base").alias("current_data_base"))
    .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
    .withColumn("updated_at", F.current_timestamp())
)

fqn = f"{CATALOG}.{GOLD_SCHEMA}.processing_state"
(
    processing_state.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(fqn)
)
spark.sql(f"ALTER TABLE {fqn} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
