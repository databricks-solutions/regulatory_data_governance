# Databricks notebook source
# MAGIC %md
# MAGIC # Silver DLT/SDP — CADOC 4016 (Balanço Patrimonial Analítico) → `scr4016_saldos`
# MAGIC
# MAGIC MESMA tabela e MESMO contrato que o clássico
# MAGIC `pipelines/classical/silver/scr4016.py` — ver lá a documentação completa.
# MAGIC
# MAGIC Documento SEMESTRAL (junho/dezembro). Posição APÓS a apuração do
# MAGIC resultado, então não deve trazer contas dos grupos 7 (Receitas) e 8
# MAGIC (Despesas) — check `sem_contas_de_resultado_grupos_7_8` na DQX Studio.
# MAGIC NÃO entra no batimento com o 3040 (que é mensal).
# MAGIC
# MAGIC Leitura de bronze via `spark.table` (não `dlt.read`): bronze e silver são
# MAGIC pipelines DLT SEPARADOS e `dlt.read` só resolve datasets do MESMO pipeline
# MAGIC — ver "Bundle gotchas" no CLAUDE.md.

# COMMAND ----------

import uuid
import dlt
from pyspark.sql import functions as F, Window

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")

DOCUMENTO = "4016"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_saldos",
    comment="Silver — Balanço Patrimonial Analítico (Doc 4016, semestral: jun/dez) normalizado. Posição APÓS a apuração do resultado — não se esperam contas dos grupos 7 (Receitas) e 8 (Despesas).",
    partition_cols=["dt_base"],
)
def scr4016_saldos():
    bronze = spark.table(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_saldos")
    dedupe_w = Window.partitionBy("cnpj_if", "dt_base", "codigo_conta").orderBy(
        F.col("_ingestion_timestamp").desc()
    )
    return (
        bronze
        .withColumn("_rn", F.row_number().over(dedupe_w))
        .filter(F.col("_rn") == 1)
        .select(
            "documento",
            "cnpj_if",
            F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
            F.col("dt_base").alias("dt_base_mes"),
            "codigo_conta",
            # Grupo COSIF = 1º dígito SIGNIFICATIVO (não `substring(...,1,1)`):
            # a forma legada vem zero-preenchida até 10 posições
            # (`0031000000` = grupo 3) e a oficial de jan/2025 já começa no grupo
            # (`1000000009` = grupo 1). Passar por bigint resolve as duas.
            F.substring(
                F.col("codigo_conta").cast("bigint").cast("string"), 1, 1
            ).cast("int").alias("grupo_cosif"),
            F.col("saldo").cast("decimal(17,2)").alias("saldo"),
            "sinal",
            "tipo_remessa",
            "formato_origem",
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )
