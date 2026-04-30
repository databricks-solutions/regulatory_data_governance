# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — SCR 3040 Validated (XML-derived)
# MAGIC
# MAGIC Reads `bronze.raw_3040_doc` (one row per XML file with parsed nested structs)
# MAGIC and explodes it into normalized tables that mirror the BACEN wire format:
# MAGIC
# MAGIC | Silver table | Source array | One row per |
# MAGIC |---|---|---|
# MAGIC | `operacoes_validadas` | `operacoes` | `<Op>` (joined with parent `<Cli>` and `<Doc3040>` header) |
# MAGIC | `scr3040_clientes` | `clientes` | `<Cli>` |
# MAGIC | `scr3040_garantias` | `garantias` | `<Gar>` |
# MAGIC | `scr3040_vencimentos` | `vencimentos` | `<Venc>` (one per Op, vertices as columns) |
# MAGIC | `scr3040_cont_4966` | `cont4966` | `<ContInstFinRes4966>` + `<Estagio>` |
# MAGIC | `scr3040_quarantine` | (rejected) | failed blocking expectations |
# MAGIC
# MAGIC Operations enrich with `mod_3050_equiv` from `reference.modalidades_equivalencia`
# MAGIC (`mod_3050_equiv`) for downstream consumers. Expectations are mapped to R.18
# MAGIC quality dimensions and recorded in DLT event log.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
BRONZE_SCHEMA = spark.conf.get("source_schema", "bronze")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")

# IPOC layout (30 chars): CNPJ_IF(8) + Mod(4) + TpCli(1) + CodCli(8) + Contrt(9)
IPOC_REGEX = r"^\d{8}\d{4}[1-6]\d{8}\d{9}$"


def _bronze():
    return dlt.read(f"{SOURCE_CATALOG}.{BRONZE_SCHEMA}.raw_3040_doc")


def _explode(array_col: str, extra_cols: list[str] | None = None):
    """Explode a bronze array column into rows, propagating header attrs."""
    base = (
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
    return base


# ── Operações validadas ───────────────────────────────────────────────────────

@dlt.table(
    name="operacoes_validadas",
    comment="Operações SCR 3040 — uma linha por <Op>, com cabeçalho propagado, validação IPOC e mapeamento 3040→3050",
    table_properties={
        "quality": "silver",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("valid_cnpj_if_length", "LENGTH(cnpj_if) = 8")
@dlt.expect_or_drop("valid_ipoc_format", f"ipoc RLIKE '{IPOC_REGEX}'")
@dlt.expect_or_drop("campos_obrigatorios_s10", "contrt IS NOT NULL AND natu_op IS NOT NULL AND mod IS NOT NULL")
@dlt.expect_or_drop("modalidade_valid_domain", "LENGTH(mod) = 4")
@dlt.expect("date_vencimento_after_contrato", "dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr")
@dlt.expect("ipoc_components_consistent", "ipoc_is_consistent = true")
@dlt.expect("dia_atraso_nao_negativo", "dia_atraso IS NULL OR dia_atraso >= 0")
@dlt.expect("perc_indx_in_range", "perc_indx IS NULL OR (perc_indx >= 0 AND perc_indx <= 9999.99)")
def operacoes_validadas():
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
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
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


# ── Clientes ──────────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_clientes",
    comment="Clientes SCR 3040 — uma linha por <Cli>, validados",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("cli_cd_not_null", "cli_cd IS NOT NULL")
@dlt.expect_or_drop("cli_tp_valid", "cli_tp IN ('1','2','3','4','5','6')")
@dlt.expect("porte_cli_valid", "porte_cli IS NULL OR porte_cli IN ('0','1','2','3','4','5','6','7','8','9')")
@dlt.expect("autorzc_valid", "autorzc IS NULL OR autorzc IN ('S','N')")
def scr3040_clientes():
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
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Garantias ─────────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_garantias",
    comment="Garantias SCR 3040 — uma linha por <Gar>, classificadas em fidejussórias (Ident+PercGar) vs reais (VlrOrig/VlrData/DtReav)",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("gar_tp_not_null", "gar_tp IS NOT NULL")
@dlt.expect("gar_categoria_consistent",
    "(gar_categoria='fidejussoria' AND ident IS NOT NULL AND vlr_orig IS NULL) OR "
    "(gar_categoria='real' AND ident IS NULL AND vlr_orig IS NOT NULL)")
@dlt.expect("perc_gar_in_range", "perc_gar IS NULL OR (perc_gar > 0 AND perc_gar <= 100)")
@dlt.expect("garantidor_diferente_cliente", "ident IS NULL OR ident != cli_cd")
def scr3040_garantias():
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
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Vencimentos (vértices) ────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_vencimentos",
    comment="Vértices SCR 3040 — uma linha por <Op>, com vértices v110…v330 + limites/coobrigações como colunas; total_saldo agregado",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect("total_saldo_positive", "total_saldo IS NULL OR total_saldo >= 0")
@dlt.expect("vertice_unico_por_op", "vertice_count >= 1")
def scr3040_vencimentos():
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
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── ContInstFinRes 4966 + Estágio ─────────────────────────────────────────────

@dlt.table(
    name="scr3040_cont_4966",
    comment="Contabilização Res. 4966 — uma linha por <ContInstFinRes4966> com estágio aninhado (Motivo, DtAlocacao)",
    table_properties={"quality": "silver"},
    partition_cols=["dt_base"],
)
@dlt.expect_or_drop("vlr_cont_br_positive", "vlr_cont_br IS NOT NULL AND vlr_cont_br >= 0")
@dlt.expect("clas_at_fin_valid", "clas_at_fin IN ('1','2','3')")
@dlt.expect("est_inst_fin_valid", "est_inst_fin IN ('1','2','3')")
@dlt.expect("cart_prov_min_valid", "cart_prov_min IN ('C1','C2','C3','C4')")
@dlt.expect("estagio_motivo_valid", "estagio_motivo IS NULL OR LENGTH(estagio_motivo) = 3")
def scr3040_cont_4966():
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
        .withColumn("validation_run_id", F.lit("dlt_pipeline"))
        .withColumn("_silver_timestamp", F.current_timestamp())
    )


# ── Quarentena ────────────────────────────────────────────────────────────────

@dlt.table(
    name="scr3040_quarantine",
    comment="Operações SCR 3040 rejeitadas pelas regras bloqueantes (expect_or_drop) — para drill-down e remediação",
    table_properties={"quality": "quarantine"},
    partition_cols=["dt_base"],
)
def scr3040_quarantine():
    ops = _explode("operacoes").select(
        "file_name", "dt_base", "cnpj_if",
        F.col("rec.cli_cd").alias("cli_cd"),
        F.col("rec.contrt").alias("contrt"),
        F.col("rec.ipoc").alias("ipoc"),
        F.col("rec.natu_op").alias("natu_op"),
        F.col("rec.mod").alias("mod"),
        "rec",
    )
    return (
        ops
        .filter(
            (F.length("cnpj_if") != 8)
            | (~F.col("ipoc").rlike(IPOC_REGEX))
            | F.col("contrt").isNull()
            | F.col("natu_op").isNull()
            | F.col("mod").isNull()
            | (F.length(F.col("mod")) != 4)
        )
        .select(
            "file_name", "cnpj_if", "dt_base", "cli_cd", "contrt", "ipoc",
            F.to_json("rec").alias("raw_record"),
            F.array(F.lit("blocking_rule")).alias("failed_expectations"),
            F.lit("Falhou em uma ou mais regras bloqueantes do silver").alias("failure_reason"),
            F.lit(None).cast("array<string>").alias("critica_ids"),
            F.lit(None).cast("array<string>").alias("dimension_r18"),
            F.lit("dlt_pipeline").alias("validation_run_id"),
            F.current_timestamp().alias("quarantine_timestamp"),
        )
    )
