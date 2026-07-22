# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze DLT/SDP — CADOC 4010 (Balancete COSIF) — parser POSICIONAL
# MAGIC
# MAGIC Versão declarativa. Produz a MESMA tabela `raw_cosif_saldos` e o mesmo
# MAGIC contrato que o notebook clássico `pipelines/classical/bronze/raw_4010.py`.
# MAGIC
# MAGIC Leiaute posicional oficial do Doc 4010/4016 (71 posições/registro):
# MAGIC identificação (#A1 + data-base MMAAAA), dados (conta N10 + valor N18 abs +
# MAGIC sinal), controle (@1). Como o parse cruza o registro de identificação
# MAGIC (data-base) com os de dados do MESMO arquivo, esta é uma tabela DLT em modo
# MAGIC **batch** (`spark.read`, não streaming) — evita stream-stream join e casa
# MAGIC com o baixo volume do balancete.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


@dlt.table(
    name="raw_cosif_saldos",
    comment="CADOC 4010 (Balancete COSIF) — arquivo posicional oficial parseado por posição. Base do batimento inter-CADOC 3040×COSIF.",
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

    lines = (
        spark.read.text(landing_path, wholetext=False)
        .select(
            F.col("value").alias("_line"),
            F.col("_metadata.file_path").alias("file_path"),
            F.col("_metadata.file_name").alias("file_name"),
        )
        .filter(F.col("_line").isNotNull() & (F.length("_line") >= 33))
    )
    tagged = lines.withColumn(
        "_rectype",
        F.when(F.substring("_line", 1, 3) == F.lit("#A1"), F.lit("ident"))
         .when(F.substring("_line", 1, 2) == F.lit("@1"), F.lit("ctrl"))
         .otherwise(F.lit("dados")),
    )
    ident = tagged.filter(F.col("_rectype") == "ident").select(
        "file_name",
        F.substring("_line", 8, 8).alias("cnpj_if"),
        F.concat(F.substring("_line", 32, 4), F.lit("-"), F.substring("_line", 30, 2)).alias("dt_base"),
    )
    dados = tagged.filter(F.col("_rectype") == "dados").select(
        "file_name", "file_path",
        F.substring("_line", 1, 10).alias("codigo_conta"),
        F.substring("_line", 15, 18).cast("decimal(20,0)").alias("_valor_centavos"),
        F.substring("_line", 33, 1).alias("sinal"),
    )
    return dados.join(ident, on="file_name", how="left").select(
        F.sha2(F.concat_ws("|", "cnpj_if", "dt_base", "codigo_conta"), 256).alias("_pk_hash"),
        "cnpj_if", "dt_base", "codigo_conta",
        (F.when(F.col("sinal") == "-", F.lit(-1)).otherwise(F.lit(1))
         * (F.col("_valor_centavos") / F.lit(100))).cast("decimal(17,2)").alias("saldo"),
        "sinal", "file_path", "file_name",
        F.lit("bcb_cosif_posicional").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )
