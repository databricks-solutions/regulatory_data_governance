# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze DLT/SDP — CADOC 4010 (Balancete COSIF) CSV Ingestion
# MAGIC
# MAGIC Versão declarativa (`@dlt.table`) do bronze 4010. Produz a MESMA tabela
# MAGIC `raw_cosif_saldos` e o mesmo contrato que o notebook clássico
# MAGIC `pipelines/classical/bronze/raw_4010.py` — diferindo só no I/O
# MAGIC (`@dlt.table` vs `writeStream.toTable`).
# MAGIC
# MAGIC O COSIF Doc 4010 é tabular → Auto Loader CSV (`cloudFiles.format=csv`).
# MAGIC Checkpoint DISTINTO do modo clássico (`bronze_4010_csv`).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DecimalType


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


DOC_4010_CSV = StructType([
    StructField("cnpj_if", StringType()),
    StructField("dt_base", StringType()),
    StructField("cosif_conta", StringType()),
    StructField("cosif_descricao", StringType()),
    StructField("saldo_credor", DecimalType(17, 2)),
    StructField("saldo_devedor", DecimalType(17, 2)),
    StructField("saldo_liquido", DecimalType(17, 2)),
    StructField("tp_conta", StringType()),
])


@dlt.table(
    name="raw_cosif_saldos",
    comment="CADOC 4010 (Balancete COSIF) — saldos por conta ingestados via Auto Loader CSV. Layout baseado no modelo COSIF (docs/spec §2.7). Base do batimento inter-CADOC 3040×COSIF.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_cosif_saldos():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = _conf("landing_path_4010", f"/Volumes/{catalog}/{schema}/scr_xml/4010/")
    schema_location = _conf("schema_location_4010", f"/Volumes/{catalog}/{schema}/_checkpoints/bronze_4010_csv/")

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

    return (
        raw.select(
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
