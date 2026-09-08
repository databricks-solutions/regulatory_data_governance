# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — CADOC 2011 (DDR) → `bronze.raw_2011_doc`
# MAGIC
# MAGIC Documento **2011 — DDR**, periodicidade **diária**: exposição cambial e
# MAGIC parcelas de requerimento de capital para risco de mercado. Leiaute v5 +
# MAGIC XSD em `docs/ddr2011/README.md` (fonte:
# MAGIC `bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011`).
# MAGIC
# MAGIC ```xml
# MAGIC <documentoDDR cnpj="99999999" dataBase="2026-03-31" codigoDocumento="2011" tipoEnvio="I">
# MAGIC   <parametros><parametro codigoParametro="31" valorParametro="..."/></parametros>
# MAGIC   <contas><conta codigoConta="111000" valorConta="1551000.00">
# MAGIC     <detalhamentosDDR><detalhamentoDDR valorDetalhe="403000.00">
# MAGIC       <detalhe codigoElemento="83" valorElemento="USD"/>
# MAGIC     </detalhamentoDDR></detalhamentosDDR>
# MAGIC   </conta></contas>
# MAGIC </documentoDDR>
# MAGIC ```
# MAGIC
# MAGIC Uma linha por **arquivo**: o leiaute tem dois grãos filhos (`parametros` e
# MAGIC `contas`→`detalhamentos`), então achatar aqui perderia um deles. A silver
# MAGIC abre em três tabelas. Difere do `raw_4010_saldos` (grão único → uma linha
# MAGIC por conta).
# MAGIC
# MAGIC Campos aninhados mantêm os nomes do leiaute e os valores ficam STRING — a
# MAGIC silver renomeia e converte ao explodir. `dataBase` é `AAAA-MM-DD` (diária,
# MAGIC contra o `AAAA-MM` do 4010/4016). `codigoDocumento` é gravado SEM filtro,
# MAGIC para o check `documento_e_2011` acusar arquivo de outro CADOC nesta pasta.
# MAGIC
# MAGIC Leitor XML nativo do Auto Loader com schema explícito (o XSD fecha a
# MAGIC estrutura; sem UDF `lxml` como no 3050). Checkpoints distintos do modo DLT.
# MAGIC Mesma tabela/contrato que `pipelines/bronze/transformations/raw_2011.py`.

# COMMAND ----------

from pyspark.sql import functions as F, types as T

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

DOCUMENTO = "2011"
LANDING_PATH = f"/Volumes/{catalog}/{landing_schema}/scr_xml/{DOCUMENTO}/"
CHECKPOINT_ROOT = f"/Volumes/{catalog}/{landing_schema}/_checkpoints"
TARGET_TABLE = f"{catalog}.{bronze_schema}.raw_{DOCUMENTO}_doc"

print(f"landing_path = {LANDING_PATH}")
print(f"target_table = {TARGET_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Contrato bronze
# MAGIC Criada ANTES do stream: sem arquivo deste CADOC na landing, a tabela fica
# MAGIC vazia e a silver segue rodando em vez de quebrar a orquestração.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
    _pk_hash              STRING,
    documento             STRING,
    tipo_envio            STRING,
    cnpj_if               STRING,
    dt_base               STRING,
    parametros            ARRAY<STRUCT<codigoParametro: STRING, valorParametro: STRING>>,
    contas                ARRAY<STRUCT<
                              codigoConta: STRING,
                              valorConta: STRING,
                              detalhamentosDDR: STRUCT<
                                  detalhamentoDDR: ARRAY<STRUCT<
                                      valorDetalhe: STRING,
                                      detalhe: ARRAY<STRUCT<
                                          codigoElemento: STRING,
                                          valorElemento: STRING
                                      >>
                                  >>
                              >
                          >>,
    file_path             STRING,
    file_name             STRING,
    _source_system        STRING,
    _ingestion_timestamp  TIMESTAMP,
    _ingestion_date       DATE
)
USING DELTA
PARTITIONED BY (_ingestion_date)
COMMENT 'CADOC 2011 — DDR (Demonstrativo Diario de Acompanhamento das Parcelas de Requerimento de Capital e dos Limites Operacionais), periodicidade DIARIA. Uma linha por arquivo, arrays de parametros/contas/detalhamentos preservados.'
TBLPROPERTIES (
    'delta.logRetentionDuration'         = 'interval 1825 days',
    'delta.deletedFileRetentionDuration' = 'interval 1825 days',
    'quality'                            = 'bronze'
)
""")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema explícito (espelha o XSD oficial)

# COMMAND ----------

_DETALHE = T.StructType([
    T.StructField("codigoElemento", T.StringType()),
    T.StructField("valorElemento", T.StringType()),
])
_DETALHAMENTO = T.StructType([
    T.StructField("valorDetalhe", T.StringType()),
    T.StructField("detalhe", T.ArrayType(_DETALHE)),
])
_CONTA = T.StructType([
    T.StructField("codigoConta", T.StringType()),
    T.StructField("valorConta", T.StringType()),   # convertido na silver
    T.StructField("detalhamentosDDR", T.StructType([
        T.StructField("detalhamentoDDR", T.ArrayType(_DETALHAMENTO)),
    ])),
])
_PARAMETRO = T.StructType([
    T.StructField("codigoParametro", T.StringType()),
    T.StructField("valorParametro", T.StringType()),
])
_DOC_SCHEMA = T.StructType([
    T.StructField("cnpj", T.StringType()),
    T.StructField("dataBase", T.StringType()),
    T.StructField("codigoDocumento", T.StringType()),
    T.StructField("tipoEnvio", T.StringType()),
    T.StructField("parametros", T.StructType([
        T.StructField("parametro", T.ArrayType(_PARAMETRO)),
    ])),
    T.StructField("contas", T.StructType([
        T.StructField("conta", T.ArrayType(_CONTA)),
    ])),
])


def _finalize(df):
    """Projeta o documento lido no contrato bronze canônico."""
    return df.select(
        # PK lógica (documento, cnpj, data-base). Remessa de substituição repete a
        # chave; a silver resolve pelo _ingestion_timestamp.
        F.sha2(F.concat_ws("|", "_documento", "cnpj_if", "dt_base"), 256).alias("_pk_hash"),
        F.col("_documento").alias("documento"),
        "tipo_envio",
        "cnpj_if",
        "dt_base",                                   # AAAA-MM-DD, texto
        "parametros",
        "contas",
        "file_path",
        "file_name",
        F.lit("bcb_ddr").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )

# COMMAND ----------
# MAGIC %md
# MAGIC ## Ingestão — Auto Loader batch (`trigger availableNow`)

# COMMAND ----------

raw_xml = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "xml")
    .option("rowTag", "documentoDDR")
    .option("attributePrefix", "")
    .option("cloudFiles.schemaLocation", f"{CHECKPOINT_ROOT}/classical_bronze_{DOCUMENTO}_xml_schema/")
    .option("pathGlobFilter", f"Doc{DOCUMENTO}_*.xml")
    .schema(_DOC_SCHEMA)
    .load(LANDING_PATH)
    .select(
        F.col("codigoDocumento").alias("_documento"),
        F.col("tipoEnvio").alias("tipo_envio"),
        F.col("cnpj").alias("cnpj_if"),
        F.col("dataBase").alias("dt_base"),
        F.col("parametros.parametro").alias("parametros"),
        F.col("contas.conta").alias("contas"),
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
    )
)


def _write(batch_df, _batch_id):
    (
        _finalize(batch_df).write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .partitionBy("_ingestion_date")
        .saveAsTable(TARGET_TABLE)
    )


(
    raw_xml.writeStream
    .foreachBatch(_write)
    .option("checkpointLocation", f"{CHECKPOINT_ROOT}/classical_bronze_{DOCUMENTO}_xml_chk/")
    .trigger(availableNow=True)
    .start()
    .awaitTermination()
)
print(f"  [xml/{DOCUMENTO}] stream concluído")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Resumo da ingestão

# COMMAND ----------

display(
    spark.table(TARGET_TABLE)
    .groupBy("documento", "tipo_envio", "dt_base")
    .agg(
        F.count("*").alias("arquivos"),
        F.sum(F.size("contas")).alias("contas"),
        F.sum(F.size("parametros")).alias("parametros"),
    )
    .orderBy("dt_base")
)
print(f"OK — {TARGET_TABLE}: {spark.table(TARGET_TABLE).count()} linha(s)")
