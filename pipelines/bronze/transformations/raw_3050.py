# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3050 Raw Ingestion
# MAGIC Ingests raw SCR 3050 TXB data (daily and monthly) from landing zone parquet files.

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SOURCE_SCHEMA = spark.conf.get("source_schema", "landing")


@dlt.table(
    name="raw_3050_diario",
    comment="SCR 3050 — concessões e saldos diários por modalidade, encargo e segmento",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_3050_diario():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3050_diario")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3050/diario/")
        .select(
            "*",
            F.lit("batch_file_3050").alias("_source_system"),
            F.lit("TXB_DIARIO").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(
                F.concat_ws(
                    "|",
                    F.col("cnpj_if"), F.col("dt_base_semanal"), F.col("dt_referencia"),
                    F.col("modalidade"), F.col("encargo"), F.col("segmento"),
                ),
                256,
            ),
        )
    )


@dlt.table(
    name="raw_3050_mensal",
    comment="SCR 3050 — saldos mensais por faixa de atraso, prazo médio e baixa para prejuízo (último DU do mês)",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_3050_mensal():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3050_mensal")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3050/mensal/")
        .select(
            "*",
            F.lit("batch_file_3050").alias("_source_system"),
            F.lit("TXB_MENSAL").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(
                F.concat_ws("|", F.col("cnpj_if"), F.col("dt_referencia"), F.col("modalidade"), F.col("encargo"), F.col("segmento")),
                256,
            ),
        )
    )
