# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — CADOC 4060 → `bronze.raw_4060_saldos`
# MAGIC
# MAGIC Balancete Patrimonial Analítico do **Conglomerado Prudencial**, mensal,
# MAGIC remetido pela instituição líder. O gêmeo semestral é o 4066.
# MAGIC
# MAGIC ⚠️ Leiaute PRÓPRIO — não é o do 4010/4016. São 7 blocos, com a posição de cada
# MAGIC entidade do conglomerado. Ver `docs/cadoc4060/README.md`.
# MAGIC
# MAGIC | # | Bloco | Obrig. | Valores |
# MAGIC |---|---|---|---|
# MAGIC | 1 | `consolidadoPais` | não | `saldoAglutinado` · `valorEliminacoes` · `saldoConsolidado` |
# MAGIC | 2 | `consolidadoExterior` | não | idem |
# MAGIC | 3 | `consolidadoPaisExterior` | **sim** | idem |
# MAGIC | 4 | `assemelhadas` | não | `saldoContabil` · `saldoAte3Meses` · `saldoApos3Meses` |
# MAGIC | 5 | `consolidadoPrudencial` | **sim** | `saldoAglutinado` · `valorEliminacoes` · `saldoConsolidado` |
# MAGIC | 6 | `dependenciasExterior` | não | `saldo` |
# MAGIC | 7 | `participacoesExterior` | não | `saldo` |
# MAGIC
# MAGIC Uma tabela só, com `bloco` como discriminador e colunas de valor nuláveis —
# MAGIC os blocos têm formas diferentes. A silver separa por grão.
# MAGIC
# MAGIC ⚠️ Envio em ordem SEQUENCIAL obrigatória: sem a data-base anterior aceita, o
# MAGIC BCB não recebe a seguinte.
# MAGIC
# MAGIC Checkpoints do Auto Loader são distintos dos do modo DLT.

# COMMAND ----------

from pyspark.sql import functions as F, types as T

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

DOCUMENTO = "4060"
LANDING_PATH = f"/Volumes/{catalog}/{landing_schema}/scr_xml/{DOCUMENTO}/"
CHECKPOINT_ROOT = f"/Volumes/{catalog}/{landing_schema}/_checkpoints"
TARGET_TABLE = f"{catalog}.{bronze_schema}.raw_{DOCUMENTO}_saldos"

print(f"landing_path     = {LANDING_PATH}")
print(f"target_table     = {TARGET_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Contrato bronze
# MAGIC As tabelas são criadas ANTES dos streams: um cliente que ainda não
# MAGIC depositou arquivo deste CADOC termina com tabela vazia (e a silver segue
# MAGIC rodando) em vez de quebrar a orquestração.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
    _pk_hash              STRING,
    documento             STRING,
    codigo_conglomerado   STRING,
    cnpj_lider            STRING,
    dt_base               STRING,
    tipo_remessa          STRING,
    taxa_conversao        DECIMAL(10,4),
    bloco                 STRING,
    entidade_id           STRING,
    tipo_assemelhada      STRING,
    origem_assemelhada    STRING,
    moeda_funcional       STRING,
    motivo_consolidacao   STRING,
    percent_consolidacao  DECIMAL(11,4),
    percent_participacao  DECIMAL(9,4),
    codigo_conta          STRING,
    saldo_contabil        DECIMAL(17,2),
    saldo_ate_3m          DECIMAL(17,2),
    saldo_apos_3m         DECIMAL(17,2),
    saldo_aglutinado      DECIMAL(17,2),
    valor_eliminacoes     DECIMAL(17,2),
    saldo_consolidado     DECIMAL(17,2),
    saldo                 DECIMAL(17,2),
    formato_origem        STRING,
    file_path             STRING,
    file_name             STRING,
    _source_system        STRING,
    _ingestion_timestamp  TIMESTAMP,
    _ingestion_date       DATE
)
USING DELTA
PARTITIONED BY (_ingestion_date)
COMMENT 'CADOC 4060 — Balancete Patrimonial Analítico do Conglomerado Prudencial (mensal). Uma linha por (bloco, entidade, conta COSIF). Leiaute XML de 7 blocos.'
TBLPROPERTIES (
    'delta.logRetentionDuration'         = 'interval 1825 days',
    'delta.deletedFileRetentionDuration' = 'interval 1825 days',
    'quality'                            = 'bronze'
)
""")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema explícito do XML
# MAGIC Todos os valores entram como STRING e são convertidos com controle no
# MAGIC `_finalize` — assim um valor fora de escala no arquivo aparece como
# MAGIC violação de check em vez de virar `null` silencioso no parse.

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

# Colunas de valor por bloco: as que o bloco não usa entram como NULL.
_VALORES = [
    "saldo_contabil", "saldo_ate_3m", "saldo_apos_3m",
    "saldo_aglutinado", "valor_eliminacoes", "saldo_consolidado", "saldo",
]
_ATRIBUTOS = [
    "entidade_id", "tipo_assemelhada", "origem_assemelhada", "moeda_funcional",
    "motivo_consolidacao", "percent_consolidacao", "percent_participacao",
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
        "dt_base",                                   # AAAA-MM (texto, como no leiaute)
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
        "codigo_conta",                              # conta COSIF
        *[F.col(c).cast("decimal(17,2)").alias(c) for c in _VALORES],
        F.lit("xml").alias("formato_origem"),
        "file_path",
        "file_name",
        F.lit("bcb_cosif").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )


def _append(df, tabela):
    (
        df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .partitionBy("_ingestion_date")
        .saveAsTable(tabela)
    )

# COMMAND ----------
# MAGIC %md
# MAGIC ## Ingestão do XML do leiaute (7 blocos)

# COMMAND ----------

raw_xml = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "xml")
    .option("rowTag", "documento")
    .option("attributePrefix", "")
    .option("cloudFiles.schemaLocation", f"{CHECKPOINT_ROOT}/classical_bronze_{DOCUMENTO}_xml_schema/")
    .option("pathGlobFilter", f"Doc{DOCUMENTO}_*.xml")
    .schema(_DOC_SCHEMA)
    .load(LANDING_PATH)
    .select(
        "codigoDocumento", "codigoConglomerado", "cnpj", "dataBase",
        "tipoRemessa", "taxaConversao",
        *BLOCOS_CONSOLIDADOS,
        "assemelhadas", "dependenciasExterior", "participacoesExterior",
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
    )
)


def _write_xml(batch_df, _batch_id):
    partes = []

    # Blocos 1, 2, 3 e 5 — consolidados (aglutinado / eliminações / consolidado).
    for bloco in BLOCOS_CONSOLIDADOS:
        partes.append(
            batch_df
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
        batch_df
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
            batch_df
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
    if unido is not None:
        _append(unido, TARGET_TABLE)


(
    raw_xml.writeStream
    .foreachBatch(_write_xml)
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
    .groupBy("documento", "dt_base", "bloco")
    .agg(
        F.countDistinct("entidade_id").alias("entidades"),
        F.count("*").alias("contas"),
    )
    .orderBy("dt_base", "bloco")
)
print(f"OK — {TARGET_TABLE}: {spark.table(TARGET_TABLE).count()} linha(s)")
