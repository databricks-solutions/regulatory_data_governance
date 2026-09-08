# Databricks notebook source
# MAGIC %md
# MAGIC # Silver CLÁSSICO — CADOC 4010 (Balancete Patrimonial Analítico) → `silver.scr4010_saldos`
# MAGIC
# MAGIC Normaliza `bronze.raw_4010_saldos` → `silver.scr4010_saldos`.
# MAGIC
# MAGIC Este é o documento MENSAL e é a **perna contábil do batimento
# MAGIC inter-CADOC** (SCR 3040 × COSIF, crítica N01) — `gold.reconciliacao_cosif`
# MAGIC lê esta tabela.
# MAGIC
# MAGIC `dt_base` é promovida a DATE (1º dia do mês) e `dt_base_mes` preserva o
# MAGIC `AAAA-MM` textual do leiaute. Dedupe por (cnpj_if, dt_base, codigo_conta)
# MAGIC mantendo a ingestão mais recente — é assim que uma remessa de substituição
# MAGIC (`tipoRemessa = 'S'`) sobrepõe a inclusão original já aceita pelo BCB.
# MAGIC
# MAGIC A coluna `documento` é passada adiante **sem filtro**: um arquivo do
# MAGIC 4016 depositado por engano na pasta do 4010 tem de chegar até aqui
# MAGIC para o check DQX `documento_e_4010` acusar, em vez de desaparecer em
# MAGIC silêncio.
# MAGIC
# MAGIC Pure ELT: nenhuma coluna de qualidade, nenhum `_errors`/`_warnings`.
# MAGIC MESMA tabela/contrato que o DLT `pipelines/silver/transformations/scr4010.py`.

# COMMAND ----------

import uuid
from pyspark.sql import functions as F, Window

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("silver_schema", "silver")

CATALOG = dbutils.widgets.get("catalog")
BRONZE_SCHEMA = dbutils.widgets.get("bronze_schema")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")

DOCUMENTO = "4010"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_saldos")

_dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "codigo_conta").orderBy(
    F.col("_ingestion_timestamp").desc()
)
silver = (
    bronze
    .withColumn("_rn", F.row_number().over(_dedupe_w))
    .filter(F.col("_rn") == 1)
    .select(
        "documento",
        "cnpj_if",
        F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
        F.col("dt_base").alias("dt_base_mes"),       # AAAA-MM textual do leiaute
        "codigo_conta",                              # conta COSIF 10 dígitos
        # Grupo COSIF = 1º dígito SIGNIFICATIVO do código. Não é
        # `substring(codigo_conta, 1, 1)`: contas na forma legada vêm
        # zero-preenchidas à esquerda até 10 posições (`0031000000` = grupo 3),
        # enquanto a forma oficial de jan/2025 já começa no grupo
        # (`1000000009` = grupo 1). Passar por bigint descarta o padding e
        # resolve as duas formas.
        F.substring(
            F.col("codigo_conta").cast("bigint").cast("string"), 1, 1
        ).cast("int").alias("grupo_cosif"),
        F.col("saldo").cast("decimal(17,2)").alias("saldo"),
        "sinal",                                     # nulo quando a origem é XML
        "tipo_remessa",
        "formato_origem",
        F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
        F.current_timestamp().alias("_silver_timestamp"),
    )
)

fqn = f"{CATALOG}.{SILVER_SCHEMA}.scr{DOCUMENTO}_saldos"
(
    silver.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn)
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
