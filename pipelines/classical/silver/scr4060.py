# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — CADOC 4060 → `silver.scr4060_*`
# MAGIC
# MAGIC Duas tabelas, uma por grão do leiaute:
# MAGIC
# MAGIC | Tabela | Grão | Blocos |
# MAGIC |---|---|---|
# MAGIC | `scr4060_saldos_entidade` | (conglomerado, data-base, bloco, entidade, conta) | 4 · 6 · 7 |
# MAGIC | `scr4060_saldos_consolidado` | (conglomerado, data-base, bloco, conta) | 1 · 2 · 3 · 5 |
# MAGIC
# MAGIC `dt_base` vira DATE (1º do mês); `dt_base_mes` guarda o `AAAA-MM` do leiaute.
# MAGIC Dedupe mantém a ingestão mais recente — é assim que `tipoRemessa = 'S'`
# MAGIC sobrepõe a inclusão original.
# MAGIC
# MAGIC `documento` passa adiante SEM filtro: um 4066 na pasta do 4060 tem de chegar
# MAGIC aqui para o check `documento_e_4060` acusar.
# MAGIC
# MAGIC Pure ELT — nenhuma coluna de qualidade.

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

DOCUMENTO = "4060"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

BLOCOS_ENTIDADE = ["assemelhadas", "dependenciasExterior", "participacoesExterior"]
BLOCOS_CONSOLIDADO = [
    "consolidadoPais", "consolidadoExterior",
    "consolidadoPaisExterior", "consolidadoPrudencial",
]

# COMMAND ----------
# MAGIC %md
# MAGIC ### Grupo COSIF
# MAGIC 1º dígito **significativo**, via `cast(... as bigint)` — nunca
# MAGIC `substring(codigo_conta, 1, 1)`. Conta legada vem zero-preenchida
# MAGIC (`0031000000` = grupo 3) e o 1º caractere devolveria `0`.

# COMMAND ----------

_GRUPO_COSIF = F.substring(
    F.col("codigo_conta").cast("bigint").cast("string"), 1, 1
).cast("int").alias("grupo_cosif")

_COMUM = [
    "documento",
    "codigo_conglomerado",
    "cnpj_lider",
    F.to_date(F.concat_ws("-", F.col("dt_base"), F.lit("01"))).alias("dt_base"),
    F.col("dt_base").alias("dt_base_mes"),
    "tipo_remessa",
    "taxa_conversao",
    "bloco",
]
_RODAPE = [
    "formato_origem",
    F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
    F.current_timestamp().alias("_silver_timestamp"),
]


def _dedupe(df, chaves: list[str]):
    janela = Window.partitionBy(*chaves).orderBy(F.col("_ingestion_timestamp").desc())
    return df.withColumn("_rn", F.row_number().over(janela)).filter(F.col("_rn") == 1)


def _gravar(df, nome: str, particao: str = "dt_base"):
    fqn = f"{CATALOG}.{SILVER_SCHEMA}.{nome}"
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy(particao)
        .saveAsTable(fqn)
    )
    print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
    return fqn


bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_saldos")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. `scr4060_saldos_entidade` — blocos 4, 6 e 7
# MAGIC Uma linha por entidade × conta. `saldo` unifica `saldoContabil`
# MAGIC (assemelhadas) e `saldo` (dependências/participações).

# COMMAND ----------

_gravar(
    _dedupe(
        bronze.filter(F.col("bloco").isin(BLOCOS_ENTIDADE)),
        ["codigo_conglomerado", "dt_base", "bloco", "entidade_id", "codigo_conta"],
    ).select(
        *_COMUM,
        "entidade_id",
        "tipo_assemelhada",
        "origem_assemelhada",
        "moeda_funcional",
        "motivo_consolidacao",
        "percent_consolidacao",
        "percent_participacao",
        "codigo_conta",
        _GRUPO_COSIF,
        F.coalesce(F.col("saldo_contabil"), F.col("saldo"))
         .cast("decimal(17,2)").alias("saldo"),
        "saldo_contabil",
        "saldo_ate_3m",
        "saldo_apos_3m",
        *_RODAPE,
    ),
    f"scr{DOCUMENTO}_saldos_entidade",
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. `scr4060_saldos_consolidado` — blocos 1, 2, 3 e 5
# MAGIC Os três valores do leiaute mais `diferenca_formacao` =
# MAGIC `saldo_consolidado − (saldo_aglutinado − valor_eliminacoes)`, que deveria
# MAGIC ser sempre zero. É a crítica **E3**, e calcular aqui deixa o check DQX ser
# MAGIC uma comparação de coluna.

# COMMAND ----------

_gravar(
    _dedupe(
        bronze.filter(F.col("bloco").isin(BLOCOS_CONSOLIDADO)),
        ["codigo_conglomerado", "dt_base", "bloco", "codigo_conta"],
    ).select(
        *_COMUM,
        "codigo_conta",
        _GRUPO_COSIF,
        "saldo_aglutinado",
        "valor_eliminacoes",
        "saldo_consolidado",
        (
            F.coalesce(F.col("saldo_consolidado"), F.lit(0))
            - (
                F.coalesce(F.col("saldo_aglutinado"), F.lit(0))
                - F.coalesce(F.col("valor_eliminacoes"), F.lit(0))
            )
        ).cast("decimal(17,2)").alias("diferenca_formacao"),
        *_RODAPE,
    ),
    f"scr{DOCUMENTO}_saldos_consolidado",
)
