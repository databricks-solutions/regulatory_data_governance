# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3040 XML Ingestion (native XML reader)
# MAGIC
# MAGIC Ingests `Doc3040_<CNPJ>_<DtBase>_R<Remessa>_P<Parte>.xml` files from the
# MAGIC landing volume using Auto Loader's native XML format
# MAGIC (`cloudFiles.format = "xml"`, `rowTag = "Doc3040"`). The parser stays in
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
# MAGIC The bronze table preserves the existing downstream contract: one row per
# MAGIC XML file with `header` struct + flat `clientes`, `operacoes`, `garantias`,
# MAGIC `vencimentos`, `cont4966` arrays whose elements are denormalized with the
# MAGIC parent keys (`cli_tp`, `cli_cd`, `contrt`, `ipoc`). The reshape is done
# MAGIC entirely with Spark `transform`/`flatten`/`filter` — JVM-native, no UDF.

# COMMAND ----------

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

DOC_3040_XML = StructType([
    StructField("DtBase", StringType()),
    StructField("CNPJ", StringType()),
    StructField("Remessa", IntegerType()),
    StructField("Parte", IntegerType()),
    StructField("TpArq", StringType()),
    StructField("NomeResp", StringType()),
    StructField("EmailResp", StringType()),
    StructField("TelResp", StringType()),
    StructField("TotalCli", IntegerType()),
    StructField("MetodApPE", StringType()),
    StructField("MetodDifTJE", StringType()),
    StructField("Cli", ArrayType(CLI_XML)),
])


# ── Bronze table ──────────────────────────────────────────────────────────────

@dlt.table(
    name="raw_3040_doc",
    comment="SCR 3040 — XML files ingestados via Auto Loader XML (JVM-nativo) e reformatados na contract bronze (header struct + 5 arrays denormalizados). 1 linha por arquivo.",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_3040_doc():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = _conf("landing_path_3040", f"/Volumes/{catalog}/{schema}/scr_xml/3040/")
    # Distinct path from the legacy binaryFile checkpoint so Auto Loader doesn't
    # try to mix incompatible state when migrating from binaryFile to native xml.
    schema_location = _conf("schema_location_3040", f"/Volumes/{catalog}/{schema}/_checkpoints/bronze_3040_xml_native/")

    raw = (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "xml")
        .option("cloudFiles.schemaLocation", schema_location)
        .option("rowTag", "Doc3040")
        .option("attributePrefix", "")
        .option("pathGlobFilter", "Doc3040_*.xml")
        .schema(DOC_3040_XML)
        .load(landing_path)
    )

    # Header — root attributes, snake_case rename
    header = F.struct(
        F.col("DtBase").alias("dt_base"),
        F.col("CNPJ").alias("cnpj_if"),
        F.col("Remessa").alias("remessa"),
        F.col("Parte").alias("parte"),
        F.col("TpArq").alias("tp_arq"),
        F.col("NomeResp").alias("nome_resp"),
        F.col("EmailResp").alias("email_resp"),
        F.col("TelResp").alias("tel_resp"),
        F.col("TotalCli").alias("total_cli"),
        F.col("MetodApPE").alias("metod_ap_pe"),
        F.col("MetodDifTJE").alias("metod_dif_tje"),
    )

    # clientes — one row per <Cli>
    clientes = F.transform(
        "Cli",
        lambda c: F.struct(
            c["Tp"].alias("cli_tp"),
            c["Cd"].alias("cli_cd"),
            c["Autorzc"].alias("autorzc"),
            c["PorteCli"].alias("porte_cli"),
            c["TpCtrl"].alias("tp_ctrl"),
            c["IniRelactCli"].alias("ini_relact_cli"),
            c["FatAnual"].alias("fat_anual"),
        ),
    )

    # operacoes — flatten Cli → Op, denormalize cli_tp/cli_cd
    operacoes = F.flatten(F.transform(
        "Cli",
        lambda c: F.transform(
            F.coalesce(c["Op"], F.array().cast(ArrayType(OP_XML))),
            lambda op: F.struct(
                c["Tp"].alias("cli_tp"),
                c["Cd"].alias("cli_cd"),
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
        ),
    ))

    # vencimentos — Cli → Op (only Ops with a <Venc> child), denormalize keys
    vencimentos = F.flatten(F.transform(
        "Cli",
        lambda c: F.transform(
            F.filter(
                F.coalesce(c["Op"], F.array().cast(ArrayType(OP_XML))),
                lambda op: op["Venc"].isNotNull(),
            ),
            lambda op: F.struct(
                c["Tp"].alias("cli_tp"),
                c["Cd"].alias("cli_cd"),
                op["Contrt"].alias("contrt"),
                op["IPOC"].alias("ipoc"),
                *[op["Venc"][v].alias(v) for v in VENC_VERTICES],
            ),
        ),
    ))

    # garantias — Cli → Op → Gar (3 levels), denormalize cli_tp/cli_cd/contrt/ipoc.
    # Sets gar_categoria = "fidejussoria" if Ident present (a person-or-cnpj)
    # else "real" (asset-based collateral).
    garantias = F.flatten(F.flatten(F.transform(
        "Cli",
        lambda c: F.transform(
            F.coalesce(c["Op"], F.array().cast(ArrayType(OP_XML))),
            lambda op: F.transform(
                F.coalesce(op["Gar"], F.array().cast(ArrayType(GAR_XML))),
                lambda g: F.struct(
                    c["Tp"].alias("cli_tp"),
                    c["Cd"].alias("cli_cd"),
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
        ),
    )))

    # cont4966 — Cli → Op → ContInstFinRes4966 (3 levels)
    cont4966 = F.flatten(F.flatten(F.transform(
        "Cli",
        lambda c: F.transform(
            F.coalesce(c["Op"], F.array().cast(ArrayType(OP_XML))),
            lambda op: F.transform(
                F.coalesce(op["ContInstFinRes4966"], F.array().cast(ArrayType(CONT4966_XML))),
                lambda c4: F.struct(
                    c["Tp"].alias("cli_tp"),
                    c["Cd"].alias("cli_cd"),
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
        ),
    )))

    return (
        raw
        .select(
            F.col("_metadata.file_path").alias("file_path"),
            F.col("_metadata.file_name").alias("file_name"),
            F.col("_metadata.file_modification_time").alias("file_modified_at"),
            F.col("_metadata.file_size").alias("file_size_bytes"),
            header.alias("header"),
            clientes.alias("clientes"),
            operacoes.alias("operacoes"),
            garantias.alias("garantias"),
            vencimentos.alias("vencimentos"),
            cont4966.alias("cont4966"),
            F.lit("bcb_scr_xml").alias("_source_system"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.current_date().alias("_ingestion_date"),
        )
    )
