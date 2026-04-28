# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Motor de Agregação 3050 (TXB V11)
# MAGIC
# MAGIC Núcleo lógico do gerador. Sobre os microdados 3040 ingeridos em 01, aplica
# MAGIC as regras de equivalência do BACEN e produz os agregados do Documento 3050
# MAGIC no modelo TXB V11 (codificação real do XSD).
# MAGIC
# MAGIC ## Regras implementadas (ref. Instruções de Preenchimento do Doc 3050)
# MAGIC
# MAGIC | # | Regra                                                                             | §     |
# MAGIC |---|------------------------------------------------------------------------------------|-------|
# MAGIC | 1 | DE/PARA Mod(3040) → (recursos, modalidade TXB) conforme 00_Setup_e_Equivalencia  | PDF Equivalência |
# MAGIC | 2 | Segmento = `pesFisica` se `cli.tp ∈ {1,3,5}`; `pesJuridica` se ∈ `{2,4,6}`       | §3    |
# MAGIC | 3 | Encargo = `derive_encargo(indx, recursos)` — mapa Anexo 5 do 3040 → §4 do 3050   | §4    |
# MAGIC | 4 | **Taxa média de juros ponderada pelo saldo da carteira ativa** (fórmula §6.1)    | §6.1  |
# MAGIC | 5 | Valor das concessões = Σ `vlr_op` onde `dt_contr ∈ [DtBase, DtBase+1M)`          | §6.2  |
# MAGIC | 6 | Prazo médio das concessões (dias entre `dt_contr` e `dt_venc_op`)                | §6.3  |
# MAGIC | 7 | Saldo da carteira ativa = Σ `saldo_ativo` (buckets v110..v180 do 3040)            | §6.4  |
# MAGIC | 8 | Saldo por faixas de atraso (0-14, 15-60, 61-90, >90) — MVP: tudo em "ate14"       | §6.8  |
# MAGIC | 9 | Prazo médio carteira ativa (ponderado pelo saldo)                                 | §6.9  |
# MAGIC
# MAGIC ## Regra de Ouro #1 — Consistência 3040 vs 3050
# MAGIC Após agregação: `Σ sldCarAtiva_3050 == Σ vlr_op_3040` (com tolerância de R$1).
# MAGIC
# MAGIC ## Saída
# MAGIC Duas tabelas Delta, uma linha por combinação `(recursos, segmento, encargo, modalidade)`:
# MAGIC - `f_3050_diario` — atributos do modelo diário do XSD (modeloN_D_GrpAtrib).
# MAGIC - `f_3050_mensal` — atributos do modelo mensal (modeloN_M_GrpAtrib).

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Equivalencia

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructType, StructField, IntegerType

stg_table = f"{CATALOG}.{SCHEMA}.stg_3050_microdados_from_3040"
df = spark.table(stg_table)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 1 — Aplicar DE/PARA via broadcast dict
# MAGIC O `DE_PARA_3040_3050` (dicionário Python definido em 00) é distribuído
# MAGIC como UDF para evitar overhead de join com tabela de referência em datasets
# MAGIC pequenos/médios.

# COMMAND ----------

from pyspark.sql.functions import udf


RET_SCHEMA = StructType([
    StructField("recursos_3050",      StringType(), True),
    StructField("modalidade_3050",    StringType(), True),
    StructField("segmento_default",   StringType(), True),
    StructField("encargo_default",    StringType(), True),
])

# Serverless não suporta spark.sparkContext.broadcast. O PySpark serializa os
# dicts via closure quando capturados no escopo do UDF — suficiente para
# dicionários pequenos como os nossos (<1 KB cada).
_DE_PARA_LOCAL   = dict(DE_PARA_3040_3050)
_FALLBACK_LOCAL  = dict(DE_PARA_FALLBACK)
_SEG_LOCAL       = dict(SEG_DE_PARA)


@udf(returnType=RET_SCHEMA)
def map_mod_3050(mod: str):
    entry = _DE_PARA_LOCAL.get(mod) if mod else None
    if not entry:
        entry = _FALLBACK_LOCAL
    return {
        "recursos_3050":    entry["recursos"],
        "modalidade_3050":  entry["modalidade"],
        "segmento_default": entry["segmento_default"],
        "encargo_default":  entry["encargo_default"],
    }


@udf(returnType=StringType())
def map_segmento(cli_tp: str):
    return _SEG_LOCAL.get(cli_tp, "pesJuridica")


df = (
    df
    .withColumn("mapa", map_mod_3050(F.col("mod")))
    .withColumn("recursos_3050",   F.col("mapa.recursos_3050"))
    .withColumn("modalidade_3050", F.col("mapa.modalidade_3050"))
    .withColumn("encargo_default", F.col("mapa.encargo_default"))
    # Segmento real vem de cli.tp, mas caímos no default quando tp_cli é desconhecido
    .withColumn(
        "segmento_3050",
        F.coalesce(map_segmento(F.col("cli_tp")), F.col("mapa.segmento_default")),
    )
    .drop("mapa")
)

print("Distribuição Mod 3040 → modalidade TXB:")
df.groupBy("mod", "modalidade_3050", "segmento_3050", "recursos_3050").count().show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 2 — Derivar encargo TXB a partir do `indx`
# MAGIC Mapa `indx` (Anexo 5 do 3040) → encargo TXB (§4). Se `var_camb != "790"`
# MAGIC a operação é em moeda estrangeira → encargo `vc`.

# COMMAND ----------

encargo_case = F.when(F.col("var_camb") != "790", F.lit("vc"))

for k, v in INDX_TO_ENCARGO_LIVRE.items():
    encargo_case = encargo_case.when(
        (F.col("recursos_3050") == "livre") & (F.col("indx") == k), F.lit(v)
    )
for k, v in INDX_TO_ENCARGO_DIRECIONADO.items():
    encargo_case = encargo_case.when(
        (F.col("recursos_3050") == "direcionado") & (F.col("indx") == k), F.lit(v)
    )

encargo_case = encargo_case.otherwise(F.col("encargo_default"))
df = df.withColumn("encargo_3050", encargo_case)

print("Distribuição encargos:")
df.groupBy("encargo_3050").count().orderBy(F.desc("count")).show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 3 — Taxa média de juros (§6.1)
# MAGIC Fórmula oficial: `TxMedia = Σ(taxa_i × saldo_i) / Σ(saldo_i)`.
# MAGIC
# MAGIC **Nota de semântica:** o campo `TaxEft` do Doc 3040 é a **Taxa Efetiva
# MAGIC Anual** (já em % a.a., vide Instruções de Preenchimento do 3040). O nome
# MAGIC `taxa_juros_am` nos microdados é herdado mas o valor já chega anualizado —
# MAGIC portanto **não re-anualizamos** aqui (isso produziria taxas absurdas
# MAGIC como 7925% a.a. para `TaxEft=65%`).
# MAGIC
# MAGIC Encargos fiscais/operacionais: o 3040 não separa juros de encargos, então
# MAGIC no MVP assumimos 0% para `txMedEncFiscais` e `txMedEncOperacionais`.
# MAGIC Produção deve puxar de tabela paramétrica de encargos.

# COMMAND ----------

df = df.withColumn("taxa_juros_aa", F.col("taxa_juros_am"))   # já está em % a.a.
df = df.withColumn("tx_x_saldo", F.col("taxa_juros_aa") * F.col("saldo_ativo"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 4 — Prazos (§6.3 e §6.9)

# COMMAND ----------

df = (
    df
    .withColumn("prazo_concessao_dias", F.datediff(F.col("dt_venc_op"), F.col("dt_contr")))
    .withColumn(
        "prazo_x_vlr_concessao",
        F.when(F.col("is_concessao_mes"), F.col("prazo_concessao_dias") * F.col("vlr_op_3040"))
         .otherwise(F.lit(0.0)),
    )
    .withColumn(
        "vlr_concessao_mes",
        F.when(F.col("is_concessao_mes"), F.col("vlr_op_3040")).otherwise(F.lit(0.0)),
    )
    .withColumn("prazo_x_saldo", F.col("prazo_remanescente_dias") * F.col("saldo_ativo"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 5 — Agregação DIÁRIA (`f_3050_diario`)
# MAGIC Chave: `(recursos, segmento, encargo, modalidade)`. Produz atributos para
# MAGIC o modelo diário do XSD (até 5 variantes — ver `MODELO_ATTRS_DIARIO` em 00).

# COMMAND ----------

from datetime import date

dt_base_mes = date(int(DT_BASE[:4]), int(DT_BASE[5:7]), 1)
dt_base_semanal_calc = dt_base_semanal(last_business_day_of_month(DT_BASE))
dt_ultimo_du_mes = last_business_day_of_month(DT_BASE)

print(f"dt_base_semanal={dt_base_semanal_calc}  dt_ultimo_du_mes={dt_ultimo_du_mes}")

df = (
    df
    .withColumn("cnpj_if",          F.lit(CNPJ_IF))
    .withColumn("dt_base_semanal",  F.lit(dt_base_semanal_calc))
    .withColumn("dt_referencia",    F.lit(dt_ultimo_du_mes))
    .withColumn("leiaute_versao",   F.lit(LEIAUTE_VERSAO))
)

GROUP_COLS = ["cnpj_if", "dt_base_semanal", "dt_referencia",
              "recursos_3050", "segmento_3050", "encargo_3050", "modalidade_3050"]

# Agregado diário — nomes dos atributos seguem o XSD TXB V11 (modeloN_D_GrpAtrib).
# No MVP, `txMedEncFiscais`/`txMedEncOperacionais` = 0 (ver nota §6.1 acima).
agg_diario = (
    df.groupBy(*GROUP_COLS)
      .agg(
          (F.sum("tx_x_saldo") / F.sum("saldo_ativo")).alias("txMedJuros"),
          F.lit(0.0).alias("txMedEncFiscais"),
          F.lit(0.0).alias("txMedEncOperacionais"),
          F.sum("vlr_concessao_mes").alias("vlrConcessoes"),
          F.when(
              F.sum("vlr_concessao_mes") > 0,
              F.sum("prazo_x_vlr_concessao") / F.sum("vlr_concessao_mes"),
          ).otherwise(F.lit(0)).alias("przDecMedConcessoes"),
          F.sum("saldo_ativo").alias("sldCarAtiva"),
          F.lit(0.0).alias("sldCedido"),
          F.lit(0.0).alias("sldAdquirido"),
          F.countDistinct("ipoc").alias("qtd_contratos"),
      )
      .withColumn("leiaute_versao", F.lit(LEIAUTE_VERSAO))
)

print(f"Agregado diário: {agg_diario.count()} linhas")
agg_diario.show(20, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 6 — Agregação MENSAL (`f_3050_mensal`)
# MAGIC Adiciona saldos por faixa de atraso (§6.8) e prazo médio em curso normal
# MAGIC (§6.9). Nomes dos atributos seguem o XSD (modeloN_M_GrpAtrib).
# MAGIC
# MAGIC > MVP: todo saldo em `sldCarAte14` porque o gerador 3040 usa apenas
# MAGIC > buckets a vencer (DiaAtraso=0). Em produção, derivar de DiaAtraso + v2xx/v3xx.

# COMMAND ----------

agg_mensal = (
    df.groupBy("cnpj_if", "dt_referencia", "recursos_3050", "segmento_3050",
               "encargo_3050", "modalidade_3050")
      .agg(
          F.sum("saldo_ativo").alias("sldCarAte14"),
          F.lit(0.0).alias("sldCarAte60"),
          F.lit(0.0).alias("sldCarAte90"),
          F.lit(0.0).alias("sldCarMaior90"),
          F.lit(0.0).alias("sldBaiPrejuizo"),
          F.when(
              F.sum("saldo_ativo") > 0,
              F.sum("prazo_x_saldo") / F.sum("saldo_ativo"),
          ).otherwise(F.lit(0)).alias("przMedCarteira"),
          F.sum("saldo_ativo").alias("sld_car_total"),     # p/ sanity check
      )
      .withColumn("leiaute_versao", F.lit(LEIAUTE_VERSAO))
)

print(f"Agregado mensal: {agg_mensal.count()} linhas")
agg_mensal.show(20, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Etapa 7 — Sanity check da Regra de Ouro #1

# COMMAND ----------

total_3040 = df.agg(F.sum("vlr_op_3040").alias("s")).collect()[0]["s"] or 0.0
total_3050_diario = agg_diario.agg(F.sum("sldCarAtiva").alias("s")).collect()[0]["s"] or 0.0
total_3050_mensal = agg_mensal.agg(F.sum("sld_car_total").alias("s")).collect()[0]["s"] or 0.0

print(f"Σ vlr_op (3040)      = {total_3040:.2f}")
print(f"Σ sldCarAtiva (D)    = {total_3050_diario:.2f}  (diff={abs(total_3040 - total_3050_diario):.2f})")
print(f"Σ sld_car_total (M)  = {total_3050_mensal:.2f}  (diff={abs(total_3040 - total_3050_mensal):.2f})")

assert abs(total_3040 - total_3050_diario) < 1.0, "Saldo agregado 3050 diário diverge do 3040"
assert abs(total_3040 - total_3050_mensal) < 1.0, "Saldo agregado 3050 mensal diverge do 3040"
print("✓ Regra de Ouro #1 atendida.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persistência final p/ notebook 03

# COMMAND ----------

final_prefix = f"{CATALOG}.{SCHEMA}.f_3050_"

(agg_diario.write.mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(final_prefix + "diario"))
(agg_mensal.write.mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(final_prefix + "mensal"))

print(f"Tabelas gravadas em {final_prefix}*")
print(f"Diário: {agg_diario.count()} linhas | Mensal: {agg_mensal.count()} linhas")
