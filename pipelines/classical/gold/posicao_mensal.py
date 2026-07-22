# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição SCR 3040 e 3050 (sem DLT/SDP)
# MAGIC
# MAGIC Versão **clássica** (job + notebook PySpark) do gold. Produz as MESMAS
# MAGIC tabelas que o pipeline DLT (`pipelines/gold/transformations/posicao_mensal.py`):
# MAGIC
# MAGIC | Table | Source | One row per |
# MAGIC |---|---|---|
# MAGIC | `posicao_3040` | silver `scr3040_operacoes` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos` | `<Op>` por `(cnpj_if, dt_base)` |
# MAGIC | `posicao_3050` | silver `scr3050` (passthrough + `_gold_timestamp`) | dimensão 3050 |
# MAGIC | `processing_state` | posicao_3040/3050 (MAX dt_base) | 1 linha (seletor Data-Base do app) |
# MAGIC
# MAGIC Muda só o I/O: `@dlt.table`→`saveAsTable(overwrite)` e a dependência
# MAGIC same-pipeline (`dlt.read`) de `processing_state` vira leitura sequencial
# MAGIC via `spark.table` (as posições já foram materializadas acima neste run).

# COMMAND ----------

import uuid

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")
dbutils.widgets.text("reference_schema", "reference")

SOURCE_CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")
REFERENCE_SCHEMA = dbutils.widgets.get("reference_schema")

# UUID lógico do run — carimbado em reconciliacao_cosif.pipeline_run_id (auditoria).
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"


def _gold_fqn(table_name):
    return f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.{table_name}"


# COMMAND ----------
# MAGIC %md
# MAGIC ## Posição SCR 3040
# MAGIC Pure ELT passthrough — silver é puro normalizado (sem DQX inline). Quality
# MAGIC é gerenciada externamente pelo DQX Studio; gold apenas promove os
# MAGIC registros silver para as posições que App/dashboards consomem.

# COMMAND ----------

ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
cont = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_cont_4966")
    .select(
        "cnpj_if", "dt_base", "ipoc",
        "clas_at_fin", "est_inst_fin", "cart_prov_min",
        "vlr_cont_br", "tje", "rend_mes",
        "estagio_motivo", "estagio_dt_alocacao",
    )
)
venc = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
    .select(
        "cnpj_if", "dt_base", "ipoc",
        F.col("total_saldo").alias("total_saldo_vencimentos"),
        "total_a_vencer", "total_vencido", "total_prejuizo",
        "total_limites", "total_coobrigacoes",
    )
)

posicao_3040 = (
    ops
    .join(cont, ["cnpj_if", "dt_base", "ipoc"], "left")
    .join(venc, ["cnpj_if", "dt_base", "ipoc"], "left")
    .select(
        "cnpj_if", "dt_base", "remessa", "parte",
        "cli_tp", "cli_cd", "ipoc", "contrt", "det_cli",
        "natu_op", "mod", "mod_3050_equiv", "segmento_3050_equiv",
        "origem_rec", "indx", "perc_indx", "var_camb",
        "dt_contr", "dt_venc_op", "tax_eft", "prov_consttd",
        "carac_especial", "dia_atraso",
        # Res. 4966 contábil
        "clas_at_fin", "est_inst_fin", "cart_prov_min",
        "vlr_cont_br", "tje", "rend_mes",
        "estagio_motivo", "estagio_dt_alocacao",
        # Vértices
        "total_saldo_vencimentos", "total_a_vencer", "total_vencido",
        "total_prejuizo", "total_limites", "total_coobrigacoes",
        "pipeline_run_id",
        F.current_timestamp().alias("_gold_timestamp"),
    )
)

fqn_3040 = _gold_fqn("posicao_3040")
(
    posicao_3040.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_3040)
)
spark.sql(
    f"ALTER TABLE {fqn_3040} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn_3040}: {spark.table(fqn_3040).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Posição SCR 3050 (passthrough do silver unificado)

# COMMAND ----------

fqn_3050 = _gold_fqn("posicao_3050")
(
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_referencia")
    .saveAsTable(fqn_3050)
)
spark.sql(
    f"ALTER TABLE {fqn_3050} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn_3050}: {spark.table(fqn_3050).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Posição CADOC 4010 (Balancete COSIF — passthrough curado)

# COMMAND ----------

fqn_4010 = _gold_fqn("posicao_4010")
(
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
    .withColumn("_gold_timestamp", F.current_timestamp())
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn_4010)
)
spark.sql(
    f"ALTER TABLE {fqn_4010} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn_4010}: {spark.table(fqn_4010).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Batimento inter-CADOC: SCR 3040 × COSIF 4010 (`reconciliacao_cosif`)
# MAGIC Dimensão VIII (Consistência). Para cada regra em `reference.cosif_contas`,
# MAGIC soma o saldo do 3040 (perna SCR, via `predicado_3040`) e compara ao saldo
# MAGIC COSIF do 4010 (perna contábil). Status: APROVADO / ALERTA / BLOQUEADO
# MAGIC conforme a tolerância. Schema conforme docs/spec/03_data_model.md §4.3.
# MAGIC
# MAGIC ⚠️ Mapeamento rubrica↔filtro REPRESENTATIVO (subconjunto T/M) — simulação,
# MAGIC não o batimento COSIF completo do BACEN.

# COMMAND ----------

TOLERANCIA_PCT = 0.10  # % — divergências acima disso bloqueiam a remessa (N01)

# Perna SCR: saldo do 3040 por rubrica (operacoes ⨝ vencimentos), agregado
# conforme o predicado de cada conta COSIF (reference.cosif_contas).
_ops = spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
_venc = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
    .select("cnpj_if", "dt_base", "ipoc", "total_saldo", "total_limites")
)
_ops_venc = _ops.select("cnpj_if", "dt_base", "mod", "ipoc").join(
    _venc, on=["cnpj_if", "dt_base", "ipoc"], how="left"
)

_regras = [
    r.asDict()
    for r in spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.cosif_contas")
    .filter(F.col("is_ativo")).collect()
]

_scr_rows = []
for reg in _regras:
    saldo_col = reg["coluna_saldo_3040"]              # total_saldo | total_limites
    pred = reg.get("predicado_3040") or "true"
    agg = (
        _ops_venc.filter(F.expr(pred))
        .groupBy("cnpj_if", F.date_format("dt_base", "yyyy-MM").alias("dt_base"))
        .agg(F.round(F.coalesce(F.sum(saldo_col), F.lit(0.0)), 2).alias("vlr_scr"))
        .withColumn("grupo_reconciliacao", F.lit(reg["grupo_reconciliacao"]))
        .withColumn("tipo_regra", F.lit(reg["tipo_regra"]))
        .withColumn("descricao_regra", F.lit(reg["descricao"]))
        .withColumn("modalidade_3040", F.lit(reg.get("modalidade_3040")))
        .withColumn("cosif_conta", F.lit(reg["cosif_conta"]))
    )
    _scr_rows.append(agg)

scr_por_regra = _scr_rows[0]
for extra in _scr_rows[1:]:
    scr_por_regra = scr_por_regra.unionByName(extra)

# Perna COSIF: saldo (absoluto) por conta do 4010. Junta por codigo_conta
# (10 dígitos, formato oficial) = reference.cosif_contas.cosif_conta.
cosif = (
    spark.table(f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr4010_saldos")
    .select(
        "cnpj_if",
        F.col("dt_base_mes").alias("dt_base"),
        F.col("codigo_conta").alias("cosif_conta"),
        F.abs(F.col("saldo")).cast("decimal(17,2)").alias("vlr_cosif"),
    )
)

recon = (
    scr_por_regra.alias("s")
    .join(cosif.alias("c"), on=["cnpj_if", "dt_base", "cosif_conta"], how="left")
    .withColumn("vlr_cosif", F.coalesce(F.col("vlr_cosif"), F.lit(0.0)).cast("decimal(17,2)"))
    .withColumn("vlr_scr", F.col("vlr_scr").cast("decimal(17,2)"))
    .withColumn("vlr_diferenca", (F.col("vlr_scr") - F.col("vlr_cosif")).cast("decimal(17,2)"))
    .withColumn(
        "pct_diferenca",
        F.when(F.col("vlr_cosif") == 0, F.lit(None))
         .otherwise(F.round(F.abs(F.col("vlr_diferenca")) / F.abs(F.col("vlr_cosif")) * 100, 4))
         .cast("decimal(8,4)"),
    )
    .withColumn("tolerancia_pct", F.lit(TOLERANCIA_PCT).cast("decimal(8,4)"))
    .withColumn(
        "status",
        F.when(F.col("pct_diferenca").isNull() | (F.col("pct_diferenca") == 0), F.lit("APROVADO"))
         .when(F.col("pct_diferenca") <= F.col("tolerancia_pct"), F.lit("ALERTA"))
         .otherwise(F.lit("BLOQUEADO")),
    )
    .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
    .withColumn("rec_timestamp", F.current_timestamp())
    .select(
        "cnpj_if", "dt_base", "tipo_regra",
        F.col("grupo_reconciliacao").alias("codigo_regra"),
        "descricao_regra", "modalidade_3040", "cosif_conta",
        "vlr_scr", "vlr_cosif", "vlr_diferenca", "pct_diferenca",
        "tolerancia_pct", "status", "pipeline_run_id", "rec_timestamp",
    )
)

fqn_recon = _gold_fqn("reconciliacao_cosif")
(recon.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .partitionBy("dt_base").saveAsTable(fqn_recon))
spark.sql(f"ALTER TABLE {fqn_recon} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn_recon}: {spark.table(fqn_recon).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Estado de processamento (data-base corrente)
# MAGIC O app usa este valor para preencher o seletor de Data-Base com o ÚLTIMO
# MAGIC CADOC processado (MAX dt_base observado nas posições 3040/3050/4010). Uma
# MAGIC única linha, recalculada a cada run. No modo clássico lemos as posições já
# MAGIC materializadas acima via `spark.table` (equivalente ao `dlt.read`
# MAGIC same-pipeline do modo DLT).

# COMMAND ----------

p3040 = spark.table(fqn_3040).select("dt_base")
p3050 = spark.table(fqn_3050).select("dt_base")
p4010 = spark.table(fqn_4010).select("dt_base")

processing_state = (
    p3040.unionByName(p3050).unionByName(p4010)
    .agg(F.max("dt_base").alias("current_data_base"))
    .withColumn("data_base_month", F.date_format(F.col("current_data_base"), "yyyy-MM"))
    .withColumn("updated_at", F.current_timestamp())
)

fqn_state = _gold_fqn("processing_state")
(
    processing_state.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(fqn_state)
)
spark.sql(f"ALTER TABLE {fqn_state} SET TBLPROPERTIES ('quality' = 'gold')")
print(f"OK — {fqn_state}: {spark.table(fqn_state).count()} linha(s)")
