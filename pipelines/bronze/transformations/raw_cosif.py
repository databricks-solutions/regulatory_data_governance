# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — COSIF Raw Ingestion
# MAGIC Ingests raw COSIF accounting balances (Doc 4010) for T02-T10 and M01-M18 reconciliation.

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SOURCE_SCHEMA = spark.conf.get("source_schema", "landing")


@dlt.table(
    name="raw_cosif_saldos",
    comment="Balancete COSIF (Documento 4010) para batimento com o SCR 3040 — regras T02-T10 e M01-M18",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_cosif_saldos():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_cosif_saldos")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_cosif/saldos/")
        .select(
            "*",
            F.lit("mainframe_db2").alias("_source_system"),
            F.lit("COSIF_BALANCETE_4010").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(F.concat_ws("|", F.col("cnpj_if"), F.col("dt_base"), F.col("cosif_conta")), 256),
        )
    )
