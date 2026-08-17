# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze DLT/SDP — CADOC 2011 (DDR) → `raw_2011_doc`
# MAGIC
# MAGIC Versão declarativa. Produz a MESMA tabela e o MESMO contrato que o notebook
# MAGIC clássico `pipelines/classical/bronze/raw_2011.py` — ver lá a documentação
# MAGIC completa do leiaute (estrutura XML, anexos de domínio e por que bronze é
# MAGIC uma linha por ARQUIVO em vez de por conta).
# MAGIC
# MAGIC Documento **2011 — DDR** (*Demonstrativo Diário de Acompanhamento das
# MAGIC Parcelas de Requerimento de Capital e dos Limites Operacionais*),
# MAGIC periodicidade **diária**. Leiaute v5 (a partir de 01/07/2023) —
# MAGIC `bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011`, cópias em
# MAGIC `docs/ddr2011/`.
# MAGIC
# MAGIC Tabela DLT em modo **batch** (`spark.read`, não streaming): o volume diário
# MAGIC do DDR é baixo (~40 contas por arquivo) e o batch mantém a paridade com o
# MAGIC parse do notebook clássico sem exigir estado de streaming próprio.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F, types as T


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


DOCUMENTO = "2011"

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
    T.StructField("valorConta", T.StringType()),   # texto: convertido na silver
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

_CONTRACT = [
    "_pk_hash", "documento", "tipo_envio", "cnpj_if", "dt_base",
    "parametros", "contas", "file_path", "file_name",
    "_source_system", "_ingestion_timestamp", "_ingestion_date",
]

# Schema do contrato bronze — usado no fallback vazio (landing sem a subpasta).
_BRONZE_SCHEMA = T.StructType([
    T.StructField("_pk_hash", T.StringType()),
    T.StructField("documento", T.StringType()),
    T.StructField("tipo_envio", T.StringType()),
    T.StructField("cnpj_if", T.StringType()),
    T.StructField("dt_base", T.StringType()),
    T.StructField("parametros", T.ArrayType(_PARAMETRO)),
    T.StructField("contas", T.ArrayType(_CONTA)),
    T.StructField("file_path", T.StringType()),
    T.StructField("file_name", T.StringType()),
    T.StructField("_source_system", T.StringType()),
    T.StructField("_ingestion_timestamp", T.TimestampType()),
    T.StructField("_ingestion_date", T.DateType()),
])


def _path_exists(path):
    """A landing pode ainda não ter a subpasta deste documento."""
    try:
        dbutils.fs.ls(path)
        return True
    except Exception:
        return False


def _finalize(df):
    """Projeta o documento lido no contrato bronze canônico."""
    return df.select(
        F.sha2(F.concat_ws("|", "_documento", "cnpj_if", "dt_base"), 256).alias("_pk_hash"),
        F.col("_documento").alias("documento"),
        "tipo_envio",
        "cnpj_if",
        "dt_base",                                   # AAAA-MM-DD (texto, como no leiaute)
        "parametros",
        "contas",
        "file_path",
        "file_name",
        F.lit("bcb_ddr").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )


def _read_xml(landing_path):
    """Leiaute XML oficial: 1 `<documentoDDR>` por arquivo."""
    df = (
        spark.read
        .format("xml")
        .option("rowTag", "documentoDDR")
        .option("attributePrefix", "")
        .schema(_DOC_SCHEMA)
        .load(f"{landing_path}Doc{DOCUMENTO}_*.xml")
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
    return _finalize(df)


def _empty():
    return spark.createDataFrame([], _BRONZE_SCHEMA)

# COMMAND ----------


@dlt.table(
    name=f"raw_{DOCUMENTO}_doc",
    comment="CADOC 2011 — DDR (Demonstrativo Diario de Acompanhamento das Parcelas de Requerimento de Capital e dos Limites Operacionais), periodicidade DIARIA. Uma linha por arquivo, arrays de parametros/contas/detalhamentos preservados.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_2011_doc():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = f"/Volumes/{catalog}/{schema}/scr_xml/{DOCUMENTO}/"

    if not _path_exists(landing_path):
        return _empty()

    return _read_xml(landing_path).select(*_CONTRACT)
