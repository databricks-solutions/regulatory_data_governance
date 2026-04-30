# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3040 XML Ingestion
# MAGIC
# MAGIC Ingests `Doc3040_<CNPJ>_<DtBase>_R<Remessa>_P<Parte>.xml` files from the landing
# MAGIC volume and parses them into a typed nested struct matching the BACEN wire format
# MAGIC (see `sample/Doc3040_99999999_2026-03_R1_P1.xml`):
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
# MAGIC Output table `raw_3040_doc` carries one row per XML file with `header` + nested
# MAGIC arrays of `clientes`, `operacoes`, `garantias`, `vencimentos`, `cont4966`. Silver
# MAGIC explodes these into normalized tables.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, ArrayType,
)

# Pipeline configuration — read inside the table function (NOT at module level).
# Calling spark.conf.get(...) at module top-level during DLT graph analysis can
# silently fail and prevent every @dlt.table decorator in the file from registering,
# which surfaces as the misleading NO_TABLES_IN_PIPELINE error.

def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


# ── Schema (matches BACEN Doc 3040 wire format, snake_case) ───────────────────

VENC_VERTICES = [
    "v110", "v120", "v130", "v140", "v150", "v160", "v165", "v170", "v175",
    "v180", "v190", "v199",
    "v205", "v210", "v220", "v230", "v240", "v250", "v260", "v270", "v280", "v290",
    "v310", "v320", "v330",
    "v20", "v40", "v60", "v80",
]

HEADER_SCHEMA = StructType([
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

CLIENTE_SCHEMA = StructType([
    StructField("cli_tp", StringType()),
    StructField("cli_cd", StringType()),
    StructField("autorzc", StringType()),
    StructField("porte_cli", StringType()),
    StructField("tp_ctrl", StringType()),
    StructField("ini_relact_cli", StringType()),
    StructField("fat_anual", DecimalType(18, 2)),
])

OP_SCHEMA = StructType([
    StructField("cli_tp", StringType()),
    StructField("cli_cd", StringType()),
    StructField("det_cli", StringType()),
    StructField("contrt", StringType()),
    StructField("natu_op", StringType()),
    StructField("mod", StringType()),
    StructField("origem_rec", StringType()),
    StructField("indx", StringType()),
    StructField("perc_indx", DecimalType(8, 4)),
    StructField("var_camb", StringType()),
    StructField("dt_venc_op", StringType()),
    StructField("cep", StringType()),
    StructField("tax_eft", DecimalType(8, 4)),
    StructField("dt_contr", StringType()),
    StructField("prov_consttd", DecimalType(18, 2)),
    StructField("carac_especial", StringType()),
    StructField("dia_atraso", IntegerType()),
    StructField("ipoc", StringType()),
])

GAR_SCHEMA = StructType([
    StructField("cli_tp", StringType()),
    StructField("cli_cd", StringType()),
    StructField("contrt", StringType()),
    StructField("ipoc", StringType()),
    StructField("gar_tp", StringType()),
    StructField("ident", StringType()),
    StructField("perc_gar", DecimalType(8, 4)),
    StructField("vlr_orig", DecimalType(18, 2)),
    StructField("vlr_data", DecimalType(18, 2)),
    StructField("dt_reav", StringType()),
    StructField("gar_categoria", StringType()),
])

VENC_SCHEMA = StructType(
    [
        StructField("cli_tp", StringType()),
        StructField("cli_cd", StringType()),
        StructField("contrt", StringType()),
        StructField("ipoc", StringType()),
    ]
    + [StructField(v, DecimalType(18, 2)) for v in VENC_VERTICES]
)

CONT4966_SCHEMA = StructType([
    StructField("cli_tp", StringType()),
    StructField("cli_cd", StringType()),
    StructField("contrt", StringType()),
    StructField("ipoc", StringType()),
    StructField("clas_at_fin", StringType()),
    StructField("est_inst_fin", StringType()),
    StructField("cart_prov_min", StringType()),
    StructField("vlr_cont_br", DecimalType(18, 2)),
    StructField("tje", DecimalType(8, 4)),
    StructField("rend_mes", DecimalType(18, 2)),
    StructField("estagio_motivo", StringType()),
    StructField("estagio_dt_alocacao", StringType()),
])

DOC_SCHEMA = StructType([
    StructField("header", HEADER_SCHEMA),
    StructField("clientes", ArrayType(CLIENTE_SCHEMA)),
    StructField("operacoes", ArrayType(OP_SCHEMA)),
    StructField("garantias", ArrayType(GAR_SCHEMA)),
    StructField("vencimentos", ArrayType(VENC_SCHEMA)),
    StructField("cont4966", ArrayType(CONT4966_SCHEMA)),
])


# ── Parser (lxml — runs distributed via UDF) ──────────────────────────────────

def _parse_3040(content):
    from lxml import etree

    if content is None:
        return None
    root = etree.fromstring(content)

    def _dec(s): return None if s in (None, "") else s
    def _int(s):
        if s in (None, ""):
            return None
        try: return int(s)
        except (ValueError, TypeError): return None

    header = {
        "dt_base": root.get("DtBase"),
        "cnpj_if": root.get("CNPJ"),
        "remessa": _int(root.get("Remessa")),
        "parte": _int(root.get("Parte")),
        "tp_arq": root.get("TpArq"),
        "nome_resp": root.get("NomeResp"),
        "email_resp": root.get("EmailResp"),
        "tel_resp": root.get("TelResp"),
        "total_cli": _int(root.get("TotalCli")),
        "metod_ap_pe": root.get("MetodApPE"),
        "metod_dif_tje": root.get("MetodDifTJE"),
    }

    clientes, operacoes, garantias, vencimentos, cont4966 = [], [], [], [], []

    for cli in root.findall("Cli"):
        cli_tp, cli_cd = cli.get("Tp"), cli.get("Cd")
        clientes.append({
            "cli_tp": cli_tp, "cli_cd": cli_cd,
            "autorzc": cli.get("Autorzc"), "porte_cli": cli.get("PorteCli"),
            "tp_ctrl": cli.get("TpCtrl"), "ini_relact_cli": cli.get("IniRelactCli"),
            "fat_anual": _dec(cli.get("FatAnual")),
        })

        for op in cli.findall("Op"):
            ipoc, contrt = op.get("IPOC"), op.get("Contrt")
            operacoes.append({
                "cli_tp": cli_tp, "cli_cd": cli_cd,
                "det_cli": op.get("DetCli"), "contrt": contrt,
                "natu_op": op.get("NatuOp"), "mod": op.get("Mod"),
                "origem_rec": op.get("OrigemRec"), "indx": op.get("Indx"),
                "perc_indx": _dec(op.get("PercIndx")), "var_camb": op.get("VarCamb"),
                "dt_venc_op": op.get("DtVencOp"), "cep": op.get("CEP"),
                "tax_eft": _dec(op.get("TaxEft")), "dt_contr": op.get("DtContr"),
                "prov_consttd": _dec(op.get("ProvConsttd")),
                "carac_especial": op.get("CaracEspecial"),
                "dia_atraso": _int(op.get("DiaAtraso")), "ipoc": ipoc,
            })

            v = op.find("Venc")
            if v is not None:
                row = {"cli_tp": cli_tp, "cli_cd": cli_cd, "contrt": contrt, "ipoc": ipoc}
                for vx in VENC_VERTICES:
                    row[vx] = _dec(v.get(vx))
                vencimentos.append(row)

            for g in op.findall("Gar"):
                ident = g.get("Ident")
                garantias.append({
                    "cli_tp": cli_tp, "cli_cd": cli_cd, "contrt": contrt, "ipoc": ipoc,
                    "gar_tp": g.get("Tp"), "ident": ident,
                    "perc_gar": _dec(g.get("PercGar")),
                    "vlr_orig": _dec(g.get("VlrOrig")),
                    "vlr_data": _dec(g.get("VlrData")),
                    "dt_reav": g.get("DtReav"),
                    "gar_categoria": "fidejussoria" if ident is not None else "real",
                })

            for c in op.findall("ContInstFinRes4966"):
                est = c.find("Estagio")
                cont4966.append({
                    "cli_tp": cli_tp, "cli_cd": cli_cd, "contrt": contrt, "ipoc": ipoc,
                    "clas_at_fin": c.get("ClasAtFin"),
                    "est_inst_fin": c.get("EstInstFin"),
                    "cart_prov_min": c.get("CartProvMin"),
                    "vlr_cont_br": _dec(c.get("VlrContBr")),
                    "tje": _dec(c.get("TJE")),
                    "rend_mes": _dec(c.get("RendMes")),
                    "estagio_motivo": est.get("Motivo") if est is not None else None,
                    "estagio_dt_alocacao": est.get("DtAlocacao") if est is not None else None,
                })

    return {
        "header": header,
        "clientes": clientes,
        "operacoes": operacoes,
        "garantias": garantias,
        "vencimentos": vencimentos,
        "cont4966": cont4966,
    }


# Note: the Python UDF that wraps _parse_3040 is created INSIDE raw_3040_doc()
# (not at module top-level) so that any UDF/serialization issue surfaces as a
# table-materialization error rather than silently preventing the @dlt.table
# decorator from registering.


# ── Bronze table ──────────────────────────────────────────────────────────────

@dlt.table(
    name="raw_3040_doc",
    comment="SCR 3040 — XML files ingestados do landing volume e parseados em struct tipado (1 linha por arquivo)",
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
    schema_location = _conf("schema_location_3040", f"/Volumes/{catalog}/{schema}/_checkpoints/bronze_3040_xml/")
    parse_3040_udf = F.udf(_parse_3040, DOC_SCHEMA)
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("cloudFiles.schemaLocation", schema_location)
        .option("pathGlobFilter", "Doc3040_*.xml")
        .load(landing_path)
        .withColumn("doc", parse_3040_udf(F.col("content")))
        .select(
            F.col("path").alias("file_path"),
            F.element_at(F.split(F.col("path"), "/"), -1).alias("file_name"),
            F.col("modificationTime").alias("file_modified_at"),
            F.col("length").alias("file_size_bytes"),
            F.col("doc.header").alias("header"),
            F.col("doc.clientes").alias("clientes"),
            F.col("doc.operacoes").alias("operacoes"),
            F.col("doc.garantias").alias("garantias"),
            F.col("doc.vencimentos").alias("vencimentos"),
            F.col("doc.cont4966").alias("cont4966"),
            F.lit("bcb_scr_xml").alias("_source_system"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.current_date().alias("_ingestion_date"),
        )
    )
