# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Posição CADOC 4060 → `gold.posicao_4060`
# MAGIC
# MAGIC A posição do 4060 é o bloco `consolidadoPrudencial` — o número que representa
# MAGIC o conglomerado. Os outros blocos são as parcelas que o compõem e ficam na
# MAGIC silver.
# MAGIC
# MAGIC `saldo` é apelido de `saldo_consolidado`, para esta tabela ficar comparável a
# MAGIC `gold.posicao_4010` (batimento 4060 × 4010, crítica I1).
# MAGIC
# MAGIC O 4060 é MENSAL, então entra em `gold.processing_state` — ao contrário do
# MAGIC 4016, que é semestral.

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

fqn = f"{CATALOG}.{GOLD_SCHEMA}.posicao_4060"
(
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr4060_saldos_consolidado")
    .filter(F.col("bloco") == "consolidadoPrudencial")
    .withColumn("saldo", F.col("saldo_consolidado"))
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
