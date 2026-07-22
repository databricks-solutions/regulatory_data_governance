# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — CADOC 4010 (Balancete COSIF) CSV Ingestion (Auto Loader)
# MAGIC
# MAGIC Versão **clássica** (job + notebook PySpark) do bronze 4010. Produz a mesma
# MAGIC tabela `bronze.raw_cosif_saldos` e o mesmo contrato downstream que o
# MAGIC pipeline DLT em `pipelines/bronze/transformations/raw_4010.py`, sem
# MAGIC `import dlt`.
# MAGIC
# MAGIC Diferente do 3040/3050 (XML): o COSIF Doc 4010 é um Balancete contábil,
# MAGIC naturalmente **tabular** — ingerimos **CSV** via Auto Loader
# MAGIC (`cloudFiles.format=csv`) com schema explícito. Layout baseado no modelo
# MAGIC COSIF do repo (docs/spec/03_data_model.md §2.7); terminologia COSIF padrão.
# MAGIC
# MAGIC Checkpoints DISTINTOS do pipeline DLT (`classical_bronze_4010_*`) para não
# MAGIC colidir estado de Auto Loader ao trocar de modo.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DecimalType

# COMMAND ----------
# MAGIC %md
# MAGIC ## Parâmetros (widgets)

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

landing_path = f"/Volumes/{catalog}/{landing_schema}/scr_xml/4010/"
schema_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_4010_schema/"
checkpoint_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_4010_chk/"
target_table = f"{catalog}.{bronze_schema}.raw_cosif_saldos"

print(f"landing_path = {landing_path}")
print(f"target_table = {target_table}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema CSV (Balancete COSIF Doc 4010 — layout baseado no COSIF)
# MAGIC Colunas conforme docs/spec/03_data_model.md §2.7 (`raw_cosif_saldos`).

# COMMAND ----------

DOC_4010_CSV = StructType([
    StructField("cnpj_if", StringType()),
    StructField("dt_base", StringType()),          # AAAA-MM
    StructField("cosif_conta", StringType()),       # 7 dígitos
    StructField("cosif_descricao", StringType()),
    StructField("saldo_credor", DecimalType(17, 2)),
    StructField("saldo_devedor", DecimalType(17, 2)),
    StructField("saldo_liquido", DecimalType(17, 2)),
    StructField("tp_conta", StringType()),
])

# COMMAND ----------
# MAGIC %md
# MAGIC ## Leitura Auto Loader (CSV) + write incremental (`availableNow`)

# COMMAND ----------

raw = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "csv")
    .option("cloudFiles.schemaLocation", schema_location)
    .option("header", "true")
    .option("pathGlobFilter", "Doc4010_*.csv")
    .schema(DOC_4010_CSV)
    .load(landing_path)
)

reshaped = (
    raw.select(
        # _pk_hash conforme spec §2.7 — SHA-256 de (cnpj_if, dt_base, cosif_conta).
        F.sha2(F.concat_ws("|", "cnpj_if", "dt_base", "cosif_conta"), 256).alias("_pk_hash"),
        "cnpj_if", "dt_base", "cosif_conta", "cosif_descricao",
        "saldo_credor", "saldo_devedor", "saldo_liquido", "tp_conta",
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
        F.lit("bcb_cosif_csv").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )
)

query = (
    reshaped.writeStream
    .format("delta")
    .option("checkpointLocation", checkpoint_location)
    .option("mergeSchema", "true")
    .partitionBy("_ingestion_date")
    .trigger(availableNow=True)
    .toTable(target_table)
)
query.awaitTermination()

# Retenção de 5 anos (R.18) — paridade com o pipeline DLT.
spark.sql(
    f"ALTER TABLE {target_table} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'bronze')"
)

print(f"OK — {target_table}: {spark.table(target_table).count()} linha(s)")
