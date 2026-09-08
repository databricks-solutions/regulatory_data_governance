# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição CADOC 4010 → `gold.posicao_4010`
# MAGIC
# MAGIC Passthrough de `silver.scr4010_saldos` (Balancete, MENSAL) + timestamp.
# MAGIC Uma linha por conta COSIF.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/posicao_4010.py`.

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

fqn = f"{CATALOG}.{GOLD_SCHEMA}.posicao_4010"
(
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write
    .format("delta")
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
