# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze CLÁSSICO — SCR 3040 XML Ingestion (Auto Loader, sem DLT/SDP)
# MAGIC
# MAGIC Versão **clássica** (job Databricks + notebook PySpark) do bronze 3040.
# MAGIC Produz exatamente a mesma tabela `bronze.raw_3040_doc` e o mesmo contrato
# MAGIC downstream (header struct + 5 arrays denormalizados) que o pipeline
# MAGIC DLT em `pipelines/bronze/transformations/raw_3040.py`, porém **sem**
# MAGIC `import dlt` nem `@dlt.table`:
# MAGIC
# MAGIC * lê via Auto Loader (`cloudFiles`, XML nativo na JVM);
# MAGIC * escreve com `writeStream.trigger(availableNow=True).toTable(...)` +
# MAGIC   checkpoint explícito — ingestão incremental e idempotente, cada run
# MAGIC   processa só os arquivos novos, sem nenhum recurso SDP.
# MAGIC
# MAGIC Os caminhos de schema/checkpoint são DISTINTOS dos usados pelo pipeline
# MAGIC DLT (`classical_*`) para que trocar de modo não colida com estado de
# MAGIC Auto Loader pré-existente.

# COMMAND ----------

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
# Caminhos DISTINTOS do pipeline DLT (`bronze_3040_xml_native`) — Auto Loader
# guarda estado format-específico e reusar o path do outro modo quebra.
schema_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3040_schema/"
checkpoint_location = f"/Volumes/{catalog}/{landing_schema}/_checkpoints/classical_bronze_3040_chk/"
target_table = f"{catalog}.{bronze_schema}.raw_3040_doc"

print(f"landing_path        = {landing_path}")
print(f"target_table        = {target_table}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Schema XML nativo (BACEN Doc 3040 wire format)
# MAGIC `attributePrefix=""` → atributos viram campos sem underscore. Idêntico ao
# MAGIC pipeline DLT.

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

# COMMAND ----------
# MAGIC %md
# MAGIC ## Leitura (Auto Loader XML nativo) + reshape para o contrato bronze
# MAGIC Reshape idêntico ao pipeline DLT — `transform`/`flatten`/`filter`
# MAGIC JVM-nativos, sem UDF.

# COMMAND ----------

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

reshaped = (
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

print(f"OK — {target_table}: {spark.table(target_table).count()} linha(s)")
