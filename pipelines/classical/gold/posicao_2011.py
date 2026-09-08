# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição CADOC 2011 (DDR) → `gold.posicao_2011`
# MAGIC
# MAGIC Único CADOC DIÁRIO. Preserva o grão diário e marca `is_ultima_do_mes`
# MAGIC (fechamento — uma data-base por `cnpj_if`/mês), para o dashboard escolher
# MAGIC entre série diária e fechamento sem um modo próprio no seletor mensal.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/posicao_2011.py`.

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")

CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")

# COMMAND ----------

contas = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr2011_contas")
ultima = (
    contas.groupBy("cnpj_if", "data_base_month")
    .agg(F.max("dt_base").alias("_dt_ultima"))
)

fqn = f"{CATALOG}.{GOLD_SCHEMA}.posicao_2011"
(
    contas.join(ultima, on=["cnpj_if", "data_base_month"], how="left")
    .withColumn("is_ultima_do_mes", F.col("dt_base") == F.col("_dt_ultima"))
    .drop("_dt_ultima")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn)
)
spark.sql(
    f"ALTER TABLE {fqn} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
