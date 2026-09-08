# Databricks notebook source
# MAGIC %md
# MAGIC # Silver CLÁSSICO — CADOC 2011 (DDR) → `silver.scr2011_*`
# MAGIC
# MAGIC Normaliza `bronze.raw_2011_doc` (uma linha por arquivo, arrays aninhados) em
# MAGIC **três** tabelas, uma por grão do leiaute:
# MAGIC
# MAGIC | Tabela | Grão | Conteúdo |
# MAGIC |---|---|---|
# MAGIC | `silver.scr2011_contas` | (cnpj_if, dt_base, codigo_conta) | valor de cada conta do Anexo 4 |
# MAGIC | `silver.scr2011_detalhamentos` | (cnpj_if, dt_base, codigo_conta, ordinal) | decomposição por país/moeda/posição |
# MAGIC | `silver.scr2011_parametros` | (cnpj_if, dt_base, codigo_parametro) | responsável pelo envio do DLO (Anexo 2) |
# MAGIC
# MAGIC **Data-base diária.** `dt_base` preserva o dia (fidelidade ao leiaute) e
# MAGIC `data_base_month` (`AAAA-MM`) liga o documento ao seletor de Data-Base MENSAL
# MAGIC compartilhado do app — não há seletor por CADOC. É também a coluna de escopo
# MAGIC dos checks DQX, que assim avaliam o mês corrente inteiro.
# MAGIC
# MAGIC **Dedupe no grão do DOCUMENTO** — `(cnpj_if, dt_base)`, não por conta como no
# MAGIC 4010: uma remessa `tipoEnvio = 'S'` reenvia o documento completo, e deduplicar
# MAGIC por conta misturaria contas de duas remessas.
# MAGIC
# MAGIC **Pivot dos eixos** — o eixo de detalhamento varia por conta (111000 por moeda
# MAGIC × posição; 210000 por país × moeda), então o leiaute usa lista chave-valor. Os
# MAGIC códigos do Anexo 3 viram colunas: `81`→`pais`, `83`→`moeda`,
# MAGIC `84`→`posicao_pais_exterior`; nulas quando a conta não usa o eixo.
# MAGIC
# MAGIC `documento` passa adiante SEM filtro, para o check `documento_e_2011` acusar
# MAGIC arquivo de outro CADOC na pasta do 2011.
# MAGIC
# MAGIC Pure ELT. Mesmas tabelas/contrato que
# MAGIC `pipelines/silver/transformations/scr2011.py`.

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

DOCUMENTO = "2011"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

# Códigos de elemento do Anexo 3 → coluna pivotada na silver.
ELEM_PAIS = "81"
ELEM_MOEDA = "83"
ELEM_POSICAO = "84"


def _silver_fqn(entidade):
    return f"{CATALOG}.{SILVER_SCHEMA}.scr{DOCUMENTO}_{entidade}"


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

# COMMAND ----------
# MAGIC %md
# MAGIC ## Documento deduplicado (uma remessa vigente por data-base)

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.raw_{DOCUMENTO}_doc")

_dedupe_w = Window.partitionBy("cnpj_if", "dt_base").orderBy(
    F.col("_ingestion_timestamp").desc()
)
doc = (
    bronze
    .withColumn("_rn", F.row_number().over(_dedupe_w))
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
# MAGIC %md
# MAGIC ## 1. `scr2011_contas` — valor por conta do Anexo 4

# COMMAND ----------

contas = (
    doc
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
        # Bloco = 1º dígito: 1 cambial · 2 liquidez · 3 RWACAM ·
        # 4 RWAJUR/COM/ACS · 5 RWAMPAD · 6 RWAMINT · 7 VPRM.
        F.substring(F.col("_c.codigoConta"), 1, 1).cast("int").alias("bloco_ddr"),
        F.when(F.col("_c.detalhamentosDDR.detalhamentoDDR").isNull(), F.lit(0))
         .otherwise(F.size("_c.detalhamentosDDR.detalhamentoDDR"))
         .alias("qtd_detalhamentos"),
        F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
        F.current_timestamp().alias("_silver_timestamp"),
    )
)

fqn_contas = _silver_fqn("contas")
(
    contas.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_contas)
)
print(f"OK — {fqn_contas}: {spark.table(fqn_contas).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. `scr2011_detalhamentos` — decomposição por país/moeda/posição
# MAGIC
# MAGIC `detalhamento_ord` (1-based) preserva a ordem do arquivo e dá chave estável à
# MAGIC linha: o leiaute NÃO garante unicidade de (conta, país, moeda, posição) — é a
# MAGIC crítica 4751, avaliada em `gold.criticas_ddr_2011`.

# COMMAND ----------

detalhamentos = (
    doc
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

fqn_det = _silver_fqn("detalhamentos")
(
    detalhamentos.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_det)
)
print(f"OK — {fqn_det}: {spark.table(fqn_det).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. `scr2011_parametros` — responsável pelo envio (Anexo 2)
# MAGIC
# MAGIC Nome (31), telefone (32) e email (33) do responsável pelo envio do DLO — a
# MAGIC trilha de accountability que a R.18 exige. Tabela própria em vez de colunas
# MAGIC repetidas em `scr2011_contas`.

# COMMAND ----------

parametros = (
    doc
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

fqn_par = _silver_fqn("parametros")
(
    parametros.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_par)
)
print(f"OK — {fqn_par}: {spark.table(fqn_par).count()} linha(s)")
