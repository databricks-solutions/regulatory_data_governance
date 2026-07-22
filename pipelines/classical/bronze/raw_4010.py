# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — CADOC 4010 (Balancete COSIF) — parser POSICIONAL
# MAGIC
# MAGIC Ingesta o arquivo **posicional de largura fixa** do Documento 4010/4016
# MAGIC (Balancete Patrimonial Analítico COSIF), conforme o leiaute oficial do BACEN
# MAGIC (https://www.bcb.gov.br/estabilidadefinanceira/leiautecosif4010, válido a
# MAGIC partir da data-base março/2022). Produz `bronze.raw_cosif_saldos`.
# MAGIC
# MAGIC ## Leiaute oficial (registros de 71 posições)
# MAGIC - **Identificação**: `#A1`(1-3) · `4010`(4-7) · CNPJ 8(8-15) · filler(16-29)
# MAGIC   · data-base MMAAAA(30-35) · tipo remessa I/S(36) · filler(37-71).
# MAGIC - **Dados** (≥ mar/2022): código conta N(10)(1-10) · filler(11-14) ·
# MAGIC   valor absoluto N(18) em centavos(15-32) · sinal +/-(33) · filler(34-71).
# MAGIC - **Controle final**: `@1`(1-2) · nº registros N(6)(3-8) · filler(9-71).
# MAGIC
# MAGIC Lemos o arquivo como TEXTO (uma linha = um registro), aplicamos substrings
# MAGIC por posição, propagamos a data-base do registro de identificação para os
# MAGIC registros de dados e escrevemos a contract bronze. Checkpoints DISTINTOS do
# MAGIC modo DLT (`classical_bronze_4010_*`).

# COMMAND ----------

from pyspark.sql import functions as F, Window

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
# MAGIC ## Leitura como linhas de texto (Auto Loader `text`) + parse posicional
# MAGIC Cada arquivo tem 1 registro de identificação (data-base) + N de dados + 1
# MAGIC de controle. `_metadata.file_name` isola cada arquivo para propagar a
# MAGIC data-base do `#A1` aos registros de dados via window.

# COMMAND ----------

raw = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "text")           # 1 linha = 1 registro posicional
    .option("cloudFiles.schemaLocation", schema_location)
    .option("wholeText", "false")
    .option("pathGlobFilter", "Doc4010_*.txt")
    .load(landing_path)
    .select(
        F.col("value").alias("_line"),
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
    )
)


def _parse_and_write(batch_df, _batch_id):
    """Parse posicional por micro-batch (batch semantics → join ident×dados sem
    complexidade de stream-stream join). Cada arquivo é pequeno e auto-contido."""
    tagged = batch_df.withColumn(
        "_rectype",
        F.when(F.substring("_line", 1, 3) == F.lit("#A1"), F.lit("ident"))
         .when(F.substring("_line", 1, 2) == F.lit("@1"), F.lit("ctrl"))
         .otherwise(F.lit("dados")),
    )
    # data-base MMAAAA do registro de identificação (30-35) → AAAA-MM.
    ident = tagged.filter(F.col("_rectype") == "ident").select(
        "file_name",
        F.substring("_line", 8, 8).alias("cnpj_if"),
        F.concat(
            F.substring("_line", 32, 4),           # AAAA (posições 32-35)
            F.lit("-"),
            F.substring("_line", 30, 2),           # MM   (posições 30-31)
        ).alias("dt_base"),
    )
    dados = tagged.filter(F.col("_rectype") == "dados").select(
        "file_name", "file_path",
        F.substring("_line", 1, 10).alias("codigo_conta"),
        F.substring("_line", 15, 18).cast("decimal(20,0)").alias("_valor_centavos"),
        F.substring("_line", 33, 1).alias("sinal"),
    )
    reshaped = dados.join(ident, on="file_name", how="left").select(
        F.sha2(F.concat_ws("|", "cnpj_if", "dt_base", "codigo_conta"), 256).alias("_pk_hash"),
        "cnpj_if", "dt_base", "codigo_conta",
        # saldo assinado em reais (valor absoluto/100 com o sinal do leiaute).
        (F.when(F.col("sinal") == "-", F.lit(-1)).otherwise(F.lit(1))
         * (F.col("_valor_centavos") / F.lit(100))).cast("decimal(17,2)").alias("saldo"),
        "sinal",
        "file_path", "file_name",
        F.lit("bcb_cosif_posicional").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )
    (reshaped.write.format("delta").mode("append")
        .option("mergeSchema", "true").partitionBy("_ingestion_date")
        .saveAsTable(target_table))


query = (
    raw.writeStream
    .foreachBatch(_parse_and_write)
    .option("checkpointLocation", checkpoint_location)
    .trigger(availableNow=True)
    .start()
)
query.awaitTermination()

spark.sql(
    f"ALTER TABLE {target_table} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'bronze')"
)

print(f"OK — {target_table}: {spark.table(target_table).count()} linha(s)")
