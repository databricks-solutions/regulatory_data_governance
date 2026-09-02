# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Estado de processamento (data-base corrente)
# MAGIC
# MAGIC Uma linha. Alimenta o seletor de Data-Base do app com o ÚLTIMO CADOC
# MAGIC processado. Vive no schema gold porque um pipeline DLT escreve em UM só
# MAGIC schema — não dá para gravar em `reference/` daqui.
# MAGIC
# MAGIC Equivalente ao clássico `pipelines/classical/gold/processing_state.py`. Aqui
# MAGIC as posições vêm por `dlt.read`, o que ordena este cálculo depois delas —
# MAGIC em troca, remover uma posição do `libraries:` quebra o grafo (o clássico
# MAGIC tolera a ausência).

# COMMAND ----------

import dlt
from pyspark.sql import functions as F


@dlt.table(
    name="processing_state",
    comment="Estado de processamento do pipeline gold — data-base do ultimo CADOC processado. O mes vigente e o MAX do mes observado em 3040/3050/4010/4060/2011 e current_data_base e o MAX dt_base DENTRO desse mes. Consumido pelo app para o seletor de Data-Base.",
    table_properties={"quality": "gold"},
)
def processing_state():
    # `dlt.read` (não spark.table) para tabelas do MESMO pipeline: é o que faz o
    # DLT ordenar este cálculo depois das posições.
    #
    # Seletor MENSAL e compartilhado: cada CADOC contribui com o MÊS da sua
    # data-base, o mês vigente é o maior deles e `current_data_base` é o maior
    # `dt_base` dentro dele. É essa redução que acomoda o DDR (diário) sem
    # tratamento especial. ⚠️ `posicao_4016` fica fora: semestral (jun/dez),
    # empurraria o seletor para um mês sem posição dos demais.
    contribuicoes = (
        dlt.read("posicao_3040").select("dt_base")
        .unionByName(dlt.read("posicao_3050").select("dt_base"))
        .unionByName(dlt.read("posicao_4010").select("dt_base"))
        # O 4060 (Conglomerado Prudencial) é MENSAL, então contribui.
        .unionByName(dlt.read("posicao_4060").select("dt_base"))
        .unionByName(dlt.read("posicao_2011").select("dt_base"))
        .withColumn("_mes", F.trunc(F.col("dt_base"), "month"))
    )
    mes_vigente = contribuicoes.agg(F.max("_mes").alias("_mes_vigente"))
    return (
        contribuicoes.join(
            F.broadcast(mes_vigente),
            contribuicoes["_mes"] == F.col("_mes_vigente"),
        )
        .agg(F.max("dt_base").alias("current_data_base"))
        .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
        .withColumn("updated_at", F.current_timestamp())
    )
