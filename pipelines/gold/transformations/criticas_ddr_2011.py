# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Críticas intra-DDR (Doc 2011)
# MAGIC
# MAGIC Das 11 críticas vigentes, só estas duas confrontam o próprio DDR (as
# MAGIC outras 9 batem contra os docs 2060/DRM e 2061/DLO, fora do escopo):
# MAGIC
# MAGIC | Crítica | Tipo | Regra |
# MAGIC |---|---|---|
# MAGIC | 4693 | E | 161000 (vendidas no PL) >= 181000 (excesso de hedge) |
# MAGIC | 4751 | I | chaves duplicadas entre posição e moeda nos detalhamentos |
# MAGIC
# MAGIC São de grão AGREGADO e a `sql_expression` do DQX roda linha a linha, então
# MAGIC materializamos com `status` e o check só olha o status — mesmo padrão da N01
# MAGIC em `reconciliacao_cosif`. Ver `docs/ddr2011/README.md`.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/criticas_ddr_2011.py`.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")

_CRIT_OK = "OK"
_CRIT_BLOQUEADO = "BLOQUEADO"


def _criticas_ddr_2011(contas, detalhamentos):
    """Avalia as críticas 4693 e 4751 por (cnpj_if, dt_base)."""
    # 4693 — soma de 161000 vs soma de 181000 na mesma data-base.
    por_data = (
        contas.groupBy("cnpj_if", "dt_base", "data_base_month")
        .agg(
            F.sum(F.when(F.col("codigo_conta") == "161000", F.col("valor_conta")))
             .alias("vlr_esquerdo"),
            F.sum(F.when(F.col("codigo_conta") == "181000", F.col("valor_conta")))
             .alias("vlr_direito"),
        )
    )
    c4693 = por_data.select(
        "cnpj_if", "dt_base", "data_base_month",
        F.lit("4693").alias("critica_id"),
        F.lit("E").alias("tipo_critica"),
        F.lit(
            "Somatorio das Posicoes Vendidas no Patrimonio Liquido (161000) inferior ao "
            "Excesso da Posicao Vendida para Hedge em Participacoes no Exterior (181000)."
        ).alias("descricao_critica"),
        F.col("vlr_esquerdo").cast("decimal(17,2)").alias("vlr_esquerdo"),
        F.col("vlr_direito").cast("decimal(17,2)").alias("vlr_direito"),
        F.lit(None).cast("bigint").alias("qtd_ocorrencias"),
        # Sem uma das duas contas na remessa não há o que confrontar → OK.
        F.when(
            F.col("vlr_esquerdo").isNull() | F.col("vlr_direito").isNull(), F.lit(_CRIT_OK)
        ).when(
            F.col("vlr_esquerdo") < F.col("vlr_direito"), F.lit(_CRIT_BLOQUEADO)
        ).otherwise(F.lit(_CRIT_OK)).alias("status"),
    )

    # 4751 — a chave (conta, país, moeda, posição) não pode repetir na data-base.
    # `count(*) - count(distinct)` = linhas excedentes, o que o BCB reporta.
    dup = (
        detalhamentos.groupBy("cnpj_if", "dt_base", "data_base_month")
        .agg(
            (
                F.count(F.lit(1))
                - F.countDistinct(
                    F.concat_ws(
                        "|",
                        F.col("codigo_conta"),
                        F.coalesce(F.col("pais"), F.lit("")),
                        F.coalesce(F.col("moeda"), F.lit("")),
                        F.coalesce(F.col("posicao_pais_exterior"), F.lit("")),
                    )
                )
            ).alias("qtd_ocorrencias")
        )
    )
    c4751 = dup.select(
        "cnpj_if", "dt_base", "data_base_month",
        F.lit("4751").alias("critica_id"),
        F.lit("I").alias("tipo_critica"),
        F.lit("Chaves duplicadas entre posicao e moeda nos detalhamentos do DDR.")
         .alias("descricao_critica"),
        F.lit(None).cast("decimal(17,2)").alias("vlr_esquerdo"),
        F.lit(None).cast("decimal(17,2)").alias("vlr_direito"),
        F.col("qtd_ocorrencias").cast("bigint").alias("qtd_ocorrencias"),
        F.when(F.col("qtd_ocorrencias") > 0, F.lit(_CRIT_BLOQUEADO))
         .otherwise(F.lit(_CRIT_OK)).alias("status"),
    )

    return c4693.unionByName(c4751).withColumn(
        "_gold_timestamp", F.current_timestamp()
    )


@dlt.table(
    name="criticas_ddr_2011",
    comment="Criticas INTRA-documento do DDR (Doc 2011): 4693 (161000 >= 181000, tipo E) e 4751 (chaves duplicadas posicao x moeda, tipo I). Uma linha por (cnpj_if, dt_base, critica_id) com status OK/BLOQUEADO. As outras 9 criticas vigentes confrontam os documentos 2060/2061 e ficam fora do escopo.",
    table_properties={"quality": "gold"},
    partition_cols=["dt_base"],
)
def criticas_ddr_2011():
    return _criticas_ddr_2011(
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr2011_contas"),
        spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr2011_detalhamentos"),
    )
