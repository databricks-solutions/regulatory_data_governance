# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — SCR 3050 / DocTXB V11 XML Ingestion (sem DLT/SDP)
# MAGIC
# MAGIC Versão **clássica** (job + notebook PySpark) do bronze 3050. Produz a
# MAGIC mesma tabela `bronze.raw_3050_doc` que o pipeline DLT
# MAGIC (`pipelines/bronze/transformations/raw_3050.py`), com o mesmo parser
# MAGIC `binaryFile + lxml` (a taxonomia TXB V11 usa *nomes de elemento* como eixo
# MAGIC de dimensão, então schema XML nativo não se aplica).
# MAGIC
# MAGIC Diferença: escreve com `writeStream.trigger(availableNow=True)` +
# MAGIC checkpoint explícito em vez de `@dlt.table`. `lxml` é instalada no job
# MAGIC clássico (ver resources/classical/*.yml, environment.dependencies).

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, ArrayType,
)

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("landing_schema", "landing")
dbutils.widgets.text("bronze_schema", "bronze")

catalog = dbutils.widgets.get("catalog")
landing_schema = dbutils.widgets.get("landing_schema")
bronze_schema = dbutils.widgets.get("bronze_schema")

landing_path = f"/Volumes/{catalog}/{landing_schema}/scr_xml/3050/"
schema_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3050_schema/"
checkpoint_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3050_chk/"
target_table = f"{catalog}.{bronze_schema}.raw_3050_doc"

print(f"landing_path = {landing_path}")
print(f"target_table = {target_table}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema alvo do struct parseado

# COMMAND ----------

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

# COMMAND ----------
# MAGIC %md
# MAGIC ## Parser lxml (idêntico ao pipeline DLT)

# COMMAND ----------

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

# COMMAND ----------
# MAGIC %md
# MAGIC ## Leitura (Auto Loader binaryFile) + parse + escrita incremental

# COMMAND ----------

parse_3050_udf = F.udf(_parse_3050, DOC_SCHEMA)

parsed = (
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

query = (
    parsed.writeStream
    .format("delta")
    .option("checkpointLocation", checkpoint_location)
    .partitionBy("_ingestion_date")
    .trigger(availableNow=True)
    .toTable(target_table)
)
query.awaitTermination()

spark.sql(
    f"ALTER TABLE {target_table} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'bronze')"
)

print(f"OK — {target_table}: {spark.table(target_table).count()} linha(s)")
