# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3040 Raw Ingestion
# MAGIC Ingests raw SCR 3040 credit operations, clients, guarantees, additional info,
# MAGIC and maturity vertices from landing zone parquet files into bronze Delta tables.

import dlt
from pyspark.sql import functions as F

# Pipeline configuration
SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SOURCE_SCHEMA = spark.conf.get("source_schema", "landing")
BRONZE_CATALOG = spark.conf.get("bronze_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("bronze_schema", "bronze")

_BRONZE_META_COLS = [
    F.lit("oracle_core_banking").alias("_source_system"),
    F.lit("TB_OPERACOES_CREDITO").alias("_source_table"),
    F.current_timestamp().alias("_ingestion_timestamp"),
    F.lit("FULL_LOAD").alias("_change_type"),
    F.current_date().alias("_ingestion_date"),
]


@dlt.table(
    name="operacoes_raw",
    comment="SCR 3040 — operações de crédito individuais capturadas via CDC do core banking Oracle",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def operacoes_raw():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3040_operacoes")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/operacoes/")
        .select(
            "*",
            F.lit("oracle_core_banking").alias("_source_system"),
            F.lit("TB_OPERACOES_CREDITO").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(F.concat_ws("|", F.col("cnpj_if"), F.col("contrt"), F.col("dt_base")), 256),
        )
    )


@dlt.table(
    name="clientes_raw",
    comment="SCR 3040 — dados cadastrais dos clientes capturados via CDC do core banking",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def clientes_raw():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3040_clientes")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/clientes/")
        .select(
            "*",
            F.lit("oracle_core_banking").alias("_source_system"),
            F.lit("TB_CLIENTES").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(F.concat_ws("|", F.col("cli_cd"), F.col("cli_tp"), F.col("dt_base")), 256),
        )
    )


@dlt.table(
    name="garantias_raw",
    comment="SCR 3040 — garantias das operações de crédito (fidejussórias e não fidejussórias)",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def garantias_raw():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3040_garantias")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/garantias/")
        .select(
            "*",
            F.lit("oracle_core_banking").alias("_source_system"),
            F.lit("TB_GARANTIAS").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(
                F.concat_ws("|", F.col("cnpj_if"), F.col("contrt"), F.col("cli_cd"), F.col("gar_tp"), F.col("dt_base")),
                256,
            ),
        )
    )


@dlt.table(
    name="inf_adicionais_raw",
    comment="SCR 3040 — informações adicionais das operações (cessões, saídas, IFRS 9, FIDC)",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def inf_adicionais_raw():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3040_inf_adicionais")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/inf_adicionais/")
        .select(
            "*",
            F.lit("oracle_core_banking").alias("_source_system"),
            F.lit("TB_INF_ADICIONAIS").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(
                F.concat_ws("|", F.col("cnpj_if"), F.col("contrt"), F.col("cli_cd"), F.col("inf_tp"), F.col("seq"), F.col("dt_base")),
                256,
            ),
        )
    )


@dlt.table(
    name="vencimentos_raw",
    comment="SCR 3040 — distribuição de vencimentos por vértice temporal (31 vértices × 5 categorias)",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def vencimentos_raw():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_3040_vencimentos")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/vencimentos/")
        .select(
            "*",
            F.lit("oracle_core_banking").alias("_source_system"),
            F.lit("TB_VENCIMENTOS").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("FULL_LOAD").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(F.concat_ws("|", F.col("cnpj_if"), F.col("contrt"), F.col("cli_cd"), F.col("dt_base")), 256),
        )
    )


@dlt.table(
    name="raw_ipoc_events",
    comment="IPOC lifecycle events — criação, alteração e saída de operações de crédito",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_ipoc_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/bronze_ipoc_events")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{SOURCE_CATALOG}/{SOURCE_SCHEMA}/landing_3040/ipoc_events/")
        .select(
            "*",
            F.lit("operational_log").alias("_source_system"),
            F.lit("IPOC_EVENTS").alias("_source_table"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.lit("CDC").alias("_change_type"),
            F.current_date().alias("_ingestion_date"),
            F.lit(None).cast("string").alias("_source_column_map"),
        )
        .withColumn(
            "_pk_hash",
            F.sha2(F.concat_ws("|", F.col("cnpj_if"), F.col("ipoc"), F.col("event_timestamp")), 256),
        )
    )
