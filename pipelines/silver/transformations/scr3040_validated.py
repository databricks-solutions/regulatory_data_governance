# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — SCR 3040 Validated Operations
# MAGIC Reads bronze SCR 3040 tables, applies DLT expectations mapped to R.18 quality
# MAGIC dimensions, enriches with modality equivalence mapping, and writes validated records
# MAGIC to silver. Invalid records are routed to quarantine.

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

# IPOC format: CNPJ_IF(8) + Mod(4) + TpCli(1) + CodCli(variable) + Contrato(variable)
IPOC_REGEX = r"^\d{8}\d{4}[1-6].+"


# ── Validated Operations ──────────────────────────────────────────────────────

@dlt.table(
    name="operacoes_validadas",
    comment="Operações de crédito SCR 3040 validadas com IPOC integrity, regras semânticas e mapeamento 3040→3050",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("valid_cnpj_if_length", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("valid_ipoc_format", f"ipoc RLIKE '{IPOC_REGEX}'")
@dlt.expect_or_drop("campos_obrigatorios_s10", "contrt IS NOT NULL AND natu_op IS NOT NULL AND mod IS NOT NULL")
@dlt.expect_or_drop("date_vencimento_after_contrato", "dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr")
@dlt.expect_or_drop("modalidade_valid_domain", "mod IS NOT NULL AND LENGTH(mod) = 4")
@dlt.expect("ipoc_components_consistent", "ipoc_is_consistent = true")
@dlt.expect("cosif_code_valid", "cosif IS NULL OR LENGTH(cosif) = 7")
@dlt.expect("classificacao_risco_valida", "class_op IS NULL OR class_op IN ('AA','A','B','C','D','E','F','G','H')")
def operacoes_validadas():
    # Read bronze operations
    ops = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.operacoes_raw")

    # Read modality equivalence mapping from reference
    equiv = spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.modalidades_equivalencia")

    # Decompose IPOC into components and validate consistency
    enriched = (
        ops
        .withColumn("ipoc_cnpj_if_part", F.substring(F.col("ipoc"), 1, 8))
        .withColumn("ipoc_mod_part", F.substring(F.col("ipoc"), 9, 4))
        .withColumn("ipoc_tp_cli_part", F.substring(F.col("ipoc"), 13, 1))
        .withColumn("ipoc_cod_cli_part", F.substring(F.col("ipoc"), 14, 14))
        .withColumn("ipoc_contrt_part", F.substring(F.col("ipoc"), 28, 40))
        .withColumn("ipoc_is_valid_format", F.col("ipoc").rlike(IPOC_REGEX))
        .withColumn(
            "ipoc_is_consistent",
            (F.col("ipoc_cnpj_if_part") == F.col("cnpj_if"))
            & (F.col("ipoc_mod_part") == F.col("mod"))
            & (F.col("ipoc_tp_cli_part") == F.col("cli_tp")),
        )
        # Cessao / saida flags
        .withColumn("is_cessao_cedente", F.col("natu_op").isin("11"))
        .withColumn("is_cessao_cessionaria", F.col("natu_op").isin("04"))
        .withColumn("is_saida", F.col("natu_op").isin("0301", "0302", "0303", "0304"))
        .withColumn("is_agregado", F.lit(False))
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_flags", F.lit(None).cast("string"))
        .withColumn("validation_run_id", F.lit(dlt.get_pipeline_id()) if hasattr(dlt, 'get_pipeline_id') else F.lit("unknown"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )

    # Join with equivalence mapping for mod_3050_equiv
    return (
        enriched
        .join(
            equiv.select(
                F.col("mod_3040").alias("_eq_mod"),
                F.col("modalidade_3050").alias("mod_3050_equiv"),
                F.col("segmento_3050"),
            ),
            enriched.mod == F.col("_eq_mod"),
            "left",
        )
        .drop("_eq_mod")
    )


# ── Validated Clients ─────────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_clientes",
    comment="Clientes SCR 3040 validados e deduplicated com SCD Type 2",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("cli_cd_not_null", "cli_cd IS NOT NULL")
@dlt.expect_or_drop("cli_tp_valid", "cli_tp IN ('1','2','3','4','5','6')")
@dlt.expect("cli_class_valid", "cli_class IS NULL OR cli_class IN ('AA','A','B','C','D','E','F','G','H')")
def scr3040_clientes():
    return (
        dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.clientes_raw")
        .withColumn("is_pf", F.col("cli_tp") == "1")
        .withColumn("is_pj", F.col("cli_tp").isin("2", "5"))
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_run_id", F.lit("pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Validated Guarantees ──────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_garantias",
    comment="Garantias SCR 3040 validadas (fidejussórias e reais)",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("gar_tp_not_null", "gar_tp IS NOT NULL")
@dlt.expect("garantidor_diferente_cliente", "ident IS NULL OR ident != cli_cd")
def scr3040_garantias():
    ops = dlt.read("operacoes_validadas").select("cnpj_if", "dt_base", "cli_cd", "contrt", "ipoc")
    gar = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.garantias_raw")
    return (
        gar
        .join(ops, ["cnpj_if", "dt_base", "cli_cd", "contrt"], "left")
        .withColumn("gar_categoria", F.when(F.col("ident").isNotNull(), "fidejussoria").otherwise("real"))
        .withColumn("is_fidejussoria", F.col("ident").isNotNull())
        .withColumn(
            "is_garantidor_diferente_cliente",
            F.when(F.col("ident").isNotNull(), F.col("ident") != F.col("cli_cd")).otherwise(None),
        )
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_run_id", F.lit("pipeline"))
    )


# ── Validated Additional Info ─────────────────────────────────────────────────

@dlt.table(
    name="scr3040_inf_adicionais",
    comment="Informações adicionais SCR 3040 normalizadas — cessões, saídas, IFRS 9",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("inf_tp_not_null", "inf_tp IS NOT NULL")
def scr3040_inf_adicionais():
    ops = dlt.read("operacoes_validadas").select("cnpj_if", "dt_base", "cli_cd", "contrt", "ipoc")
    inf = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.inf_adicionais_raw")
    return (
        inf
        .join(ops, ["cnpj_if", "dt_base", "cli_cd", "contrt"], "left")
        .withColumn(
            "inf_categoria",
            F.when(F.col("inf_tp").startswith("01"), "cessao_cessionaria")
            .when(F.col("inf_tp").startswith("02"), "cessao_cedente")
            .when(F.col("inf_tp").isin("0303", "0304", "0316"), "saida")
            .when(F.col("inf_tp").startswith("12"), "coobrigacao")
            .otherwise("outro"),
        )
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_run_id", F.lit("pipeline"))
    )


# ── Validated Maturity Vertices ───────────────────────────────────────────────

@dlt.table(
    name="scr3040_vencimentos",
    comment="Vértices de vencimento SCR 3040 validados — 31 vértices × 5 categorias",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect("vertex_total_positive", "total_saldo >= 0 OR total_saldo IS NULL")
def scr3040_vencimentos():
    ops = dlt.read("operacoes_validadas").select("cnpj_if", "dt_base", "cli_cd", "contrt", "ipoc")
    venc = dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.vencimentos_raw")

    a_vencer_cols = ["v110", "v120", "v130", "v140", "v150", "v160", "v170", "v180", "v190", "v199"]
    vencido_cols = ["v205", "v210", "v220", "v230", "v240", "v250", "v260", "v270", "v280", "v290"]
    prejuizo_cols = ["v310", "v320", "v330"]

    def coalesce_sum(cols):
        return sum(F.coalesce(F.col(c), F.lit(0)) for c in cols)

    return (
        venc
        .join(ops, ["cnpj_if", "dt_base", "cli_cd", "contrt"], "left")
        .withColumn("total_a_vencer", coalesce_sum(a_vencer_cols))
        .withColumn("total_vencido", coalesce_sum(vencido_cols))
        .withColumn("total_prejuizo", coalesce_sum(prejuizo_cols))
        .withColumn("total_limites", F.coalesce(F.col("v20"), F.lit(0)) + F.coalesce(F.col("v40"), F.lit(0)))
        .withColumn("total_a_liberar", F.coalesce(F.col("v60"), F.lit(0)) + F.coalesce(F.col("v80"), F.lit(0)))
        .withColumn("total_saldo", F.col("total_a_vencer") + F.col("total_vencido") + F.col("total_prejuizo") + F.col("total_limites") + F.col("total_a_liberar"))
        .withColumn("is_valid", F.lit(True))
        .withColumn("validation_run_id", F.lit("pipeline"))
    )


# ── Quarantine ────────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_quarantine",
    comment="Operações SCR 3040 rejeitadas pelas regras de validação bloqueantes (expect_or_drop)",
    table_properties={"quality": "quarantine"},
    partition_cols=["dt_base"],
)
def scr3040_quarantine():
    return (
        dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.operacoes_raw")
        .filter(
            (F.length(F.col("cnpj_if")) != 8)
            | (~F.col("ipoc").rlike(IPOC_REGEX))
            | F.col("contrt").isNull()
            | F.col("natu_op").isNull()
            | F.col("mod").isNull()
        )
        .select(
            "cnpj_if", "dt_base", "cli_cd", "contrt", "ipoc",
            F.to_json(F.struct("*")).alias("raw_record"),
            F.array(F.lit("multiple_blocking_rules")).alias("failed_expectations"),
            F.lit("Record failed one or more blocking validation rules").alias("failure_reason"),
            F.lit(None).cast("array<string>").alias("critica_ids"),
            F.lit(None).cast("array<string>").alias("dimension_r18"),
            F.lit("pipeline").alias("validation_run_id"),
            F.current_timestamp().alias("quarantine_timestamp"),
        )
    )
