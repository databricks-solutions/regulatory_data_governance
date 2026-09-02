# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze DLT/SDP — CADOC 4060 (Balancete Patrimonial Analítico do Conglomerado Prudencial) → `raw_4060_saldos`
# MAGIC
# MAGIC Versão declarativa. Produz as MESMAS tabelas e o MESMO contrato que o notebook
# MAGIC clássico `pipelines/classical/bronze/raw_4060.py` — ver lá a documentação
# MAGIC completa do leiaute.
# MAGIC
# MAGIC Documento **4060 — Balancete Patrimonial Analítico do Conglomerado Prudencial**,
# MAGIC periodicidade **mensal**, remetido pela **instituição líder do conglomerado prudencial**.
# MAGIC O gêmeo semestral é o **4066** (Balanço), que compartilha este mesmo leiaute.
# MAGIC
# MAGIC Tabelas DLT em modo **batch** (`spark.read`, não streaming): o parse do XML
# MAGIC é autocontido por arquivo (cabeçalho + blocos), sem cross-file joins.
# MAGIC
# MAGIC ⚠️ Checkpoints DISTINTOS do modo clássico (o estado do Auto Loader é específico
# MAGIC de formato e de pipeline) — não colidindo com `classical_bronze_4060_*`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F, types as T


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


DOCUMENTO = "4060"

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schemas explícitos — todos os valores entram como STRING e são convertidos com
# MAGIC ## controle no _finalize para que fora de escala apareça como violação de check em
# MAGIC ## vez de virar NULL silencioso.

# COMMAND ----------


def _conta_consolidado():
    return T.StructType([
        T.StructField("codigoConta", T.StringType()),
        T.StructField("saldoAglutinado", T.StringType()),
        T.StructField("valorEliminacoes", T.StringType()),
        T.StructField("saldoConsolidado", T.StringType()),
    ])


def _bloco_consolidado():
    return T.StructType([
        T.StructField("contas", T.StructType([
            T.StructField("conta", T.ArrayType(_conta_consolidado())),
        ])),
    ])


_CONTA_ASSEMELHADA = T.StructType([
    T.StructField("codigoConta", T.StringType()),
    T.StructField("saldoContabil", T.StringType()),
    T.StructField("saldoAte3Meses", T.StringType()),
    T.StructField("saldoApos3Meses", T.StringType()),
])

_CONTA_SIMPLES = T.StructType([
    T.StructField("codigoConta", T.StringType()),
    T.StructField("saldo", T.StringType()),
])

_DOC_SCHEMA = T.StructType([
    T.StructField("codigoDocumento", T.StringType()),
    T.StructField("codigoConglomerado", T.StringType()),
    T.StructField("cnpj", T.StringType()),
    T.StructField("dataBase", T.StringType()),
    T.StructField("tipoRemessa", T.StringType()),
    T.StructField("taxaConversao", T.StringType()),
    T.StructField("consolidadoPais", _bloco_consolidado()),
    T.StructField("consolidadoExterior", _bloco_consolidado()),
    T.StructField("consolidadoPaisExterior", _bloco_consolidado()),
    T.StructField("assemelhadas", T.StructType([
        T.StructField("balancAssemelhada", T.ArrayType(T.StructType([
            T.StructField("idAssemelhada", T.StringType()),
            T.StructField("tipoAssemelhada", T.StringType()),
            T.StructField("origemAssemelhada", T.StringType()),
            T.StructField("moedaFuncional", T.StringType()),
            T.StructField("motivoConsolidacao", T.StringType()),
            T.StructField("percentConsolidacao", T.StringType()),
            T.StructField("contas", T.StructType([
                T.StructField("conta", T.ArrayType(_CONTA_ASSEMELHADA)),
            ])),
        ]))),
    ])),
    T.StructField("consolidadoPrudencial", _bloco_consolidado()),
    T.StructField("dependenciasExterior", T.StructType([
        T.StructField("dependencia", T.ArrayType(T.StructType([
            T.StructField("identificacao", T.StringType()),
            T.StructField("moedaFuncional", T.StringType()),
            T.StructField("contas", T.StructType([
                T.StructField("conta", T.ArrayType(_CONTA_SIMPLES)),
            ])),
        ]))),
    ])),
    T.StructField("participacoesExterior", T.StructType([
        T.StructField("participacao", T.ArrayType(T.StructType([
            T.StructField("identificacao", T.StringType()),
            T.StructField("moedaFuncional", T.StringType()),
            T.StructField("percentParticipacao", T.StringType()),
            T.StructField("contas", T.StructType([
                T.StructField("conta", T.ArrayType(_CONTA_SIMPLES)),
            ])),
        ]))),
    ])),
])

BLOCOS_CONSOLIDADOS = [
    "consolidadoPais",
    "consolidadoExterior",
    "consolidadoPaisExterior",
    "consolidadoPrudencial",
]

# COMMAND ----------

_CABECALHO = [
    F.col("codigoDocumento").alias("documento"),
    F.col("codigoConglomerado").alias("codigo_conglomerado"),
    F.col("cnpj").alias("cnpj_lider"),
    F.col("dataBase").alias("dt_base"),
    F.col("tipoRemessa").alias("tipo_remessa"),
    F.col("taxaConversao").alias("taxa_conversao"),
]

_VALORES = [
    "saldo_contabil", "saldo_ate_3m", "saldo_apos_3m",
    "saldo_aglutinado", "valor_eliminacoes", "saldo_consolidado", "saldo",
]
_ATRIBUTOS = [
    "entidade_id", "tipo_assemelhada", "origem_assemelhada", "moeda_funcional",
    "motivo_consolidacao", "percent_consolidacao", "percent_participacao",
]

_CONTRACT_SALDOS = [
    "_pk_hash", "documento", "codigo_conglomerado", "cnpj_lider", "dt_base",
    "tipo_remessa", "taxa_conversao", "bloco", "entidade_id", "tipo_assemelhada",
    "origem_assemelhada", "moeda_funcional", "motivo_consolidacao",
    "percent_consolidacao", "percent_participacao", "codigo_conta",
    "saldo_contabil", "saldo_ate_3m", "saldo_apos_3m", "saldo_aglutinado",
    "valor_eliminacoes", "saldo_consolidado", "saldo", "formato_origem",
    "file_path", "file_name", "_source_system", "_ingestion_timestamp", "_ingestion_date",
]

def _finalize(df):
    """Projeta qualquer bloco no contrato bronze canônico."""
    presentes = set(df.columns)
    faltando = [
        F.lit(None).cast("string").alias(c)
        for c in _ATRIBUTOS + _VALORES
        if c not in presentes
    ]
    df = df.select("*", *faltando) if faltando else df
    return df.select(
        F.sha2(
            F.concat_ws(
                "|", "documento", "codigo_conglomerado", "dt_base", "bloco",
                F.coalesce(F.col("entidade_id"), F.lit("")), "codigo_conta",
            ),
            256,
        ).alias("_pk_hash"),
        "documento",
        "codigo_conglomerado",
        "cnpj_lider",
        "dt_base",
        "tipo_remessa",
        F.col("taxa_conversao").cast("decimal(10,4)").alias("taxa_conversao"),
        "bloco",
        "entidade_id",
        "tipo_assemelhada",
        "origem_assemelhada",
        "moeda_funcional",
        "motivo_consolidacao",
        F.col("percent_consolidacao").cast("decimal(11,4)").alias("percent_consolidacao"),
        F.col("percent_participacao").cast("decimal(9,4)").alias("percent_participacao"),
        "codigo_conta",
        *[F.col(c).cast("decimal(17,2)").alias(c) for c in _VALORES],
        F.lit("xml").alias("formato_origem"),
        "file_path",
        "file_name",
        F.lit("bcb_cosif").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )


def _path_exists(path):
    """A landing pode ainda não ter a subpasta deste documento."""
    try:
        dbutils.fs.ls(path)
        return True
    except Exception:
        return False


def _empty_saldos():
    return spark.createDataFrame([], T.StructType([
        T.StructField("_pk_hash", T.StringType()),
        T.StructField("documento", T.StringType()),
        T.StructField("codigo_conglomerado", T.StringType()),
        T.StructField("cnpj_lider", T.StringType()),
        T.StructField("dt_base", T.StringType()),
        T.StructField("tipo_remessa", T.StringType()),
        T.StructField("taxa_conversao", T.DecimalType(10, 4)),
        T.StructField("bloco", T.StringType()),
        T.StructField("entidade_id", T.StringType()),
        T.StructField("tipo_assemelhada", T.StringType()),
        T.StructField("origem_assemelhada", T.StringType()),
        T.StructField("moeda_funcional", T.StringType()),
        T.StructField("motivo_consolidacao", T.StringType()),
        T.StructField("percent_consolidacao", T.DecimalType(11, 4)),
        T.StructField("percent_participacao", T.DecimalType(9, 4)),
        T.StructField("codigo_conta", T.StringType()),
        T.StructField("saldo_contabil", T.DecimalType(17, 2)),
        T.StructField("saldo_ate_3m", T.DecimalType(17, 2)),
        T.StructField("saldo_apos_3m", T.DecimalType(17, 2)),
        T.StructField("saldo_aglutinado", T.DecimalType(17, 2)),
        T.StructField("valor_eliminacoes", T.DecimalType(17, 2)),
        T.StructField("saldo_consolidado", T.DecimalType(17, 2)),
        T.StructField("saldo", T.DecimalType(17, 2)),
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
    comment="CADOC 4060 — Balancete Patrimonial Analítico do Conglomerado Prudencial (mensal). Uma linha por (bloco, entidade, conta COSIF). Leiaute XML de 7 blocos.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_4060_saldos():
    """XML do leiaute (7 blocos): consolidados, assemelhadas, dependências, participações."""
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = f"/Volumes/{catalog}/{schema}/scr_xml/{DOCUMENTO}/"
    checkpoint_root = f"/Volumes/{catalog}/{schema}/_checkpoints"

    if not _path_exists(landing_path):
        return _empty_saldos()

    raw_xml = (
        spark.read
        .format("xml")
        .option("rowTag", "documento")
        .option("attributePrefix", "")
        .schema(_DOC_SCHEMA)
        .load(f"{landing_path}Doc{DOCUMENTO}_*.xml")
        .select(
            "codigoDocumento", "codigoConglomerado", "cnpj", "dataBase",
            "tipoRemessa", "taxaConversao",
            *BLOCOS_CONSOLIDADOS,
            "assemelhadas", "dependenciasExterior", "participacoesExterior",
            F.col("_metadata.file_path").alias("file_path"),
            F.col("_metadata.file_name").alias("file_name"),
        )
    )

    partes = []

    # Blocos 1, 2, 3 e 5 — consolidados (aglutinado / eliminações / consolidado).
    for bloco in BLOCOS_CONSOLIDADOS:
        partes.append(
            raw_xml
            .withColumn("_conta", F.explode_outer(F.col(f"{bloco}.contas.conta")))
            .select(
                *_CABECALHO,
                F.lit(bloco).alias("bloco"),
                F.col("_conta.codigoConta").alias("codigo_conta"),
                F.col("_conta.saldoAglutinado").alias("saldo_aglutinado"),
                F.col("_conta.valorEliminacoes").alias("valor_eliminacoes"),
                F.col("_conta.saldoConsolidado").alias("saldo_consolidado"),
                "file_path", "file_name",
            )
        )

    # Bloco 4 — assemelhadas: uma entidade por `balancAssemelhada`.
    partes.append(
        raw_xml
        .withColumn("_ent", F.explode_outer("assemelhadas.balancAssemelhada"))
        .withColumn("_conta", F.explode_outer(F.col("_ent.contas.conta")))
        .select(
            *_CABECALHO,
            F.lit("assemelhadas").alias("bloco"),
            F.col("_ent.idAssemelhada").alias("entidade_id"),
            F.col("_ent.tipoAssemelhada").alias("tipo_assemelhada"),
            F.col("_ent.origemAssemelhada").alias("origem_assemelhada"),
            F.col("_ent.moedaFuncional").alias("moeda_funcional"),
            F.col("_ent.motivoConsolidacao").alias("motivo_consolidacao"),
            F.col("_ent.percentConsolidacao").alias("percent_consolidacao"),
            F.col("_conta.codigoConta").alias("codigo_conta"),
            F.col("_conta.saldoContabil").alias("saldo_contabil"),
            F.col("_conta.saldoAte3Meses").alias("saldo_ate_3m"),
            F.col("_conta.saldoApos3Meses").alias("saldo_apos_3m"),
            "file_path", "file_name",
        )
    )

    # Blocos 6 e 7 — dependências e participações no exterior.
    for bloco, filho, extra in (
        ("dependenciasExterior", "dependencia", []),
        ("participacoesExterior", "participacao",
         [F.col("_ent.percentParticipacao").alias("percent_participacao")]),
    ):
        partes.append(
            raw_xml
            .withColumn("_ent", F.explode_outer(f"{bloco}.{filho}"))
            .withColumn("_conta", F.explode_outer(F.col("_ent.contas.conta")))
            .select(
                *_CABECALHO,
                F.lit(bloco).alias("bloco"),
                F.col("_ent.identificacao").alias("entidade_id"),
                F.col("_ent.moedaFuncional").alias("moeda_funcional"),
                *extra,
                F.col("_conta.codigoConta").alias("codigo_conta"),
                F.col("_conta.saldo").alias("saldo"),
                "file_path", "file_name",
            )
        )

    unido = None
    for parte in partes:
        pronto = _finalize(parte.filter(F.col("codigo_conta").isNotNull()))
        unido = pronto if unido is None else unido.unionByName(pronto)

    return (unido.select(*_CONTRACT_SALDOS)
            if unido is not None
            else _empty_saldos())


# MAGIC %md
# MAGIC ## Equivalente ao clássico `pipelines/classical/bronze/raw_4060.py`
