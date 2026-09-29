# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3040 XML Ingestion (native XML reader)
# MAGIC
# MAGIC Ingests `Doc3040_<CNPJ>_<DtBase>_R<Remessa>_P<Parte>.xml` files from the
# MAGIC landing volume using Auto Loader's native XML format
# MAGIC (`cloudFiles.format = "xml"`, `rowTag = "Cli"`). The parser stays in
# MAGIC the JVM — no Python UDF round-trip — which is meaningfully faster than
# MAGIC `binaryFile + lxml UDF` for production-scale submissions
# MAGIC (10k+ ops, 100MB+ payloads).
# MAGIC
# MAGIC The natural XML hierarchy is:
# MAGIC
# MAGIC ```
# MAGIC <Doc3040 DtBase CNPJ Remessa Parte TpArq NomeResp EmailResp TelResp
# MAGIC          TotalCli MetodApPE MetodDifTJE>
# MAGIC   <Cli Tp Cd Autorzc PorteCli TpCtrl IniRelactCli FatAnual>
# MAGIC     <Op DetCli Contrt NatuOp Mod OrigemRec Indx PercIndx VarCamb DtVencOp
# MAGIC         CEP TaxEft DtContr ProvConsttd CaracEspecial DiaAtraso IPOC>
# MAGIC       <Venc v110|v120|...|v330="..."/>
# MAGIC       <Gar Tp [Ident PercGar] | [VlrOrig VlrData DtReav]/>+
# MAGIC       <ContInstFinRes4966 ClasAtFin EstInstFin CartProvMin VlrContBr TJE RendMes>
# MAGIC         <Estagio Motivo DtAlocacao/>
# MAGIC       </ContInstFinRes4966>
# MAGIC     </Op>+
# MAGIC   </Cli>+
# MAGIC </Doc3040>
# MAGIC ```
# MAGIC
# MAGIC The bronze table carries a `header` struct + flat `clientes`, `operacoes`,
# MAGIC `garantias`, `vencimentos`, `cont4966` arrays whose elements are
# MAGIC denormalized with the parent keys (`cli_tp`, `cli_cd`, `contrt`, `ipoc`).
# MAGIC The reshape is done entirely with Spark `transform`/`flatten`/`filter` —
# MAGIC JVM-native, no UDF.
# MAGIC
# MAGIC **Grain: one row per `<Cli>`.** The native XML reader buffers the whole
# MAGIC `rowTag` element as text, so reading per client keeps memory at
# MAGIC O(largest `<Cli>`), regardless of file size. To count documents use
# MAGIC `count(distinct file_path)` — `file_path`, `file_name`, `file_size_bytes`
# MAGIC and `header` repeat across rows of the same file.
# MAGIC
# MAGIC **Header**: with a nested `rowTag` the reader does not surface the root
# MAGIC attributes, so they come from each file's prefix, joined on `file_path`.
# MAGIC
# MAGIC **Parallelism**: multiline XML is not splittable, so one file is one
# MAGIC task. It comes from the submission being split into `Parte` files, not
# MAGIC from compute size.

# COMMAND ----------

import glob
import re

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, ArrayType,
)


def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


VENC_VERTICES = [
    "v110", "v120", "v130", "v140", "v150", "v160", "v165", "v170", "v175",
    "v180", "v190", "v199",
    "v205", "v210", "v220", "v230", "v240", "v250", "v260", "v270", "v280", "v290",
    "v310", "v320", "v330",
    "v20", "v40", "v60", "v80",
]


# ── Natural XML schema (matches BACEN Doc 3040 wire format) ──────────────────
# `attributePrefix=""` → attributes appear as fields without a leading underscore.
# Children with `maxOccurs > 1` become ArrayType; single-child elements become
# StructType. Decimal/Integer types are coerced by the connector at parse time.

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

# Contract of the `header` column consumed by silver.
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

# XML attribute → header field, in HEADER_STRUCT order.
HEADER_ATTRS = [
    ("DtBase", str), ("CNPJ", str), ("Remessa", int), ("Parte", int),
    ("TpArq", str), ("NomeResp", str), ("EmailResp", str), ("TelResp", str),
    ("TotalCli", int), ("MetodApPE", str), ("MetodDifTJE", str),
]


# ── Header from each file's prefix ────────────────────────────────────────────
# The root open tag follows the XML prolog and is ~250 bytes, so 64 KB is plenty
# and the read does not depend on file size.

PROBE_BYTES = 1 << 16
ROOT_TAG_RE = re.compile(rb"<Doc3040\b[^>]*>")
ATTR_RE = re.compile(rb'([A-Za-z0-9_]+)\s*=\s*"([^"]*)"')
ENCODING_RE = re.compile(rb'encoding\s*=\s*["\']([\w.-]+)["\']')


def read_root_attrs(path: str) -> tuple:
    """`<Doc3040 ...>` attributes, read from the file's prefix."""
    with open(path, "rb") as fh:
        head = fh.read(PROBE_BYTES)

    tag = ROOT_TAG_RE.search(head)
    if tag is None:
        raise ValueError(
            f"{path}: no <Doc3040 ...> open tag in the first {PROBE_BYTES} "
            f"bytes. Not a Doc 3040, truncated, or a double-width encoding "
            f"(the layout allows UTF-16, which this prefix reader does not "
            f"cover)."
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
            # A malformed integer becomes NULL, like the native XML reader's cast.
            try:
                return int(v)
            except ValueError:
                return None
        return v

    return tuple(coerce(n, k) for n, k in HEADER_ATTRS)


def build_header_df(landing_path: str):
    """Static (file_path, header) DataFrame for the files in the landing path.

    Lists with the same criteria as Auto Loader — recursive, `Doc3040_*.xml`
    glob — so every file the stream reads has a header.
    """
    paths = sorted(glob.glob(f"{landing_path.rstrip('/')}/**/Doc3040_*.xml",
                             recursive=True))
    if not paths:
        raise RuntimeError(
            f"no Doc3040_*.xml under {landing_path} — with no file there is no "
            f"header to read and nothing for bronze to ingest.")

    schema = StructType([
        StructField("hdr_file_path", StringType(), False),
        StructField("header", HEADER_STRUCT),
    ])
    return spark.createDataFrame([(p, read_root_attrs(p)) for p in paths],
                                 schema=schema)


# ── Bronze table ──────────────────────────────────────────────────────────────

@dlt.table(
    name="raw_3040_doc",
    comment="SCR 3040 — XML files ingestados via Auto Loader XML (JVM-nativo, rowTag=Cli) e reformatados na contract bronze (header struct + 5 arrays denormalizados). 1 linha por <Cli>.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
# Structural invariant, not a data-quality rule: a row with no header has no
# data-base and is useless to silver.
@dlt.expect_or_fail("header_presente", "header.dt_base IS NOT NULL")
def raw_3040_doc():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = _conf("landing_path_3040", f"/Volumes/{catalog}/{schema}/scr_xml/3040/")
    # Auto Loader state is specific to format AND schema, and both pipeline modes
    # share the volume: a dedicated path avoids collisions.
    schema_location = _conf("schema_location_3040", f"/Volumes/{catalog}/{schema}/_checkpoints/bronze_3040_cli/")

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

    # Missing `Op` → empty array, so transform/flatten don't propagate NULL.
    ops = F.coalesce(F.col("Op"), F.array().cast(ArrayType(OP_XML)))

    # clientes — single-element array: the record is one <Cli>
    clientes = F.array(F.struct(
        F.col("Tp").alias("cli_tp"),
        F.col("Cd").alias("cli_cd"),
        F.col("Autorzc").alias("autorzc"),
        F.col("PorteCli").alias("porte_cli"),
        F.col("TpCtrl").alias("tp_ctrl"),
        F.col("IniRelactCli").alias("ini_relact_cli"),
        F.col("FatAnual").alias("fat_anual"),
    ))

    # operacoes — the current client's Ops, denormalizing cli_tp/cli_cd
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

    # vencimentos — only Ops with a <Venc> child, denormalize keys
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

    # garantias — Op → Gar (2 levels), denormalize cli_tp/cli_cd/contrt/ipoc.
    # Sets gar_categoria = "fidejussoria" if Ident present (a person-or-cnpj)
    # else "real" (asset-based collateral).
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

    # cont4966 — Op → ContInstFinRes4966 (2 levels)
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

    # `_metadata.file_path` carries a scheme (`dbfs:/Volumes/...`) while the
    # driver-side listing does not; normalizing both sides makes the join match.
    file_path_norm = F.regexp_replace(
        F.col("_metadata.file_path"), "^[A-Za-z0-9+.-]+:", "")

    return (
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
        # LEFT, not INNER: a file whose header is missing from the map must reach
        # the table and trip the expectation, rather than vanish silently.
        .join(F.broadcast(build_header_df(landing_path)),
              on=F.col("file_path") == F.col("hdr_file_path"),
              how="left")
        .select(
            "file_path", "file_name", "file_modified_at", "file_size_bytes",
            "header",
            "clientes", "operacoes", "garantias", "vencimentos", "cont4966",
            "_source_system", "_ingestion_timestamp", "_ingestion_date",
        )
    )
