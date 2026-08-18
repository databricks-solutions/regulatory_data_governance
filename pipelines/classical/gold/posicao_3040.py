# Databricks notebook source
# MAGIC %md
# MAGIC # Gold CLÁSSICO — Posição SCR 3040 → `gold.posicao_3040`
# MAGIC
# MAGIC Uma linha por `<Op>` em `(cnpj_if, dt_base)`:
# MAGIC `scr3040_operacoes` ⨝ `scr3040_cont_4966` ⨝ `scr3040_vencimentos`.
# MAGIC Pure ELT — quality é externa (DQX Studio).
# MAGIC
# MAGIC Equivalente ao DLT `pipelines/gold/transformations/posicao_3040.py`.

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")

CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")

# COMMAND ----------

ops = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3040_operacoes")
cont = (
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3040_cont_4966")
    .select(
        "cnpj_if", "dt_base", "ipoc",
        "clas_at_fin", "est_inst_fin", "cart_prov_min",
        "vlr_cont_br", "tje", "rend_mes",
        "estagio_motivo", "estagio_dt_alocacao",
    )
)
venc = (
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr3040_vencimentos")
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

fqn = f"{CATALOG}.{GOLD_SCHEMA}.posicao_3040"
(
    posicao_3040.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn)
)
spark.sql(
    f"ALTER TABLE {fqn} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'delta.deletedFileRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")
