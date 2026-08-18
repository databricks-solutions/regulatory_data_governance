# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição SCR 3050 → `gold.posicao_3050`
# MAGIC
# MAGIC Passthrough fino: a silver já unifica diário+mensal (coluna
# MAGIC `periodicidade`), então o gold só acrescenta o timestamp de auditoria.
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/posicao_3050.py`.

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

fqn = f"{CATALOG}.{GOLD_SCHEMA}.posicao_3050"
(
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3050")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_referencia")
    .saveAsTable(fqn)
)
spark.sql(
    f"ALTER TABLE {fqn} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
