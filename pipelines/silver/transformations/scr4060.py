# Databricks notebook source
# MAGIC %md
# MAGIC # Silver DLT/SDP — CADOC 4060 → `scr4060_saldos_entidade`, `scr4060_saldos_consolidado`
# MAGIC
# MAGIC Versão declarativa. Produz as MESMAS tabelas e o MESMO contrato que o notebook
# MAGIC clássico `pipelines/classical/silver/scr4060.py` — ver lá a documentação completa.
# MAGIC
# MAGIC Normaliza `bronze.raw_4060_saldos` em **duas tabelas, uma por GRÃO do
# MAGIC leiaute** — mesmo critério já usado no DDR 2011.
# MAGIC
# MAGIC Leitura de bronze via `spark.table` (não `dlt.read`): bronze e silver são
# MAGIC pipelines DLT SEPARADOS e `dlt.read` só resolve datasets do MESMO pipeline
# MAGIC — ver "Bundle gotchas" no CLAUDE.md.
# MAGIC
# MAGIC Pure ELT: nenhuma coluna de qualidade, nenhum `_errors`/`_warnings`.

# COMMAND ----------

import uuid
import dlt
from pyspark.sql import functions as F, types as T, Window

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")

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
# MAGIC É o 1º dígito **significativo** do código, obtido por `cast(... as bigint)`
# MAGIC — nunca `substring(codigo_conta, 1, 1)`. Contas na forma legada vêm
# MAGIC zero-preenchidas à esquerda (`0031000000` = grupo 3), enquanto a forma
# MAGIC oficial de jan/2025 já começa no grupo (`1000000009` = grupo 1).

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
    """Deduplica mantendo a ingestão mais recente."""
    janela = Window.partitionBy(*chaves).orderBy(F.col("_ingestion_timestamp").desc())
    return df.withColumn("_rn", F.row_number().over(janela)).filter(F.col("_rn") == 1)

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_saldos_entidade",
    comment="Silver — Blocos com entidade (assemelhadas, dependências, participações). Uma linha por (conglomerado, data-base, bloco, entidade, conta).",
    partition_cols=["dt_base"],
)
def scr4060_saldos_entidade():
    """Blocos 4, 6 e 7: assemelhadas, dependências, participações."""
    bronze = spark.table(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_saldos")

    return (
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
        )
    )

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_saldos_consolidado",
    comment="Silver — Blocos consolidados (1, 2, 3, 5). Uma linha por (conglomerado, data-base, bloco, conta).",
    partition_cols=["dt_base"],
)
def scr4060_saldos_consolidado():
    """Blocos 1, 2, 3 e 5: consolidados com aglutinado/eliminações/consolidado."""
    bronze = spark.table(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_saldos")

    return (
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
        )
    )

# COMMAND ----------
# MAGIC %md
# MAGIC ## Equivalente ao clássico `pipelines/classical/silver/scr4060.py`
