# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze — SCR 3050 / DocTXB V11 XML Ingestion
# MAGIC
# MAGIC Ingests `Doc3050_<CNPJ>_<DtBase>_R<Remessa>_P<Parte>.xml` files from the landing
# MAGIC volume and parses them into a typed nested struct matching the BACEN wire format
# MAGIC (see `sample/Doc3050_99999999_2026-03_R1_P1.xml`):
# MAGIC
# MAGIC ```
# MAGIC <DocTXB cnpjInstituicao dataBase indRemessa nmContato telContato>
# MAGIC   <referencia dataRef>
# MAGIC     <diario|mensal>
# MAGIC       <crdLivre|crdDirec>
# MAGIC         <pesJuridica|pesFisica>
# MAGIC           <pre|flu|vc|ipca|igpm|ind>
# MAGIC             <modalidade-tag attr1=... attr2=.../>+
# MAGIC ```
# MAGIC
# MAGIC The `modalidade-tag` is the *element name* (e.g. `capGirPrzAte365`); the metric
# MAGIC values live on its attributes. The parser walks the four-level hierarchy and
# MAGIC pivots `(carteira, segmento, encargo, modalidade)` into rows.
# MAGIC
# MAGIC Output table `raw_3050_doc` carries one row per XML file with `header` + nested
# MAGIC arrays `diario` and `mensal`. Silver explodes both arrays into a single
# MAGIC `scr3050` table with a `periodicidade` column.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, ArrayType,
)

# Pipeline configuration — read inside the table function (NOT at module level).
# See raw_3040.py for why module-level spark.conf.get is unsafe in DLT.

def _conf(key, default):
    try:
        return spark.conf.get(key)
    except Exception:
        return default


# ── Schema ────────────────────────────────────────────────────────────────────

HEADER_SCHEMA = StructType([
    StructField("cnpj_if", StringType()),
    StructField("dt_base", StringType()),
    StructField("ind_remessa", StringType()),
    StructField("nm_contato", StringType()),
    StructField("tel_contato", StringType()),
    StructField("dt_referencia", StringType()),
])

DIARIO_SCHEMA = StructType([
    StructField("carteira", StringType()),
    StructField("segmento", StringType()),
    StructField("encargo", StringType()),
    StructField("modalidade", StringType()),
    StructField("tx_med_juros", DecimalType(8, 2)),
    StructField("tx_med_enc_fiscais", DecimalType(8, 2)),
    StructField("tx_med_enc_operacionais", DecimalType(8, 2)),
    StructField("vlr_concessoes", DecimalType(18, 0)),
    StructField("prz_dec_med_concessoes", IntegerType()),
    StructField("sld_car_ativa", DecimalType(18, 0)),
])

MENSAL_SCHEMA = StructType([
    StructField("carteira", StringType()),
    StructField("segmento", StringType()),
    StructField("encargo", StringType()),
    StructField("modalidade", StringType()),
    StructField("sld_bai_prejuizo", DecimalType(18, 0)),
    StructField("sld_car_ate14", DecimalType(18, 0)),
    StructField("sld_car_ate60", DecimalType(18, 0)),
    StructField("sld_car_ate90", DecimalType(18, 0)),
    StructField("sld_car_maior90", DecimalType(18, 0)),
    StructField("prz_med_carteira", IntegerType()),
])

DOC_SCHEMA = StructType([
    StructField("header", HEADER_SCHEMA),
    StructField("diario", ArrayType(DIARIO_SCHEMA)),
    StructField("mensal", ArrayType(MENSAL_SCHEMA)),
])

DIARIO_ATTRS = [
    ("tx_med_juros", "txMedJuros"),
    ("tx_med_enc_fiscais", "txMedEncFiscais"),
    ("tx_med_enc_operacionais", "txMedEncOperacionais"),
    ("vlr_concessoes", "vlrConcessoes"),
    ("prz_dec_med_concessoes", "przDecMedConcessoes"),
    ("sld_car_ativa", "sldCarAtiva"),
]

MENSAL_ATTRS = [
    ("sld_bai_prejuizo", "sldBaiPrejuizo"),
    ("sld_car_ate14", "sldCarAte14"),
    ("sld_car_ate60", "sldCarAte60"),
    ("sld_car_ate90", "sldCarAte90"),
    ("sld_car_maior90", "sldCarMaior90"),
    ("prz_med_carteira", "przMedCarteira"),
]

INTEGER_ATTRS = {"prz_dec_med_concessoes", "prz_med_carteira"}


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_3050(content):
    from lxml import etree

    if content is None:
        return None
    root = etree.fromstring(content)
    referencia = root.find("referencia")

    header = {
        "cnpj_if": root.get("cnpjInstituicao"),
        "dt_base": root.get("dataBase"),
        "ind_remessa": root.get("indRemessa"),
        "nm_contato": root.get("nmContato"),
        "tel_contato": root.get("telContato"),
        "dt_referencia": referencia.get("dataRef") if referencia is not None else None,
    }

    if referencia is None:
        return {"header": header, "diario": [], "mensal": []}

    def _dec(s): return None if s in (None, "") else s
    def _int(s):
        if s in (None, ""):
            return None
        try: return int(s)
        except (ValueError, TypeError): return None

    def walk(period_el, attr_pairs, target):
        if period_el is None:
            return
        for carteira_el in period_el:
            carteira = carteira_el.tag
            for segmento_el in carteira_el:
                segmento = segmento_el.tag
                for encargo_el in segmento_el:
                    encargo = encargo_el.tag
                    for mod_el in encargo_el:
                        row = {
                            "carteira": carteira,
                            "segmento": segmento,
                            "encargo": encargo,
                            "modalidade": mod_el.tag,
                        }
                        for snake, bcb_name in attr_pairs:
                            v = mod_el.get(bcb_name)
                            row[snake] = _int(v) if snake in INTEGER_ATTRS else _dec(v)
                        target.append(row)

    diario_rows, mensal_rows = [], []
    walk(referencia.find("diario"), DIARIO_ATTRS, diario_rows)
    walk(referencia.find("mensal"), MENSAL_ATTRS, mensal_rows)

    return {"header": header, "diario": diario_rows, "mensal": mensal_rows}


# Note: the Python UDF that wraps _parse_3050 is created INSIDE raw_3050_doc()
# (not at module top-level) so that any UDF/serialization issue surfaces as a
# table-materialization error rather than silently preventing the @dlt.table
# decorator from registering.


# ── Bronze table ──────────────────────────────────────────────────────────────

@dlt.table(
    name="raw_3050_doc",
    comment="SCR 3050 / DocTXB V11 — XML files ingestados e parseados em struct tipado (1 linha por arquivo)",
    table_properties={
        "quality": "bronze",
        "delta.logRetentionDuration": "interval 1825 days",
        "delta.deletedFileRetentionDuration": "interval 1825 days",
    },
    partition_cols=["_ingestion_date"],
)
def raw_3050_doc():
    catalog = _conf("source_catalog", "rc18_catalog")
    schema = _conf("source_schema", "landing")
    landing_path = _conf("landing_path_3050", f"/Volumes/{catalog}/{schema}/scr_xml/3050/")
    schema_location = _conf("schema_location_3050", f"/Volumes/{catalog}/{schema}/_checkpoints/bronze_3050_xml/")
    parse_3050_udf = F.udf(_parse_3050, DOC_SCHEMA)
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("cloudFiles.schemaLocation", schema_location)
        .option("pathGlobFilter", "Doc3050_*.xml")
        .load(landing_path)
        .withColumn("doc", parse_3050_udf(F.col("content")))
        .select(
            F.col("path").alias("file_path"),
            F.element_at(F.split(F.col("path"), "/"), -1).alias("file_name"),
            F.col("modificationTime").alias("file_modified_at"),
            F.col("length").alias("file_size_bytes"),
            F.col("doc.header").alias("header"),
            F.col("doc.diario").alias("diario"),
            F.col("doc.mensal").alias("mensal"),
            F.lit("bcb_scr_xml").alias("_source_system"),
            F.current_timestamp().alias("_ingestion_timestamp"),
            F.current_date().alias("_ingestion_date"),
        )
    )
