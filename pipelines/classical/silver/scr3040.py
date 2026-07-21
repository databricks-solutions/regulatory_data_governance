# Databricks notebook source
# MAGIC %md
# MAGIC # Silver CLÁSSICO — SCR 3040 (XML-derived, sem DLT/SDP)
# MAGIC
# MAGIC Versão **clássica** (job + notebook PySpark) do silver 3040. Lê
# MAGIC `bronze.raw_3040_doc` e produz as MESMAS 5 tabelas normalizadas que o
# MAGIC pipeline DLT (`pipelines/silver/transformations/scr3040.py`):
# MAGIC `scr3040_operacoes`, `scr3040_clientes`, `scr3040_garantias`,
# MAGIC `scr3040_vencimentos`, `scr3040_cont_4966`.
# MAGIC
# MAGIC Pure ELT — quality roda externamente na DQX Studio. As transformações são
# MAGIC idênticas ao pipeline DLT; muda só o I/O:
# MAGIC * `dlt.read(...)` → `spark.table(...)`
# MAGIC * `@dlt.table` → `.write.mode("overwrite").saveAsTable(...)`
# MAGIC
# MAGIC O overwrite mantém o notebook idempotente (reprocessa o snapshot completo
# MAGIC do bronze a cada run), coerente com o comportamento das tabelas
# MAGIC materializadas DLT.

# COMMAND ----------

import uuid

from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("bronze_schema", "bronze")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("reference_schema", "reference")

SOURCE_CATALOG = dbutils.widgets.get("catalog")
BRONZE_SCHEMA = dbutils.widgets.get("bronze_schema")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
REFERENCE_SCHEMA = dbutils.widgets.get("reference_schema")

# UUID logical-run identifier carimbado em cada linha (debug + auditoria).
# Uma execução do notebook = um único valor compartilhado pelas 5 tabelas.
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"


def _write(df, table_name, partition_col="dt_base"):
    """Materializa uma tabela silver clássica (overwrite idempotente)."""
    fqn = f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.{table_name}"
    (
        df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy(partition_col)
        .saveAsTable(fqn)
    )
    print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")


# COMMAND ----------
# MAGIC %md
# MAGIC ## Helpers de explode (idênticos ao pipeline DLT, `dlt.read`→`spark.table`)

# COMMAND ----------

def _bronze():
    return spark.table(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3040_doc")


def _explode(array_col: str):
    """Explode a bronze array column into rows, propagating header attrs."""
    return (
        _bronze()
        .select(
            F.col("file_name"),
            F.col("file_path"),
            F.col("header.dt_base").alias("dt_base"),
            F.col("header.cnpj_if").alias("cnpj_if"),
            F.col("header.remessa").alias("remessa"),
            F.col("header.parte").alias("parte"),
            F.explode(F.col(array_col)).alias("rec"),
        )
    )


# COMMAND ----------
# MAGIC %md
# MAGIC ## Operações
# MAGIC IPOC layout (30 chars): CNPJ_IF(8) + Mod(4) + TpCli(1) + CodCli(8) + Contrt(9)

# COMMAND ----------

def _build_operacoes_df():
    """DataFrame enriquecido de operações 3040 (decomposição IPOC, flags de
    natureza, lista de `carac_especial`, join com `modalidades_equivalencia`)."""
    ops = _explode("operacoes")

    enriched = (
        ops
        .select(
            "file_name", "file_path", "dt_base", "cnpj_if", "remessa", "parte",
            F.col("rec.cli_tp").alias("cli_tp"),
            F.col("rec.cli_cd").alias("cli_cd"),
            F.col("rec.det_cli").alias("det_cli"),
            F.col("rec.contrt").alias("contrt"),
            F.col("rec.natu_op").alias("natu_op"),
            F.col("rec.mod").alias("mod"),
            F.col("rec.origem_rec").alias("origem_rec"),
            F.col("rec.indx").alias("indx"),
            F.col("rec.perc_indx").alias("perc_indx"),
            F.col("rec.var_camb").alias("var_camb"),
            F.to_date(F.col("rec.dt_venc_op")).alias("dt_venc_op"),
            F.col("rec.cep").alias("cep"),
            F.col("rec.tax_eft").alias("tax_eft"),
            F.to_date(F.col("rec.dt_contr")).alias("dt_contr"),
            F.col("rec.prov_consttd").alias("prov_consttd"),
            F.col("rec.carac_especial").alias("carac_especial"),
            F.col("rec.dia_atraso").alias("dia_atraso"),
            F.col("rec.ipoc").alias("ipoc"),
        )
        # IPOC decomposition
        .withColumn("ipoc_cnpj_if_part", F.substring("ipoc", 1, 8))
        .withColumn("ipoc_mod_part", F.substring("ipoc", 9, 4))
        .withColumn("ipoc_tp_cli_part", F.substring("ipoc", 13, 1))
        .withColumn("ipoc_cod_cli_part", F.substring("ipoc", 14, 8))
        .withColumn("ipoc_contrt_part", F.substring("ipoc", 22, 9))
        .withColumn(
            "ipoc_is_consistent",
            (F.col("ipoc_cnpj_if_part") == F.col("cnpj_if"))
            & (F.col("ipoc_mod_part") == F.col("mod"))
            & (F.col("ipoc_tp_cli_part") == F.col("cli_tp"))
            & (F.col("ipoc_cod_cli_part") == F.col("cli_cd"))
            & (F.col("ipoc_contrt_part") == F.col("contrt")),
        )
        # Natureza-derived flags
        .withColumn("is_cessao_cessionaria", F.col("natu_op") == "04")
        .withColumn("is_cessao_cedente", F.col("natu_op") == "11")
        .withColumn(
            "is_saida",
            F.col("natu_op").isin("0301", "0302", "0303", "0304"),
        )
        # CaracEspecial is a semicolon-separated list
        .withColumn(
            "carac_especial_list",
            F.when(F.col("carac_especial").isNotNull(), F.split(F.col("carac_especial"), ";"))
            .otherwise(F.array().cast("array<string>")),
        )
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )

    # 3040 → 3050 modality equivalence
    equiv = (
        spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.modalidades_equivalencia")
        .select(
            F.col("mod_3040").alias("_eq_mod"),
            F.col("modalidade_3050").alias("mod_3050_equiv"),
            F.col("segmento_3050").alias("segmento_3050_equiv"),
        )
    )

    return (
        enriched
        .join(equiv, enriched.mod == equiv._eq_mod, "left")
        .drop("_eq_mod")
    )


_write(_build_operacoes_df(), "scr3040_operacoes")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Clientes

# COMMAND ----------

def _build_clientes_df():
    return (
        _explode("clientes")
        .select(
            "file_name", "dt_base", "cnpj_if", "remessa", "parte",
            F.col("rec.cli_tp").alias("cli_tp"),
            F.col("rec.cli_cd").alias("cli_cd"),
            F.col("rec.autorzc").alias("autorzc"),
            F.col("rec.porte_cli").alias("porte_cli"),
            F.col("rec.tp_ctrl").alias("tp_ctrl"),
            F.to_date(F.col("rec.ini_relact_cli")).alias("ini_relact_cli"),
            F.col("rec.fat_anual").alias("fat_anual"),
        )
        .withColumn("is_pf", F.col("cli_tp") == "1")
        .withColumn("is_pj", F.col("cli_tp").isin("2", "5"))
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


_write(_build_clientes_df(), "scr3040_clientes")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Garantias

# COMMAND ----------

def _build_garantias_df():
    return (
        _explode("garantias")
        .select(
            "file_name", "dt_base", "cnpj_if", "remessa", "parte",
            F.col("rec.cli_tp").alias("cli_tp"),
            F.col("rec.cli_cd").alias("cli_cd"),
            F.col("rec.contrt").alias("contrt"),
            F.col("rec.ipoc").alias("ipoc"),
            F.col("rec.gar_tp").alias("gar_tp"),
            F.col("rec.ident").alias("ident"),
            F.col("rec.perc_gar").alias("perc_gar"),
            F.col("rec.vlr_orig").alias("vlr_orig"),
            F.col("rec.vlr_data").alias("vlr_data"),
            F.to_date(F.col("rec.dt_reav")).alias("dt_reav"),
            F.col("rec.gar_categoria").alias("gar_categoria"),
        )
        .withColumn("is_fidejussoria", F.col("gar_categoria") == "fidejussoria")
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


_write(_build_garantias_df(), "scr3040_garantias")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Vencimentos (vértices)

# COMMAND ----------

def _build_vencimentos_df():
    a_vencer_cols = ["v110", "v120", "v130", "v140", "v150", "v160", "v165", "v170", "v175", "v180", "v190", "v199"]
    vencido_cols = ["v205", "v210", "v220", "v230", "v240", "v250", "v260", "v270", "v280", "v290"]
    prejuizo_cols = ["v310", "v320", "v330"]
    limite_cols = ["v20", "v40"]
    coobr_cols = ["v60", "v80"]

    df = (
        _explode("vencimentos")
        .select(
            "file_name", "dt_base", "cnpj_if", "remessa", "parte",
            F.col("rec.cli_tp").alias("cli_tp"),
            F.col("rec.cli_cd").alias("cli_cd"),
            F.col("rec.contrt").alias("contrt"),
            F.col("rec.ipoc").alias("ipoc"),
            *[F.col(f"rec.{c}").alias(c)
              for c in a_vencer_cols + vencido_cols + prejuizo_cols + limite_cols + coobr_cols],
        )
    )

    def _coalesce_sum(cols):
        return sum(F.coalesce(F.col(c), F.lit(0)) for c in cols)

    return (
        df
        .withColumn("total_a_vencer", _coalesce_sum(a_vencer_cols))
        .withColumn("total_vencido", _coalesce_sum(vencido_cols))
        .withColumn("total_prejuizo", _coalesce_sum(prejuizo_cols))
        .withColumn("total_limites", _coalesce_sum(limite_cols))
        .withColumn("total_coobrigacoes", _coalesce_sum(coobr_cols))
        .withColumn(
            "total_saldo",
            F.col("total_a_vencer") + F.col("total_vencido") + F.col("total_prejuizo"),
        )
        .withColumn(
            "vertice_count",
            sum(
                F.when(F.col(c).isNotNull() & (F.col(c) > 0), 1).otherwise(0)
                for c in a_vencer_cols + vencido_cols + prejuizo_cols
            ),
        )
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


_write(_build_vencimentos_df(), "scr3040_vencimentos")

# COMMAND ----------
# MAGIC %md
# MAGIC ## ContInstFinRes 4966 + Estágio

# COMMAND ----------

def _build_cont_4966_df():
    return (
        _explode("cont4966")
        .select(
            "file_name", "dt_base", "cnpj_if", "remessa", "parte",
            F.col("rec.cli_tp").alias("cli_tp"),
            F.col("rec.cli_cd").alias("cli_cd"),
            F.col("rec.contrt").alias("contrt"),
            F.col("rec.ipoc").alias("ipoc"),
            F.col("rec.clas_at_fin").alias("clas_at_fin"),
            F.col("rec.est_inst_fin").alias("est_inst_fin"),
            F.col("rec.cart_prov_min").alias("cart_prov_min"),
            F.col("rec.vlr_cont_br").alias("vlr_cont_br"),
            F.col("rec.tje").alias("tje"),
            F.col("rec.rend_mes").alias("rend_mes"),
            F.col("rec.estagio_motivo").alias("estagio_motivo"),
            F.col("rec.estagio_dt_alocacao").alias("estagio_dt_alocacao"),
        )
        .withColumn("pipeline_run_id", F.lit(_PIPELINE_RUN_ID))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


_write(_build_cont_4966_df(), "scr3040_cont_4966")
