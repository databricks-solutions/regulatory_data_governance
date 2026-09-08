# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze DLT/SDP — CADOC 4010 (Balancete Patrimonial Analítico) → `raw_4010_saldos`
# MAGIC
# MAGIC Versão declarativa. Produz a MESMA tabela e o MESMO contrato que o notebook
# MAGIC clássico `pipelines/classical/bronze/raw_4010.py` — ver lá a documentação
# MAGIC completa do leiaute (XML oficial da IN BCB 469/2024 e posicional legado).
# MAGIC
# MAGIC Documento **4010 — Balancete Patrimonial Analítico**, periodicidade **mensal**
# MAGIC (toda data-base mensal), envio pelo STA com o código `ACOS010`.
# MAGIC
# MAGIC O Balancete é o documento MENSAL; inclui as contas de resultado
# MAGIC (grupos 7 Receitas e 8 Despesas), ao contrário do 4016.
# MAGIC
# MAGIC Tabela DLT em modo **batch** (`spark.read`, não streaming): o parse do
# MAGIC posicional cruza o registro de identificação (data-base) com os de dados do
# MAGIC MESMO arquivo, o que evitaria um stream-stream join — e o volume do
# MAGIC balancete é baixo. As duas origens são unidas, discriminadas por
# MAGIC `formato_origem`.
# MAGIC
# MAGIC ⚠️ O Doc 4016 compartilha ESTE MESMO leiaute e tem um notebook gêmeo
# MAGIC (`raw_4016.py`). Mudança de parse aqui deve ser espelhada lá.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F, types as T


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


DOCUMENTO = "4010"

_CONTA = T.StructType([
    T.StructField("codigoConta", T.StringType()),
    T.StructField("saldo", T.StringType()),   # texto: convertido com controle no _finalize
])
_DOC_SCHEMA = T.StructType([
    T.StructField("codigoDocumento", T.StringType()),
    T.StructField("cnpj", T.StringType()),
    T.StructField("dataBase", T.StringType()),
    T.StructField("tipoRemessa", T.StringType()),
    T.StructField("contas", T.StructType([
        T.StructField("conta", T.ArrayType(_CONTA)),
    ])),
])

_CONTRACT = [
    "_pk_hash", "documento", "tipo_remessa", "cnpj_if", "dt_base", "codigo_conta",
    "saldo", "sinal", "formato_origem", "file_path", "file_name",
    "_source_system", "_ingestion_timestamp", "_ingestion_date",
]


def _path_exists(path):
    """A landing pode ainda não ter a subpasta deste documento."""
    try:
        dbutils.fs.ls(path)
        return True
    except Exception:
        return False


def _finalize(df, documento_col, formato_origem):
    """Projeta qualquer uma das origens no contrato bronze canônico."""
    return df.select(
        F.sha2(
            F.concat_ws("|", documento_col, "cnpj_if", "dt_base", "codigo_conta"), 256
        ).alias("_pk_hash"),
        documento_col.alias("documento"),
        "tipo_remessa",
        "cnpj_if",
        "dt_base",                                   # AAAA-MM (texto, como no leiaute)
        "codigo_conta",                              # 10 dígitos COSIF
        F.col("saldo").cast("decimal(17,2)").alias("saldo"),
        "sinal",                                     # nulo no leiaute XML
        F.lit(formato_origem).alias("formato_origem"),
        "file_path",
        "file_name",
        F.lit("bcb_cosif").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )


def _read_xml(landing_path):
    """Leiaute XML oficial: 1 `<documento>` por arquivo, N `<conta>` dentro."""
    df = (
        spark.read
        .format("xml")
        .option("rowTag", "documento")
        .option("attributePrefix", "")
        .schema(_DOC_SCHEMA)
        .load(f"{landing_path}Doc{DOCUMENTO}_*.xml")
        .select(
            "codigoDocumento", "cnpj", "dataBase", "tipoRemessa",
            F.col("contas.conta").alias("_contas"),
            F.col("_metadata.file_path").alias("file_path"),
            F.col("_metadata.file_name").alias("file_name"),
        )
        .withColumn("_conta", F.explode_outer("_contas"))
        .select(
            F.col("codigoDocumento").alias("_documento"),
            F.col("tipoRemessa").alias("tipo_remessa"),
            F.col("cnpj").alias("cnpj_if"),
            F.col("dataBase").alias("dt_base"),
            F.col("_conta.codigoConta").alias("codigo_conta"),
            F.col("_conta.saldo").alias("saldo"),
            F.lit(None).cast("string").alias("sinal"),   # leiaute XML não tem sinal
            "file_path", "file_name",
        )
        .filter(F.col("codigo_conta").isNotNull())
    )
    return _finalize(df, F.col("_documento"), "xml")


def _read_posicional(landing_path):
    """Leiaute posicional legado (71 posições/registro), data-base < jan/2025."""
    lines = (
        spark.read
        .option("pathGlobFilter", f"Doc{DOCUMENTO}_*.txt")
        .text(landing_path, wholetext=False)
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
    # Identificação: doc(4-7) · CNPJ(8-15) · data-base MMAAAA(30-35) · remessa(36).
    ident = tagged.filter(F.col("_rectype") == "ident").select(
        "file_name",
        F.substring("_line", 4, 4).alias("_documento"),
        F.substring("_line", 8, 8).alias("cnpj_if"),
        F.concat(
            F.substring("_line", 32, 4),          # AAAA
            F.lit("-"),
            F.substring("_line", 30, 2),          # MM
        ).alias("dt_base"),
        F.substring("_line", 36, 1).alias("tipo_remessa"),
    )
    # Dados: conta(1-10) · valor absoluto em centavos(15-32) · sinal(33).
    dados = tagged.filter(F.col("_rectype") == "dados").select(
        "file_name", "file_path",
        F.substring("_line", 1, 10).alias("codigo_conta"),
        F.substring("_line", 15, 18).cast("decimal(20,0)").alias("_valor_centavos"),
        F.substring("_line", 33, 1).alias("sinal"),
    )
    return dados.join(ident, on="file_name", how="left").withColumn(
        # saldo assinado em reais (valor absoluto/100 × sinal do leiaute).
        "saldo",
        (F.when(F.col("sinal") == "-", F.lit(-1)).otherwise(F.lit(1))
         * (F.col("_valor_centavos") / F.lit(100))),
    )


def _empty():
    return spark.createDataFrame([], T.StructType([
        T.StructField("_pk_hash", T.StringType()),
        T.StructField("documento", T.StringType()),
        T.StructField("tipo_remessa", T.StringType()),
        T.StructField("cnpj_if", T.StringType()),
        T.StructField("dt_base", T.StringType()),
        T.StructField("codigo_conta", T.StringType()),
        T.StructField("saldo", T.DecimalType(17, 2)),
        T.StructField("sinal", T.StringType()),
        T.StructField("formato_origem", T.StringType()),
        T.StructField("file_path", T.StringType()),
        T.StructField("file_name", T.StringType()),
        T.StructField("_source_system", T.StringType()),
        T.StructField("_ingestion_timestamp", T.TimestampType()),
        T.StructField("_ingestion_date", T.DateType()),
    ]))

# COMMAND ----------


@dlt.table(
    name=f"raw_{DOCUMENTO}_saldos",
    comment="CADOC 4010 — Balancete Patrimonial Analítico COSIF (mensal). Leiaute XML oficial (IN BCB 469/2024) e posicional legado. Base da perna COSIF do batimento inter-CADOC 3040×COSIF.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_4010_saldos():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = f"/Volumes/{catalog}/{schema}/scr_xml/{DOCUMENTO}/"

    if not _path_exists(landing_path):
        return _empty()

    partes = [_read_xml(landing_path), _read_posicional(landing_path)]
    out = partes[0]
    for extra in partes[1:]:
        out = out.unionByName(extra)
    return out.select(*_CONTRACT)
