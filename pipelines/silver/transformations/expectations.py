# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — Expectations Catalog (R.18 Quality Dimensions)
# MAGIC
# MAGIC Helper module exposing the canonical mapping of DLT expectations to the 12 R.18
# MAGIC mandatory data quality dimensions for **SCR Doc 3040** and **Doc 3050 / TXB V11**.
# MAGIC
# MAGIC Field names match the XML wire format normalized to snake_case (`mod`, `natu_op`,
# MAGIC `vlr_cont_br`, `sld_car_ate14`, `encargo`, `modalidade`, `carteira`, `segmento`).
# MAGIC The actual `@dlt.expect*` decorators live next to each silver table in
# MAGIC `scr3040_validated.py` / `scr3050_validated.py`; this catalog is the authoritative
# MAGIC index used by:
# MAGIC - `quality_metrics.py` (per-dimension scorecard)
# MAGIC - `dashboards/` (R.18 conformance panels)
# MAGIC - the App's `/quality/dimensions` API
# MAGIC
# MAGIC The **canonical 12 dimensions** are those listed in
# MAGIC `docs/spec/01_requirements.md` §1.2 and seeded in
# MAGIC `reference.dimensoes_r18` (Roman id `I`..`XII`):
# MAGIC
# MAGIC | Dimension | ID | Expectation IDs |
# MAGIC |-----------|-----|-----------------|
# MAGIC | Acessibilidade  | I    | (UC catalog access logs — externo) |
# MAGIC | Acurácia        | II   | ipoc_components_consistent, perc_indx_in_range, taxa_juros_range, concessoes_positive |
# MAGIC | Adaptabilidade  | III  | leiaute_versao_v11_3050 |
# MAGIC | Clareza         | IV   | (UC COMMENT ON COLUMN coverage — externo) |
# MAGIC | Comparabilidade | V    | dt_base_present_3040, dt_referencia_present_3050 |
# MAGIC | Completude      | VI   | campos_obrigatorios_s10, valid_cnpj_if_length, modalidade_not_null, encargo_valid, segmento_valid, carteira_valid |
# MAGIC | Confiabilidade  | VII  | validation_run_id_stamped (proxy via `validation_run_id IS NOT NULL`) |
# MAGIC | Consistência    | VIII | date_vencimento_after_contrato, saldo_faixas_consistente_3018, gar_categoria_consistent, vlr_cont_br_positive |
# MAGIC | Integridade     | IX   | ipoc_cnpj_if_matches_header (proxy: `ipoc_cnpj_if_part = cnpj_if`) |
# MAGIC | Rastreabilidade | X    | file_name_present_3040, file_name_present_3050 |
# MAGIC | Relevância      | XI   | (semi-annual report + CA review — externo) |
# MAGIC | Tempestividade  | XII  | dt_base_format_valid_3040 |
# MAGIC
# MAGIC Each entry below has:
# MAGIC - `name`: matches either a `@dlt.expect_*` decorator on the validated tables
# MAGIC   (silver pipeline) OR a row in `reference.validation_rules.critica_id` whose
# MAGIC   `expressao_sql` is evaluated at runtime by `silver.criticas_results`.
# MAGIC - `documento`: '3040' | '3050' | 'AMBOS'
# MAGIC - `target_table`: silver table the rule is evaluated against. For 3050 the
# MAGIC   unified `scr3050_validated` carries a `periodicidade` column ∈ {`diario`, `mensal`}.
# MAGIC - `constraint`: SQL predicate.
# MAGIC - `action`: `expect` | `expect_or_drop` | `expect_or_fail` | `runtime_critica`
# MAGIC   (`runtime_critica` = computed by `criticas_results.py` from `validation_rules`).

# COMMAND ----------


EXPECTATIONS_BY_DIMENSION = {
    "II_acuracia": [
        {"name": "ipoc_components_consistent", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "ipoc_is_consistent = true", "action": "expect"},
        {"name": "perc_indx_in_range", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "perc_indx IS NULL OR (perc_indx >= 0 AND perc_indx <= 9999.99)", "action": "expect"},
        {"name": "taxa_juros_range", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "tx_med_juros IS NULL OR (tx_med_juros >= 0 AND tx_med_juros <= 9999.99)", "action": "expect"},
        {"name": "concessoes_positive", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "vlr_concessoes IS NULL OR vlr_concessoes >= 0", "action": "expect"},
    ],
    "III_adaptabilidade": [
        # Layout V11 awareness — 3050 silver stamps every record with `leiaute_versao='V11'`.
        # If a future ingestion wave brings V12 the `validation_rules` row CR_ADAPT_3050
        # becomes the single switch: bump it to a regex IN ('V11','V12').
        {"name": "leiaute_versao_v11_3050", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "leiaute_versao = 'V11'", "action": "runtime_critica"},
    ],
    "V_comparabilidade": [
        {"name": "dt_base_present_3040", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "dt_base IS NOT NULL", "action": "runtime_critica"},
        {"name": "dt_referencia_present_3050", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "dt_referencia IS NOT NULL", "action": "runtime_critica"},
    ],
    "VI_completude": [
        {"name": "campos_obrigatorios_s10", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "contrt IS NOT NULL AND natu_op IS NOT NULL AND mod IS NOT NULL", "action": "expect_or_drop"},
        {"name": "valid_cnpj_if_length", "documento": "AMBOS",
         "target_table": "operacoes_validadas|scr3050_validated",
         "constraint": "LENGTH(cnpj_if) = 8", "action": "expect_or_drop"},
        {"name": "modalidade_not_null", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "modalidade IS NOT NULL", "action": "expect_or_drop"},
        {"name": "encargo_valid", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "encargo IN ('pre','flu','vc','ipca','igpm','ind')", "action": "expect_or_drop"},
        {"name": "segmento_valid", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "segmento IN ('pesJuridica','pesFisica')", "action": "expect_or_drop"},
        {"name": "carteira_valid", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "carteira IN ('crdLivre','crdDirec')", "action": "expect_or_drop"},
        # IPOC = CNPJ(8) + Mod(4) + TpCli(1) + CodCli(8) + Contrt(9) = 30 chars
        {"name": "valid_ipoc_format", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": r"ipoc RLIKE '^\d{8}\d{4}[1-6]\d{8}\d{9}$'", "action": "expect_or_drop"},
        {"name": "modalidade_valid_domain", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "mod IS NOT NULL AND LENGTH(mod) = 4", "action": "expect_or_drop"},
    ],
    "VII_confiabilidade": [
        # Append-only audit trail: every silver row carries a non-null run id.
        {"name": "validation_run_id_stamped_3040", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "validation_run_id IS NOT NULL", "action": "runtime_critica"},
    ],
    "VIII_consistencia": [
        {"name": "date_vencimento_after_contrato", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr", "action": "expect"},
        {"name": "saldo_faixas_consistente_3018", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": (
             "periodicidade <> 'mensal' OR ABS("
             "COALESCE(sld_car_ate14,0)+COALESCE(sld_car_ate60,0)"
             "+COALESCE(sld_car_ate90,0)+COALESCE(sld_car_maior90,0)"
             "-COALESCE(sld_car_total,0)) < 0.01"
         ),
         "action": "expect"},
        {"name": "gar_categoria_consistent", "documento": "3040",
         "target_table": "scr3040_garantias",
         "constraint": (
             "(gar_categoria='fidejussoria' AND ident IS NOT NULL AND vlr_orig IS NULL) OR "
             "(gar_categoria='real' AND ident IS NULL AND vlr_orig IS NOT NULL)"
         ),
         "action": "expect"},
        {"name": "vlr_cont_br_positive", "documento": "3040",
         "target_table": "scr3040_cont_4966",
         "constraint": "vlr_cont_br IS NOT NULL AND vlr_cont_br >= 0", "action": "expect_or_drop"},
    ],
    "IX_integridade": [
        # Referential integrity inside the document: IPOC's first 8 chars MUST equal
        # the header cnpj_if. Equivalent of a primary-key/FK check.
        {"name": "ipoc_cnpj_if_matches_header", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "ipoc_cnpj_if_part = cnpj_if", "action": "runtime_critica"},
    ],
    "X_rastreabilidade": [
        # Source-file lineage anchor for every silver row.
        {"name": "file_name_present_3040", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": "file_name IS NOT NULL", "action": "runtime_critica"},
        {"name": "file_name_present_3050", "documento": "3050",
         "target_table": "scr3050_validated",
         "constraint": "file_name IS NOT NULL", "action": "runtime_critica"},
    ],
    "XII_tempestividade": [
        # `dt_base` must follow YYYY-MM so timeliness reports can group by month.
        {"name": "dt_base_format_valid_3040", "documento": "3040",
         "target_table": "operacoes_validadas",
         "constraint": r"dt_base RLIKE '^[0-9]{4}-[0-9]{2}$'", "action": "runtime_critica"},
    ],
}


# Dimensions evidenced exclusively by platform/governance signals (UC ACL audit,
# semi-annual board report, COMMENT-ON-COLUMN coverage). They have no row-level
# expectation — the scorecard surfaces them with sourced metrics from the App
# governance router. Listed here so consumers don't expect a `@dlt.expect_*` for them.
EXTERNAL_DIMENSIONS = {
    "I_acessibilidade":  "UC catalog access SLAs + tracking table",
    "IV_clareza":        "UC COMMENT ON COLUMN coverage %",
    "XI_relevancia":     "Relatório semestral CA + ata de reunião",
}


def get_expectations_for_dimension(dimension_code: str) -> list[dict]:
    """Return the list of expectations for a given R.18 dimension code (e.g. 'VI_completude')."""
    return EXPECTATIONS_BY_DIMENSION.get(dimension_code, [])


def get_all_blocking_expectations(documento: str | None = None) -> list[dict]:
    """Return all expectations with action=expect_or_drop, optionally filtered by documento."""
    blocking = []
    for dim_rules in EXPECTATIONS_BY_DIMENSION.values():
        for rule in dim_rules:
            if rule["action"] == "expect_or_drop":
                if documento is None or rule["documento"] in (documento, "AMBOS"):
                    blocking.append(rule)
    return blocking


def load_criticas_from_reference(spark, catalog: str = "rc18_catalog", schema: str = "reference") -> list[dict]:
    """Load active validation rules from `reference.validation_rules` for runtime evaluation."""
    df = spark.table(f"{catalog}.{schema}.validation_rules").filter("is_active = true")
    return [row.asDict() for row in df.collect()]
