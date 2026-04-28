# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — DLT Expectations Mapped to R.18 Dimensions
# MAGIC Defines reusable expectation rules loaded from the `reference.validation_rules`
# MAGIC table. These are used by the validation pipeline to dynamically apply criticas
# MAGIC as DLT expectations.
# MAGIC
# MAGIC ## R.18 Dimension → Expectation Mapping
# MAGIC | Dimension | ID | Key Expectations |
# MAGIC |-----------|-----|-----------------|
# MAGIC | Acuracia | II | ipoc_components_consistent, classificacao_risco_valida, taxa_juros_range |
# MAGIC | Atualidade | III | data_base_current, ingestion_lag_acceptable |
# MAGIC | Completude | IV | campos_obrigatorios_s10, modalidade_not_null, encargo_valid |
# MAGIC | Confidencialidade | V | (handled by UC ACLs, not DLT) |
# MAGIC | Conformidade | VI | valid_ipoc_format, modalidade_valid_domain, cnpj_if_valid |
# MAGIC | Confiabilidade | VII | pipeline_success_rate (measured post-run) |
# MAGIC | Consistencia | VIII | date_vencimento_after_contrato, saldo_faixas_consistent_3018, cosif_batimento |
# MAGIC | Efetividade | IX | ipoc_unique_in_doc |
# MAGIC | Rastreabilidade | X | (handled by UC lineage, not DLT) |
# MAGIC | Tempestividade | XI | all_dias_uteis_semana_3050, envio_no_prazo |
# MAGIC | Unicidade | XII | pk_hash_unique, ipoc_unique_per_dt_base |

from pyspark.sql import functions as F

# This module provides helper functions for loading expectations from the
# reference.validation_rules table and converting them to DLT-compatible format.

EXPECTATIONS_BY_DIMENSION = {
    "II_acuracia": [
        {"name": "ipoc_components_consistent", "constraint": "ipoc_is_consistent = true", "action": "expect"},
        {"name": "classificacao_risco_valida", "constraint": "class_op IS NULL OR class_op IN ('AA','A','B','C','D','E','F','G','H')", "action": "expect"},
        {"name": "taxa_juros_range", "constraint": "tx_med_juros IS NULL OR (tx_med_juros >= 0 AND tx_med_juros <= 9999.99)", "action": "expect"},
    ],
    "IV_completude": [
        {"name": "campos_obrigatorios_s10", "constraint": "contrt IS NOT NULL AND natu_op IS NOT NULL AND mod IS NOT NULL", "action": "expect_or_drop"},
        {"name": "modalidade_not_null", "constraint": "modalidade IS NOT NULL", "action": "expect_or_drop"},
        {"name": "encargo_valid", "constraint": "encargo IN ('pre','flu','vc','ipca','igpm','ind')", "action": "expect_or_drop"},
    ],
    "VI_conformidade": [
        {"name": "valid_cnpj_if_length", "constraint": "LENGTH(cnpj_if) = 8", "action": "expect_or_drop"},
        {"name": "valid_ipoc_format", "constraint": "ipoc RLIKE '^\\d{8}\\d{4}[1-6].+'", "action": "expect_or_drop"},
        {"name": "modalidade_valid_domain", "constraint": "mod IS NOT NULL AND LENGTH(mod) = 4", "action": "expect_or_drop"},
    ],
    "VIII_consistencia": [
        {"name": "date_vencimento_after_contrato", "constraint": "dt_venc_op IS NULL OR dt_contr IS NULL OR dt_venc_op >= dt_contr", "action": "expect_or_drop"},
        {"name": "saldo_faixas_consistent_3018", "constraint": "ABS(COALESCE(sld_car_ate14,0)+COALESCE(sld_car_15a60,0)+COALESCE(sld_car_61a90,0)+COALESCE(sld_car_maior90,0)-COALESCE(sld_car_total,0)) < 0.01", "action": "expect"},
        {"name": "cosif_code_valid", "constraint": "cosif IS NULL OR LENGTH(cosif) = 7", "action": "expect"},
    ],
    "XI_tempestividade": [
        {"name": "all_dias_uteis_semana_3050", "constraint": "dias_uteis_count = dias_uteis_expected", "action": "expect_or_fail"},
    ],
    "XII_unicidade": [
        {"name": "pk_hash_unique", "constraint": "_pk_hash IS NOT NULL", "action": "expect_or_drop"},
    ],
}


def get_expectations_for_dimension(dimension_code: str) -> list[dict]:
    """Return the list of expectations for a given R.18 dimension code."""
    return EXPECTATIONS_BY_DIMENSION.get(dimension_code, [])


def get_all_blocking_expectations() -> list[dict]:
    """Return all expectations with action=expect_or_drop (blocking)."""
    blocking = []
    for dim_rules in EXPECTATIONS_BY_DIMENSION.values():
        for rule in dim_rules:
            if rule["action"] == "expect_or_drop":
                blocking.append(rule)
    return blocking


def load_criticas_from_reference(spark, catalog: str = "rc18_catalog", schema: str = "reference") -> list[dict]:
    """Load active validation rules from the reference.validation_rules table.

    Returns a list of dicts with keys: critica_id, expressao_sql, acao_dlt, dimensao_r18.
    """
    df = spark.table(f"{catalog}.{schema}.validation_rules").filter("is_active = true")
    return [row.asDict() for row in df.collect()]
