# Databricks notebook source
# MAGIC %md
# MAGIC # Silver DLT/SDP — CADOC 2011 (DDR) → `scr2011_contas` · `scr2011_detalhamentos` · `scr2011_parametros`
# MAGIC
# MAGIC MESMAS tabelas e MESMO contrato que o clássico
# MAGIC `pipelines/classical/silver/scr2011.py` — ver lá a documentação completa
# MAGIC (data-base diária dentro do mês, dedupe no grão do documento e pivot dos
# MAGIC elementos do Anexo 3).
# MAGIC
# MAGIC O DDR é o único CADOC **diário** do acelerador: `dt_base` guarda o dia e
# MAGIC `data_base_month` (`AAAA-MM`) o liga ao seletor de Data-Base MENSAL
# MAGIC compartilhado do app.
# MAGIC
# MAGIC Três tabelas porque o leiaute tem três grãos (`parametros`, `contas` e os
# MAGIC `detalhamentos` dentro de cada conta). Todas no MESMO schema — um pipeline
# MAGIC DLT escreve num único schema (`schema:` do recurso).
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

DOCUMENTO = "2011"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

# Códigos de elemento do Anexo 3 → coluna pivotada na silver.
ELEM_PAIS = "81"
ELEM_MOEDA = "83"
ELEM_POSICAO = "84"


def _elemento(array_col, codigo):
    """Extrai `valorElemento` do `detalhe` com `codigoElemento` = `codigo`.

    O XSD garante unicidade do código dentro de cada `detalhamentoDDR`, então a
    lista filtrada tem 0 ou 1 item. `array_max` devolve NULL em lista vazia,
    evitando o erro de índice de `element_at(..., 1)`.
    """
    return F.expr(
        f"array_max(transform(filter({array_col}, "
        f"e -> e.codigoElemento = '{codigo}'), e -> e.valorElemento))"
    )


def _documento_vigente():
    """Uma remessa por (cnpj_if, dt_base) — a de ingestão mais recente.

    `tipoEnvio = 'S'` reenvia o documento completo, então o dedupe é no grão do
    DOCUMENTO (não por conta como no 4010).
    """
    bronze = spark.table(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_doc")
    dedupe_w = Window.partitionBy("cnpj_if", "dt_base").orderBy(
        F.col("_ingestion_timestamp").desc()
    )
    return (
        bronze
        .withColumn("_rn", F.row_number().over(dedupe_w))
        .filter(F.col("_rn") == 1)
        .select(
            "documento",
            "tipo_envio",
            "cnpj_if",
            F.to_date("dt_base").alias("dt_base"),
            F.date_format(F.to_date("dt_base"), "yyyy-MM").alias("data_base_month"),
            "parametros",
            "contas",
        )
    )

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_contas",
    comment="Silver — DDR (Doc 2011, diario) normalizado no grao da conta do Anexo 4. valor_conta + bloco_ddr (1 exposicao cambial · 2 liquidez · 3 RWACAM · 4 RWAJUR/COM/ACS · 5 RWAMPAD · 6 RWAMINT · 7 VPRM).",
    partition_cols=["dt_base"],
)
def scr2011_contas():
    return (
        _documento_vigente()
        .select(
            "documento", "tipo_envio", "cnpj_if", "dt_base", "data_base_month",
            F.explode("contas").alias("_c"),
        )
        .select(
            "documento",
            "cnpj_if",
            "dt_base",
            "data_base_month",
            "tipo_envio",
            F.col("_c.codigoConta").alias("codigo_conta"),
            F.col("_c.valorConta").cast("decimal(17,2)").alias("valor_conta"),
            F.substring(F.col("_c.codigoConta"), 1, 1).cast("int").alias("bloco_ddr"),
            F.when(F.col("_c.detalhamentosDDR.detalhamentoDDR").isNull(), F.lit(0))
             .otherwise(F.size("_c.detalhamentosDDR.detalhamentoDDR"))
             .alias("qtd_detalhamentos"),
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_detalhamentos",
    comment="Silver — decomposicao dos valores do DDR por pais (elem 81), moeda (elem 83) e posicao pais/exterior (elem 84). detalhamento_ord preserva a ordem do arquivo; a duplicidade de chave e avaliada pela critica 4751 em gold.criticas_ddr_2011.",
    partition_cols=["dt_base"],
)
def scr2011_detalhamentos():
    return (
        _documento_vigente()
        .select(
            "documento", "cnpj_if", "dt_base", "data_base_month",
            F.explode("contas").alias("_c"),
        )
        .select(
            "documento", "cnpj_if", "dt_base", "data_base_month",
            F.col("_c.codigoConta").alias("codigo_conta"),
            F.col("_c.detalhamentosDDR.detalhamentoDDR").alias("_dets"),
        )
        .filter(F.col("_dets").isNotNull())
        .select(
            "documento", "cnpj_if", "dt_base", "data_base_month", "codigo_conta",
            F.posexplode("_dets").alias("_ord", "_d"),
        )
        .select(
            "documento",
            "cnpj_if",
            "dt_base",
            "data_base_month",
            "codigo_conta",
            (F.col("_ord") + F.lit(1)).alias("detalhamento_ord"),
            F.col("_d.valorDetalhe").cast("decimal(17,2)").alias("valor_detalhe"),
            _elemento("_d.detalhe", ELEM_PAIS).alias("pais"),
            _elemento("_d.detalhe", ELEM_MOEDA).alias("moeda"),
            _elemento("_d.detalhe", ELEM_POSICAO).alias("posicao_pais_exterior"),
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )

# COMMAND ----------


@dlt.table(
    name=f"scr{DOCUMENTO}_parametros",
    comment="Silver — parametros do DDR (Anexo 2): nome (31), telefone (32) e email (33) do responsavel pelo envio do DLO. Trilha de accountability exigida pela R.18.",
    partition_cols=["dt_base"],
)
def scr2011_parametros():
    return (
        _documento_vigente()
        .select(
            "documento", "cnpj_if", "dt_base", "data_base_month",
            F.explode("parametros").alias("_p"),
        )
        .select(
            "documento",
            "cnpj_if",
            "dt_base",
            "data_base_month",
            F.col("_p.codigoParametro").alias("codigo_parametro"),
            F.col("_p.valorParametro").alias("valor_parametro"),
            F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
            F.current_timestamp().alias("_silver_timestamp"),
        )
    )
