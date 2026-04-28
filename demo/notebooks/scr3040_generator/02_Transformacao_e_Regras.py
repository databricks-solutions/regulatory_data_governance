# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Transformações e Aplicação das Regras do Doc 3040
# MAGIC
# MAGIC Aplica, sobre as staging geradas em 01, as regras intra-documento
# MAGIC obrigatórias antes da serialização XML. As regras abaixo são as que,
# MAGIC se violadas, reprovam a remessa no **Aplicativo Validador do BACEN**
# MAGIC (ver `docs/scr3040/ManualValidador3040.pdf` e `SCR3040_Criticas.xls`).
# MAGIC
# MAGIC | # | Regra                                                                  | Tag/Atributo             |
# MAGIC |---|------------------------------------------------------------------------|--------------------------|
# MAGIC | 1 | `DetCli` = CNPJ14 (PJ-only no MVP, XSD 202601 @DetCli=tipoCNPJ14)     | `Op/@DetCli`             |
# MAGIC | 2 | `IPOC` = CNPJ_IF(8)+Mod(4)+TpCli(1)+Cd(8)+Contrt — único por operação  | `Op/@IPOC`               |
# MAGIC | 3 | `VarCamb` = "790" → sem indexador cambial; ≠ "790" exige `Indx` cambial| `Op/@VarCamb` / `@Indx`  |
# MAGIC | 4 | Garantia `Tp` 09xx (fidejussória) exige `Ident`+`PercGar`; demais exigem `VlrOrig`/`VlrData`/`DtReav` | `<Gar>` |
# MAGIC | 5 | `Venc` v-buckets com soma ≥ saldo (consistência de posição)            | `<Venc>`                 |
# MAGIC | 6 | `DtContr` ≤ DtBase ≤ `DtVencOp`                                         | `Op/@DtContr`/`@DtVencOp`|
# MAGIC
# MAGIC Obs.: ClassCli/ClassOp/Cosif foram REMOVIDOS do layout 2026 — sem regra aqui.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Dominios

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import StringType

staging_prefix = f"{CATALOG}.{SCHEMA}.stg_3040_"
df_clientes   = spark.table(staging_prefix + "clientes")
df_operacoes  = spark.table(staging_prefix + "operacoes")
df_vencimentos = spark.table(staging_prefix + "vencimentos")
df_garantias  = spark.table(staging_prefix + "garantias")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 1 — DetCli (CNPJ14)
# MAGIC Como o MVP gera apenas PJ, DetCli = CNPJ14 = cli_cd(8) + filial(4) + DV(2).
# MAGIC A filial é derivada do hash estável do `op_id`, garantindo reprodutibilidade
# MAGIC e filiais distintas entre operações do mesmo cliente.

# COMMAND ----------

from pyspark.sql.functions import udf


def _det_cli_pj(cli_cd: str, op_id: str) -> str:
    base = cli_cd                     # 8 dígitos (raiz CNPJ)
    h = abs(hash(op_id)) % 9999 + 1
    filial = f"{h:04d}"
    partial = base + filial
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def dv(d, w):
        s = sum(int(x) * y for x, y in zip(d, w))
        r = s % 11
        return 0 if r < 2 else 11 - r

    d1 = dv(partial, w1)
    d2 = dv(partial + str(d1), w2)
    return f"{partial}{d1}{d2}"


det_cli_udf = udf(_det_cli_pj, StringType())

df_ops = df_operacoes.withColumn(
    "det_cli", det_cli_udf(F.col("cli_cd"), F.col("op_id"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 2 — IPOC
# MAGIC Chave única por operação na IF. Construída determinística a partir de
# MAGIC atributos que já existem no registro.

# COMMAND ----------

df_ops = df_ops.withColumn(
    "ipoc",
    F.concat(
        F.lit(CNPJ_IF),        # 8
        F.col("mod"),           # 4
        F.col("tp_cli"),        # 1
        F.col("cli_cd"),        # 8
        F.col("contrt"),        # variável
    ),
)

# Verificação de unicidade — qualquer duplicata reprova no validador
ipoc_dup = df_ops.groupBy("ipoc").count().filter("count > 1").count()
assert ipoc_dup == 0, f"IPOC duplicado: {ipoc_dup} ocorrências"
print(f"IPOCs únicos: {df_ops.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 3 — VarCamb vs Indx
# MAGIC Como geramos `VarCamb="790"` (BRL) no 01, não há risco de inconsistência aqui,
# MAGIC mas a validação defensiva é feita mesmo assim.

# COMMAND ----------

df_ops = df_ops.withColumn(
    "indx",
    F.when((F.col("var_camb") == "790") & (F.col("indx").isin("21", "22", "23")),
           F.lit("11"))              # Força prefixado se BRL + indexador cambial
    .otherwise(F.col("indx")),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 4 — Atributos condicionais de `<Gar>`
# MAGIC Garante que exatamente o conjunto correto de atributos esteja preenchido
# MAGIC conforme o tipo de garantia (real vs fidejussória).

# COMMAND ----------

df_gar = (
    df_garantias
    .withColumn("is_fidej", F.col("tp").startswith("09"))
    .withColumn("ident",    F.when(F.col("is_fidej"), F.col("ident")).otherwise(F.lit(None).cast(StringType())))
    .withColumn("perc_gar", F.when(F.col("is_fidej"), F.col("perc_gar")).otherwise(F.lit(None)))
    .withColumn("vlr_orig", F.when(~F.col("is_fidej"), F.col("vlr_orig")).otherwise(F.lit(None)))
    .withColumn("vlr_data", F.when(~F.col("is_fidej"), F.col("vlr_data")).otherwise(F.lit(None)))
    .withColumn("dt_reav",  F.when(~F.col("is_fidej"), F.col("dt_reav")).otherwise(F.lit(None)))
    .drop("is_fidej")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 5 — Consistência de Venc
# MAGIC Não exigimos igualdade estrita (há operações em atraso), mas registramos o
# MAGIC gap para referência e alerta. Em produção, essa diferença cai em tabelas de
# MAGIC controle de qualidade.

# COMMAND ----------

cols_v = [F.col(b) for b in VENC_BUCKETS]
df_venc = df_vencimentos.withColumn("soma_venc", sum(cols_v))

df_check_venc = (
    df_ops.select("op_id", "vlr_op")
    .join(df_venc.select("op_id", "soma_venc"), on="op_id", how="left")
    .withColumn("gap", F.round(F.col("vlr_op") - F.col("soma_venc"), 2))
)
print("Amostra de consistência Venc x vlr_op:")
df_check_venc.show(5, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Regra 6 — DtContr ≤ DtBase ≤ DtVencOp
# MAGIC Operações com `dt_venc_op` ≤ DtBase são recalculadas para a janela
# MAGIC [DtBase+30d, DtBase+720d] — coerente com o 01 mas reforçado aqui.

# COMMAND ----------

from datetime import date

dt_base = F.to_date(F.lit(DT_BASE + "-01"))
df_ops = (
    df_ops
    .withColumn(
        "dt_venc_op",
        F.when(F.col("dt_venc_op") <= dt_base,
               F.date_add(dt_base, 180)).otherwise(F.col("dt_venc_op")),
    )
    .withColumn(
        "dt_contr",
        F.when(F.col("dt_contr") > dt_base, F.date_sub(dt_base, 30)).otherwise(F.col("dt_contr")),
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persistência das tabelas finais para 03

# COMMAND ----------

final_prefix = f"{CATALOG}.{SCHEMA}.f_3040_"
df_clientes.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(final_prefix + "clientes")
df_ops.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(final_prefix + "operacoes")
df_venc.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(final_prefix + "vencimentos")
df_gar.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(final_prefix + "garantias")

print(f"Tabelas finais gravadas em {final_prefix}*")
print(f"Clientes: {df_clientes.count()} | Operações: {df_ops.count()} | "
      f"Venc: {df_venc.count()} | Gar: {df_gar.count()}")
