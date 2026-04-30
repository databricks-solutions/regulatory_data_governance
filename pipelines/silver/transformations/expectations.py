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
# MAGIC ## R.18 Dimension → Expectation Map
# MAGIC | Dimension | ID | Expectation IDs |
# MAGIC |-----------|-----|-----------------|
# MAGIC | Acessibilidade   | I    | (UC ACL audit, externo) |
# MAGIC | Acuracia         | II   | ipoc_components_consistent, taxa_juros_range, perc_indx_in_range |
# MAGIC | Atualidade       | III  | data_base_current, ingestion_lag_acceptable |
# MAGIC | Completude       | IV   | campos_obrigatorios_s10, modalidade_not_null, encargo_valid, carteira_valid |
# MAGIC | Confidencialidade| V    | (UC ACL, externo) |
# MAGIC | Conformidade     | VI   | valid_ipoc_format, modalidade_valid_domain, valid_cnpj_if_length, encargo_valid, segmento_valid |
# MAGIC | Confiabilidade   | VII  | (pipeline_success_rate, externo) |
# MAGIC | Consistencia     | VIII | date_vencimento_after_contrato, saldo_faixas_consistente_3018, gar_categoria_consistent, vlr_cont_br_positive |
# MAGIC | Efetividade      | IX   | ipoc_unique_in_doc |
# MAGIC | Rastreabilidade  | X    | (UC lineage, externo) |
# MAGIC | Tempestividade   | XI   | all_dias_uteis_semana_3050, envio_no_prazo |
# MAGIC | Unicidade        | XII  | ipoc_unique_per_dt_base |

# COMMAND ----------


EXPECTATIONS_BY_DIMENSION = {
    "II_acuracia": [
        {"name": "ipoc_components_consistent", "documento": "3040",
         "constraint": "ipoc_is_consistent = true", "action": "expect"},
        {"name": "taxa_juros_range", "documento": "3050",
         "constraint": "tx_med_juros IS NULL OR (tx_med_juros >= 0 AND tx_med_juros <= 9999.99)", "action": "expect"},
        {"name": "perc_indx_in_range", "documento": "3040",
         "constraint": "perc_indx IS NULL OR (perc_indx >= 0 AND perc_indx <= 9999.99)", "action": "expect"},
    ],
    "IV_completude": [
        {"name": "campos_obrigatorios_s10", "documento": "3040",
         "constraint": "contrt IS NOT NULL AND natu_op IS NOT NULL AND mod IS NOT NULL", "action": "expect_or_drop"},
        {"name": "modalidade_not_null", "documento": "3050",
         "constraint": "modalidade IS NOT NULL", "action": "expect_or_drop"},
        {"name": "encargo_valid", "documento": "3050",
         "constraint": "encargo IN ('pre','flu','vc','ipca','igpm','ind')", "action": "expect_or_drop"},
        {"name": "carteira_valid", "documento": "3050",
         "constraint": "carteira IN ('crdLivre','crdDirec')", "action": "expect_or_drop"},
    ],
    "VI_conformidade": [
        {"name": "valid_cnpj_if_length", "documento": "AMBOS",
         "constraint": "LENGTH(cnpj_if) = 8", "action": "expect_or_drop"},
        # IPOC = CNPJ(8) + Mod(4) + TpCli(1) + CodCli(8) + Contrt(9) = 30 chars
        {"name": "valid_ipoc_format", "documento": "3040",
         "constraint": r"ipoc RLIKE '^\d{8}\d{4}[1-6]\d{8}\d{9}$'", "action": "expect_or_drop"},
        {"name": "modalidade_valid_domain", "documento": "3040",
         "constraint": "mod IS NOT NULL AND LENGTH(mod) = 4", "action": "expect_or_drop"},
        {"name": "segmento_valid", "documento": "3050",
         "constraint": "segmento IN ('pesJuridica','pesFisica')", "action": "expect_or_drop"},
    ],
    "VIII_consistencia": [
        {"name": "date_vencimento_after_contrato", "documento": "3040",
         "constraint": "dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr", "action": "expect"},
        {"name": "saldo_faixas_consistente_3018", "documento": "3050",
         "constraint": "ABS(COALESCE(sld_car_ate14,0)+COALESCE(sld_car_ate60,0)+COALESCE(sld_car_ate90,0)+COALESCE(sld_car_maior90,0)-COALESCE(sld_car_total,0)) < 0.01",
         "action": "expect"},
        {"name": "gar_categoria_consistent", "documento": "3040",
         "constraint": "(gar_categoria='fidejussoria' AND ident IS NOT NULL AND vlr_orig IS NULL) OR (gar_categoria='real' AND ident IS NULL AND vlr_orig IS NOT NULL)",
         "action": "expect"},
        {"name": "vlr_cont_br_positive", "documento": "3040",
         "constraint": "vlr_cont_br IS NOT NULL AND vlr_cont_br >= 0", "action": "expect_or_drop"},
    ],
    "XI_tempestividade": [
        {"name": "all_dias_uteis_semana_3050", "documento": "3050",
         "constraint": "dias_uteis_count = dias_uteis_expected", "action": "expect_or_fail"},
    ],
    "XII_unicidade": [
        {"name": "ipoc_unique_per_dt_base", "documento": "3040",
         "constraint": "ipoc IS NOT NULL", "action": "expect_or_drop"},
    ],
}


def get_expectations_for_dimension(dimension_code: str) -> list[dict]:
    """Return the list of expectations for a given R.18 dimension code (e.g. 'VI_conformidade')."""
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
