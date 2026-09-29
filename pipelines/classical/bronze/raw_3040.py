# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — SCR 3040 XML (Auto Loader, sem DLT/SDP)
# MAGIC
# MAGIC Ingesta `Doc3040_*.xml` do volume de landing em `bronze.raw_3040_doc`:
# MAGIC header struct + 5 arrays denormalizados (`clientes`, `operacoes`,
# MAGIC `garantias`, `vencimentos`, `cont4966`), o mesmo contrato do pipeline DLT
# MAGIC em `pipelines/bronze/transformations/raw_3040.py`, sem `import dlt`.
# MAGIC
# MAGIC **Grão: 1 linha por `<Cli>`.** O leitor XML nativo bufferiza como texto o
# MAGIC elemento inteiro do `rowTag`, então ler por cliente mantém a memória em
# MAGIC O(maior `<Cli>`), independente do tamanho do arquivo. Para contar
# MAGIC documentos use `count(distinct file_path)` — `file_path`, `file_name`,
# MAGIC `file_size_bytes` e `header` repetem nas linhas do mesmo arquivo.
# MAGIC
# MAGIC **Cabeçalho**: com o `rowTag` aninhado o leitor não expõe os atributos da
# MAGIC raiz, então eles vêm do prefixo de cada arquivo e são ligados por
# MAGIC `file_path`.
# MAGIC
# MAGIC **Paralelismo**: XML multiline não é splittable, então 1 arquivo = 1 task.
# MAGIC Vem da remessa estar dividida em `Parte`, não do tamanho da compute.

# COMMAND ----------

import glob
import re

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, ArrayType,
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Parâmetros (widgets)
# MAGIC Injetados pelo job clássico via `base_parameters`; defaults permitem rodar
# MAGIC o notebook interativamente.

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

landing_path = f"/Volumes/{catalog}/{landing_schema}/scr_xml/3040/"
# Estado do Auto Loader é específico de formato E schema, e os dois modos
# compartilham o volume: caminhos próprios (`classical_*`) evitam colisão.
schema_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3040_cli_schema/"
checkpoint_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3040_cli_chk/"
target_table = f"{catalog}.{bronze_schema}.raw_3040_doc"

print(f"landing_path        = {landing_path}")
print(f"target_table        = {target_table}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema XML nativo (BACEN Doc 3040 wire format)
# MAGIC `attributePrefix=""` → atributos viram campos sem underscore. `CLI_XML` é
# MAGIC o schema do registro; `HEADER_STRUCT`, o do cabeçalho.

# COMMAND ----------

VENC_VERTICES = [
    "v110", "v120", "v130", "v140", "v150", "v160", "v165", "v170", "v175",
    "v180", "v190", "v199",
    "v205", "v210", "v220", "v230", "v240", "v250", "v260", "v270", "v280", "v290",
    "v310", "v320", "v330",
    "v20", "v40", "v60", "v80",
]

VENC_XML = StructType([StructField(v, DecimalType(18, 2)) for v in VENC_VERTICES])

GAR_XML = StructType([
    StructField("Tp", StringType()),
    StructField("Ident", StringType()),
    StructField("PercGar", DecimalType(8, 4)),
    StructField("VlrOrig", DecimalType(18, 2)),
    StructField("VlrData", DecimalType(18, 2)),
    StructField("DtReav", StringType()),
])

ESTAGIO_XML = StructType([
    StructField("Motivo", StringType()),
    StructField("DtAlocacao", StringType()),
])

CONT4966_XML = StructType([
    StructField("ClasAtFin", StringType()),
    StructField("EstInstFin", StringType()),
    StructField("CartProvMin", StringType()),
    StructField("VlrContBr", DecimalType(18, 2)),
    StructField("TJE", DecimalType(8, 4)),
    StructField("RendMes", DecimalType(18, 2)),
    StructField("Estagio", ESTAGIO_XML),
])

OP_XML = StructType([
    StructField("DetCli", StringType()),
    StructField("Contrt", StringType()),
    StructField("NatuOp", StringType()),
    StructField("Mod", StringType()),
    StructField("OrigemRec", StringType()),
    StructField("Indx", StringType()),
    StructField("PercIndx", DecimalType(8, 4)),
    StructField("VarCamb", StringType()),
    StructField("DtVencOp", StringType()),
    StructField("CEP", StringType()),
    StructField("TaxEft", DecimalType(8, 4)),
    StructField("DtContr", StringType()),
    StructField("ProvConsttd", DecimalType(18, 2)),
    StructField("CaracEspecial", StringType()),
    StructField("DiaAtraso", IntegerType()),
    StructField("IPOC", StringType()),
    StructField("Venc", VENC_XML),
    StructField("Gar", ArrayType(GAR_XML)),
    StructField("ContInstFinRes4966", ArrayType(CONT4966_XML)),
])

# Schema do registro — o `rowTag` é <Cli>.
CLI_XML = StructType([
    StructField("Tp", StringType()),
    StructField("Cd", StringType()),
    StructField("Autorzc", StringType()),
    StructField("PorteCli", StringType()),
    StructField("TpCtrl", StringType()),
    StructField("IniRelactCli", StringType()),
    StructField("FatAnual", DecimalType(18, 2)),
    StructField("Op", ArrayType(OP_XML)),
])

# Contrato da coluna `header` consumida pelo silver.
HEADER_STRUCT = StructType([
    StructField("dt_base", StringType()),
    StructField("cnpj_if", StringType()),
    StructField("remessa", IntegerType()),
    StructField("parte", IntegerType()),
    StructField("tp_arq", StringType()),
    StructField("nome_resp", StringType()),
    StructField("email_resp", StringType()),
    StructField("tel_resp", StringType()),
    StructField("total_cli", IntegerType()),
    StructField("metod_ap_pe", StringType()),
    StructField("metod_dif_tje", StringType()),
])

# Atributo XML → campo do header, na ordem de HEADER_STRUCT.
HEADER_ATTRS = [
    ("DtBase", str), ("CNPJ", str), ("Remessa", int), ("Parte", int),
    ("TpArq", str), ("NomeResp", str), ("EmailResp", str), ("TelResp", str),
    ("TotalCli", int), ("MetodApPE", str), ("MetodDifTJE", str),
]

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cabeçalho: lido do prefixo de cada arquivo
# MAGIC A tag de abertura da raiz vem logo após o prolog XML e tem ~250 bytes, então
# MAGIC 64 KB bastam e a leitura não depende do tamanho do arquivo.

# COMMAND ----------

PROBE_BYTES = 1 << 16
ROOT_TAG_RE = re.compile(rb"<Doc3040\b[^>]*>")
ATTR_RE = re.compile(rb'([A-Za-z0-9_]+)\s*=\s*"([^"]*)"')
ENCODING_RE = re.compile(rb'encoding\s*=\s*["\']([\w.-]+)["\']')


def read_root_attrs(path: str) -> dict:
    """Atributos da tag raiz `<Doc3040 ...>`, lidos do prefixo do arquivo."""
    with open(path, "rb") as fh:
        head = fh.read(PROBE_BYTES)

    tag = ROOT_TAG_RE.search(head)
    if tag is None:
        raise ValueError(
            f"{path}: tag de abertura <Doc3040 ...> não encontrada nos primeiros "
            f"{PROBE_BYTES} bytes. Arquivo não é um Doc 3040, está truncado, ou "
            f"usa um encoding de largura dupla (o leiaute admite UTF-16, que este "
            f"leitor de prefixo não cobre)."
        )

    enc_match = ENCODING_RE.search(head[:200])
    enc = enc_match.group(1).decode("ascii", "replace") if enc_match else "utf-8"
    try:
        "".encode(enc)
    except LookupError:
        enc = "utf-8"

    raw = {k.decode("ascii"): v.decode(enc, "replace")
           for k, v in ATTR_RE.findall(tag.group(0))}

    def coerce(name, kind):
        v = raw.get(name)
        if v is None or v == "":
            return None
        if kind is int:
            # Inteiro malformado vira NULL, como o cast do leitor XML nativo.
            try:
                return int(v)
            except ValueError:
                return None
        return v

    return {"attrs": tuple(coerce(n, k) for n, k in HEADER_ATTRS)}


def build_header_df(landing_path: str):
    """DataFrame estático (file_path, header) dos arquivos do landing.

    Lista com o mesmo critério do Auto Loader — recursivo, glob `Doc3040_*.xml` —
    para que todo arquivo lido pelo stream tenha cabeçalho.
    """
    paths = sorted(glob.glob(f"{landing_path.rstrip('/')}/**/Doc3040_*.xml",
                             recursive=True))
    if not paths:
        raise RuntimeError(
            f"nenhum Doc3040_*.xml em {landing_path} — sem arquivo não há "
            f"cabeçalho a ler e o bronze não teria o que ingerir.")

    rows = [(p, read_root_attrs(p)["attrs"]) for p in paths]
    schema = StructType([
        StructField("hdr_file_path", StringType(), False),
        StructField("header", HEADER_STRUCT),
    ])
    print(f"cabeçalhos lidos    = {len(rows)} arquivo(s)")
    for p, attrs in rows:
        print(f"  {p.rsplit('/', 1)[-1]:<48} DtBase={attrs[0]} "
              f"Remessa={attrs[2]} Parte={attrs[3]} TotalCli={attrs[8]}")
    return spark.createDataFrame(rows, schema=schema)


header_df = build_header_df(landing_path)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Leitura (Auto Loader XML nativo) + reshape para o contrato bronze
# MAGIC Reshape com `transform`/`flatten`/`filter` JVM-nativos, sem UDF — idêntico
# MAGIC ao pipeline DLT.

# COMMAND ----------

raw = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "xml")
    .option("cloudFiles.schemaLocation", schema_location)
    .option("rowTag", "Cli")
    .option("attributePrefix", "")
    .option("pathGlobFilter", "Doc3040_*.xml")
    .schema(CLI_XML)
    .load(landing_path)
)

# `Op` ausente → array vazio, para os transform/flatten não propagarem NULL.
ops = F.coalesce(F.col("Op"), F.array().cast(ArrayType(OP_XML)))

# clientes — array de 1 elemento: o registro é um <Cli>
clientes = F.array(F.struct(
    F.col("Tp").alias("cli_tp"),
    F.col("Cd").alias("cli_cd"),
    F.col("Autorzc").alias("autorzc"),
    F.col("PorteCli").alias("porte_cli"),
    F.col("TpCtrl").alias("tp_ctrl"),
    F.col("IniRelactCli").alias("ini_relact_cli"),
    F.col("FatAnual").alias("fat_anual"),
))

# operacoes — Op do cliente corrente, denormalizando cli_tp/cli_cd
operacoes = F.transform(
    ops,
    lambda op: F.struct(
        F.col("Tp").alias("cli_tp"),
        F.col("Cd").alias("cli_cd"),
        op["DetCli"].alias("det_cli"),
        op["Contrt"].alias("contrt"),
        op["NatuOp"].alias("natu_op"),
        op["Mod"].alias("mod"),
        op["OrigemRec"].alias("origem_rec"),
        op["Indx"].alias("indx"),
        op["PercIndx"].alias("perc_indx"),
        op["VarCamb"].alias("var_camb"),
        op["DtVencOp"].alias("dt_venc_op"),
        op["CEP"].alias("cep"),
        op["TaxEft"].alias("tax_eft"),
        op["DtContr"].alias("dt_contr"),
        op["ProvConsttd"].alias("prov_consttd"),
        op["CaracEspecial"].alias("carac_especial"),
        op["DiaAtraso"].alias("dia_atraso"),
        op["IPOC"].alias("ipoc"),
    ),
)

# vencimentos — só as Ops com filho <Venc>, denormalizando as chaves
vencimentos = F.transform(
    F.filter(ops, lambda op: op["Venc"].isNotNull()),
    lambda op: F.struct(
        F.col("Tp").alias("cli_tp"),
        F.col("Cd").alias("cli_cd"),
        op["Contrt"].alias("contrt"),
        op["IPOC"].alias("ipoc"),
        *[op["Venc"][v].alias(v) for v in VENC_VERTICES],
    ),
)

# garantias — Op → Gar (2 níveis), denormalizando cli_tp/cli_cd/contrt/ipoc.
# gar_categoria = "fidejussoria" quando há Ident (pessoa/CNPJ), senão "real".
garantias = F.flatten(F.transform(
    ops,
    lambda op: F.transform(
        F.coalesce(op["Gar"], F.array().cast(ArrayType(GAR_XML))),
        lambda g: F.struct(
            F.col("Tp").alias("cli_tp"),
            F.col("Cd").alias("cli_cd"),
            op["Contrt"].alias("contrt"),
            op["IPOC"].alias("ipoc"),
            g["Tp"].alias("gar_tp"),
            g["Ident"].alias("ident"),
            g["PercGar"].alias("perc_gar"),
            g["VlrOrig"].alias("vlr_orig"),
            g["VlrData"].alias("vlr_data"),
            g["DtReav"].alias("dt_reav"),
            F.when(g["Ident"].isNotNull(), F.lit("fidejussoria"))
             .otherwise(F.lit("real"))
             .alias("gar_categoria"),
        ),
    ),
))

# cont4966 — Op → ContInstFinRes4966 (2 níveis)
cont4966 = F.flatten(F.transform(
    ops,
    lambda op: F.transform(
        F.coalesce(op["ContInstFinRes4966"], F.array().cast(ArrayType(CONT4966_XML))),
        lambda c4: F.struct(
            F.col("Tp").alias("cli_tp"),
            F.col("Cd").alias("cli_cd"),
            op["Contrt"].alias("contrt"),
            op["IPOC"].alias("ipoc"),
            c4["ClasAtFin"].alias("clas_at_fin"),
            c4["EstInstFin"].alias("est_inst_fin"),
            c4["CartProvMin"].alias("cart_prov_min"),
            c4["VlrContBr"].alias("vlr_cont_br"),
            c4["TJE"].alias("tje"),
            c4["RendMes"].alias("rend_mes"),
            c4["Estagio"]["Motivo"].alias("estagio_motivo"),
            c4["Estagio"]["DtAlocacao"].alias("estagio_dt_alocacao"),
        ),
    ),
))

# `_metadata.file_path` vem com esquema (`dbfs:/Volumes/...`) e a listagem do
# driver sem; normalizar os dois lados é o que faz o join casar.
file_path_norm = F.regexp_replace(F.col("_metadata.file_path"), "^[A-Za-z0-9+.-]+:", "")

reshaped = (
    raw
    .select(
        file_path_norm.alias("file_path"),
        F.col("_metadata.file_name").alias("file_name"),
        F.col("_metadata.file_modification_time").alias("file_modified_at"),
        F.col("_metadata.file_size").alias("file_size_bytes"),
        clientes.alias("clientes"),
        operacoes.alias("operacoes"),
        garantias.alias("garantias"),
        vencimentos.alias("vencimentos"),
        cont4966.alias("cont4966"),
        F.lit("bcb_scr_xml").alias("_source_system"),
        F.current_timestamp().alias("_ingestion_timestamp"),
        F.current_date().alias("_ingestion_date"),
    )
    # LEFT, não INNER: arquivo sem cabeçalho no mapa tem de chegar na tabela e
    # ser acusado pela checagem final, em vez de desaparecer em silêncio.
    .join(F.broadcast(header_df),
          on=F.col("file_path") == F.col("hdr_file_path"),
          how="left")
    .select(
        "file_path", "file_name", "file_modified_at", "file_size_bytes",
        "header",
        "clientes", "operacoes", "garantias", "vencimentos", "cont4966",
        "_source_system", "_ingestion_timestamp", "_ingestion_date",
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Escrita incremental (`availableNow`) + propriedades de retenção
# MAGIC `trigger(availableNow=True)` processa todos os arquivos pendentes e
# MAGIC encerra — equivalente batch do streaming table DLT, mas 100% clássico.

# COMMAND ----------

query = (
    reshaped.writeStream
    .format("delta")
    .option("checkpointLocation", checkpoint_location)
    .partitionBy("_ingestion_date")
    .trigger(availableNow=True)
    .toTable(target_table)
)
query.awaitTermination()

# Retenção de 5 anos (R.18) — paridade com as table_properties do pipeline DLT.
spark.sql(
    f"ALTER TABLE {target_table} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'bronze')"
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Integridade do cabeçalho
# MAGIC Header nulo indica arquivo que chegou ao landing entre a leitura dos
# MAGIC prefixos e o batch. Sem data-base a linha é inútil para o silver, então
# MAGIC falha aqui.

# COMMAND ----------

sem_header = spark.sql(
    f"SELECT count(*) AS n, count(distinct file_path) AS arquivos "
    f"FROM {target_table} WHERE header IS NULL OR header.dt_base IS NULL"
).first()

if sem_header["n"]:
    raise RuntimeError(
        f"{target_table}: {sem_header['n']} linha(s) em "
        f"{sem_header['arquivos']} arquivo(s) sem cabeçalho. O arquivo chegou ao "
        f"landing depois da leitura dos prefixos — rode o notebook novamente "
        f"para reprocessá-lo com cabeçalho."
    )

resumo = spark.sql(
    f"SELECT count(*) AS linhas, count(distinct file_path) AS arquivos "
    f"FROM {target_table}"
).first()
print(f"OK — {target_table}: {resumo['linhas']} linha(s) "
      f"(1 por <Cli>) em {resumo['arquivos']} arquivo(s)")
