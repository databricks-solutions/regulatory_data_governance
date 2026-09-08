# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — CADOC 4016 (Balanço Patrimonial Analítico) → `bronze.raw_4016_saldos`
# MAGIC
# MAGIC Documento contábil COSIF **4016 — Balanço Patrimonial Analítico**, periodicidade
# MAGIC **semestral** (apenas as datas-base de junho e dezembro), prazo de envio até o último dia útil do mês seguinte ao da data-base.
# MAGIC
# MAGIC O Balanço é SEMESTRAL e representa a posição contábil **após a
# MAGIC apuração do resultado do exercício** — por isso não se espera a
# MAGIC presença das contas dos grupos 7 (Receitas) e 8 (Despesas)
# MAGIC (§3.2.2.a). Essa regra é validada na DQX Studio, não aqui.
# MAGIC
# MAGIC ## Leiaute oficial (XML) — vigente a partir da data-base jan/2025
# MAGIC Fonte: *Balancete e Balanço Patrimonial Analítico — Documentos 4010/4016,
# MAGIC Instruções de Preenchimento* (Desig/BCB) —
# MAGIC `bcb.gov.br/content/estabilidadefinanceira/cosif_leiautes/Leiaute_4010_xmlV1.pdf`,
# MAGIC cópia e tabelas de campos em `docs/cosif/README.md`. A **IN BCB 469/2024**
# MAGIC substituiu o arquivo posicional pelo XML. Envio pelo STA com o código `ACOS016`.
# MAGIC
# MAGIC ```xml
# MAGIC <documento codigoDocumento="4016" cnpj="99999999" dataBase="AAAA-MM" tipoRemessa="I">
# MAGIC   <contas>
# MAGIC     <conta codigoConta="0031000000" saldo="321460997.24" />
# MAGIC   </contas>
# MAGIC </documento>
# MAGIC ```
# MAGIC
# MAGIC - `codigoDocumento` — sempre `4016` neste pipeline (§3.1.2.b). É gravado na
# MAGIC   coluna `documento` SEM filtro: um arquivo do 4010 depositado por engano
# MAGIC   nesta pasta precisa aparecer para o check DQX `documento_e_4016` acusar.
# MAGIC - `cnpj` — obrigatório, alfanumérico de 8 caracteres (§3.1.2.c).
# MAGIC - `dataBase` — padrão `AAAA-MM` (§3.1.2.d).
# MAGIC - `tipoRemessa` — `I` (inclusão) ou `S` (substituição) (§3.1.2.e).
# MAGIC - `codigoConta` — conta COSIF, 10 dígitos sem ponto/traço: 9 de hierarquia
# MAGIC   (6 níveis desde jan/2025, INs 426 a 433) + 1 dígito verificador (§3.2.2.a).
# MAGIC - `saldo` — saldo de fechamento em R$ do último dia útil do mês, até 18
# MAGIC   posições com 2 decimais (§3.2.2.b). O leiaute **não tem campo de sinal**,
# MAGIC   por isso `sinal` fica nulo nas linhas vindas de XML.
# MAGIC
# MAGIC ## Leiaute POSICIONAL (legado, data-base < jan/2025)
# MAGIC Registros de 71 posições — identificação (`#A1` + código do documento + CNPJ
# MAGIC + data-base `MMAAAA` + tipo de remessa), dados (conta N(10) + valor absoluto
# MAGIC N(18) em centavos + sinal `+`/`-`) e controle (`@1` + nº de registros).
# MAGIC Mantido para reprocessar histórico anterior à migração XML.
# MAGIC
# MAGIC ⚠️ O Doc 4010 compartilha ESTE MESMO leiaute e tem um notebook gêmeo
# MAGIC (`raw_4010.py`). Mudança de parse aqui deve ser espelhada lá.
# MAGIC
# MAGIC Os dois caminhos (XML e posicional) gravam o MESMO contrato e rodam em
# MAGIC sequência (append no mesmo Delta). Checkpoints DISTINTOS do modo DLT.

# COMMAND ----------

from pyspark.sql import functions as F, types as T

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

DOCUMENTO = "4016"
LANDING_PATH = f"/Volumes/{catalog}/{landing_schema}/scr_xml/{DOCUMENTO}/"
CHECKPOINT_ROOT = f"/Volumes/{catalog}/{landing_schema}/_checkpoints"
TARGET_TABLE = f"{catalog}.{bronze_schema}.raw_{DOCUMENTO}_saldos"

print(f"landing_path = {LANDING_PATH}")
print(f"target_table = {TARGET_TABLE}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Contrato bronze
# MAGIC Uma linha por (cnpj_if, data-base, conta COSIF). `formato_origem` registra
# MAGIC de qual leiaute a linha veio (`xml` | `posicional`), preservando a auditoria
# MAGIC de proveniência depois da migração da IN BCB 469/2024.
# MAGIC
# MAGIC A tabela é criada ANTES dos streams: um cliente que ainda não tem arquivo
# MAGIC deste CADOC na landing termina com a tabela vazia (e a silver segue
# MAGIC rodando) em vez de quebrar a orquestração.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
    _pk_hash              STRING,
    documento             STRING,
    tipo_remessa          STRING,
    cnpj_if               STRING,
    dt_base               STRING,
    codigo_conta          STRING,
    saldo                 DECIMAL(17,2),
    sinal                 STRING,
    formato_origem        STRING,
    file_path             STRING,
    file_name             STRING,
    _source_system        STRING,
    _ingestion_timestamp  TIMESTAMP,
    _ingestion_date       DATE
)
USING DELTA
PARTITIONED BY (_ingestion_date)
COMMENT 'CADOC 4016 — Balanço Patrimonial Analítico COSIF (semestral: junho e dezembro). Leiaute XML oficial (IN BCB 469/2024) e posicional legado. Posição após a apuração do resultado — sem contas dos grupos 7 e 8.'
TBLPROPERTIES (
    'delta.logRetentionDuration'         = 'interval 1825 days',
    'delta.deletedFileRetentionDuration' = 'interval 1825 days',
    'quality'                            = 'bronze'
)
""")


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


def _append(df):
    (
        df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .partitionBy("_ingestion_date")
        .saveAsTable(TARGET_TABLE)
    )

# COMMAND ----------
# MAGIC %md
# MAGIC ## Caminho 1 — leiaute XML (oficial, data-base ≥ jan/2025)
# MAGIC Auto Loader com o leitor **nativo de XML** (`cloudFiles.format=xml`,
# MAGIC `rowTag=documento`), schema explícito e `attributePrefix=""` para os
# MAGIC atributos do leiaute virarem colunas com o nome original.

# COMMAND ----------

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
        "codigoDocumento", "cnpj", "dataBase", "tipoRemessa",
        F.col("contas.conta").alias("_contas"),
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
    )
)


def _write_xml(batch_df, _batch_id):
    exploded = (
        batch_df
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
    _append(_finalize(exploded, F.col("_documento"), "xml"))


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
# MAGIC ## Caminho 2 — leiaute POSICIONAL (legado, data-base < jan/2025)
# MAGIC Lê cada arquivo como TEXTO (1 linha = 1 registro de 71 posições), aplica
# MAGIC substrings por posição e propaga a data-base do registro de identificação
# MAGIC (`#A1`) para os de dados via join por `file_name` — o batch é auto-contido,
# MAGIC então não há stream-stream join.

# COMMAND ----------

raw_txt = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "text")          # 1 linha = 1 registro posicional
    .option("cloudFiles.schemaLocation", f"{CHECKPOINT_ROOT}/classical_bronze_{DOCUMENTO}_posicional_schema/")
    .option("wholeText", "false")
    .option("pathGlobFilter", f"Doc{DOCUMENTO}_*.txt")
    .load(LANDING_PATH)
    .select(
        F.col("value").alias("_line"),
        F.col("_metadata.file_path").alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
    )
    .filter(F.col("_line").isNotNull() & (F.length("_line") >= 33))
)


def _parse_posicional(lines):
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


def _write_posicional(batch_df, _batch_id):
    _append(_finalize(_parse_posicional(batch_df), F.col("_documento"), "posicional"))


(
    raw_txt.writeStream
    .foreachBatch(_write_posicional)
    .option("checkpointLocation", f"{CHECKPOINT_ROOT}/classical_bronze_{DOCUMENTO}_posicional_chk/")
    .trigger(availableNow=True)
    .start()
    .awaitTermination()
)
print(f"  [posicional/{DOCUMENTO}] stream concluído")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Resumo da ingestão

# COMMAND ----------

display(
    spark.table(TARGET_TABLE)
    .groupBy("documento", "formato_origem", "dt_base")
    .agg(F.count("*").alias("contas"), F.sum(F.abs("saldo")).alias("soma_abs_saldo"))
    .orderBy("dt_base")
)
print(f"OK — {TARGET_TABLE}: {spark.table(TARGET_TABLE).count()} linha(s)")
