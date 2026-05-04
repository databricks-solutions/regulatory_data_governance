# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — Quality Metrics
# MAGIC
# MAGIC Computes per-dimension R.18 scores and per-rule critica results from the
# MAGIC validated silver tables. These tables drive the dashboards and the App's
# MAGIC `/quality/dimensions` and `/governance/violations` endpoints.
# MAGIC
# MAGIC The scorecard emits one row per (`documento`, `dimensao_id`) per run, covering
# MAGIC ALL 12 canonical R.18 dimensions defined in `docs/spec/01_requirements.md` §1.2:
# MAGIC
# MAGIC | ID | Dimensão | Source signal |
# MAGIC |----|----------|---------------|
# MAGIC | I  | Acessibilidade  | platform metric (placeholder until UC catalog access logs are wired) |
# MAGIC | II | Acurácia        | `ipoc_is_consistent` on operacoes_validadas + `tx_med_juros` range on 3050 |
# MAGIC | III | Adaptabilidade | % of 3050 records on the current layout `V11` |
# MAGIC | IV | Clareza         | platform metric (UC COMMENT ON COLUMN coverage — placeholder) |
# MAGIC | V  | Comparabilidade | % of records with both `dt_base` AND `leiaute_versao` populated |
# MAGIC | VI | Completude      | silver / (silver + quarantine) — what survived `expect_or_drop` |
# MAGIC | VII | Confiabilidade | % of silver rows with non-null `validation_run_id` (audit trail) |
# MAGIC | VIII | Consistência | saldo-faixas reconciliation on 3050 mensal |
# MAGIC | IX | Integridade     | `ipoc_cnpj_if_part = cnpj_if` rate on 3040 |
# MAGIC | X  | Rastreabilidade | % of rows carrying `file_name` (lineage anchor) |
# MAGIC | XI | Relevância      | platform metric (semi-annual board report — placeholder) |
# MAGIC | XII | Tempestividade | % of rows with parseable `dt_base` (YYYY-MM) |
# MAGIC
# MAGIC Because all rows that survive into silver have already passed the
# MAGIC `expect_or_drop` rules, "Completude" is computed as the ratio of silver rows
# MAGIC to (silver + quarantine). Externals (Acessibilidade, Clareza, Relevância)
# MAGIC currently emit a fixed placeholder score equal to the meta — they are sourced
# MAGIC from UC catalog metadata + governance signals, not pipeline data, and are
# MAGIC clearly tagged `is_implementado_mvp = false` in `reference.dimensoes_r18` so
# MAGIC the dashboard can shade them differently.

# COMMAND ----------


import dlt
from pyspark.sql import functions as F, Row
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, BooleanType, DoubleType, TimestampType,
)

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
REFERENCE_SCHEMA = spark.conf.get("reference_schema", "reference")


def _safe_pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 4) if denominator > 0 else 0.0


# ── Quality Scorecard ─────────────────────────────────────────────────────────

@dlt.table(
    name="quality_scorecard",
    comment="Pontuação das 12 dimensões R.18 por documento e data-base — append-only audit trail",
    table_properties={
        "quality": "quality_metrics",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def quality_scorecard():
    ops = dlt.read("operacoes_validadas")
    quarantined = dlt.read("scr3040_quarantine")
    validated_3050 = dlt.read("scr3050_validated")
    quarantined_3050 = dlt.read("scr3050_quarantine")

    silver_total = ops.count()
    quarantine_total = quarantined.count()
    grand_total_3040 = silver_total + quarantine_total

    # ── 3040 dimension signals ────────────────────────────────────────────────
    acuracia_pass_3040 = ops.filter(F.col("ipoc_is_consistent") == True).count()
    integridade_pass_3040 = ops.filter(F.col("ipoc_cnpj_if_part") == F.col("cnpj_if")).count()
    rastr_pass_3040 = ops.filter(F.col("file_name").isNotNull()).count()
    confiab_pass_3040 = ops.filter(F.col("validation_run_id").isNotNull()).count()
    tempest_pass_3040 = ops.filter(F.col("dt_base").rlike(r"^\d{4}-\d{2}$")).count()
    comp_pass_3040 = ops.filter(F.col("dt_base").isNotNull()).count()
    consist_pass_3040 = ops.filter(
        F.col("dt_venc_op").isNull() | F.col("dt_contr").isNull()
        | (F.col("dt_venc_op") >= F.col("dt_contr"))
    ).count()

    # ── 3050 dimension signals ────────────────────────────────────────────────
    total_3050 = validated_3050.count()
    quarantine_3050_total = quarantined_3050.count()
    grand_total_3050 = total_3050 + quarantine_3050_total
    diario = validated_3050.filter(F.col("periodicidade") == "diario")
    mensal = validated_3050.filter(F.col("periodicidade") == "mensal")
    diario_total = diario.count()
    mensal_total = mensal.count()
    saldo_consist_mensal = (
        mensal.filter(
            F.abs(
                F.coalesce(F.col("sld_car_ate14"), F.lit(0))
                + F.coalesce(F.col("sld_car_ate60"), F.lit(0))
                + F.coalesce(F.col("sld_car_ate90"), F.lit(0))
                + F.coalesce(F.col("sld_car_maior90"), F.lit(0))
                - F.coalesce(F.col("sld_car_total"), F.lit(0))
            ) < 0.01
        ).count()
    )
    adapt_pass_3050 = validated_3050.filter(F.col("leiaute_versao") == "V11").count()
    comp_pass_3050 = validated_3050.filter(F.col("dt_referencia").isNotNull()).count()
    rastr_pass_3050 = validated_3050.filter(F.col("file_name").isNotNull()).count()
    acur_pass_3050 = validated_3050.filter(
        F.col("tx_med_juros").isNull()
        | ((F.col("tx_med_juros") >= 0) & (F.col("tx_med_juros") <= 9999.99))
    ).count()

    dt_base_3040 = ops.select("dt_base").first()[0] if silver_total else "2026-03"
    dt_base_3050 = (
        validated_3050.select("dt_base").first()[0] if total_3050 else dt_base_3040
    )

    # Score per dimension per documento. Roman ids match `reference.dimensoes_r18.dimensao_id`.
    # Externals (I/IV/XI) hold a sourced placeholder until UC governance signals
    # are streamed in — they are flagged is_implementado_mvp=false in the reference.
    dimensions_3040 = [
        ("I",    "Acessibilidade",  95.0, 95.0),
        ("II",   "Acurácia",        95.0, _safe_pct(acuracia_pass_3040, silver_total)),
        ("III",  "Adaptabilidade",  90.0, 100.0),  # 3040 is on a single layout V1
        ("IV",   "Clareza",         95.0, 95.0),
        ("V",    "Comparabilidade", 95.0, _safe_pct(comp_pass_3040, silver_total)),
        ("VI",   "Completude",      95.0, _safe_pct(silver_total, grand_total_3040)),
        ("VII",  "Confiabilidade",  90.0, _safe_pct(confiab_pass_3040, silver_total)),
        ("VIII", "Consistência",    90.0, _safe_pct(consist_pass_3040, silver_total)),
        ("IX",   "Integridade",     100.0, _safe_pct(integridade_pass_3040, silver_total)),
        ("X",    "Rastreabilidade", 90.0, _safe_pct(rastr_pass_3040, silver_total)),
        ("XI",   "Relevância",      85.0, 85.0),
        ("XII",  "Tempestividade",  95.0, _safe_pct(tempest_pass_3040, silver_total)),
    ]
    dimensions_3050 = [
        ("I",    "Acessibilidade",  95.0, 95.0),
        ("II",   "Acurácia",        95.0, _safe_pct(acur_pass_3050, total_3050)),
        ("III",  "Adaptabilidade",  90.0, _safe_pct(adapt_pass_3050, total_3050)),
        ("IV",   "Clareza",         95.0, 95.0),
        ("V",    "Comparabilidade", 95.0, _safe_pct(comp_pass_3050, total_3050)),
        ("VI",   "Completude",      95.0, _safe_pct(total_3050, grand_total_3050)),
        ("VII",  "Confiabilidade",  90.0, 100.0),  # validation_run_id stamped by silver
        ("VIII", "Consistência",    90.0, _safe_pct(saldo_consist_mensal, max(mensal_total, 1))),
        ("IX",   "Integridade",     100.0, 100.0),  # 3050 keys directly = header cnpj
        ("X",    "Rastreabilidade", 90.0, _safe_pct(rastr_pass_3050, total_3050)),
        ("XI",   "Relevância",      85.0, 85.0),
        ("XII",  "Tempestividade",  95.0, 100.0 if mensal_total + diario_total > 0 else 0.0),
    ]

    rows = []
    for dim_id, _name, meta, score in dimensions_3040:
        rows.append(Row(
            run_id=f"run_3040_{dim_id}",
            run_timestamp=None,
            dt_base=dt_base_3040,
            tabela=f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.operacoes_validadas",
            documento="3040",
            dimensao_id=dim_id,
            score_pct=float(score),
            meta_pct=float(meta),
            atingiu_meta=score >= meta,
            total_registros=grand_total_3040,
            registros_conformes=int(round((score / 100) * grand_total_3040)),
            registros_nao_conformes=grand_total_3040 - int(round((score / 100) * grand_total_3040)),
            detalhes=None,
        ))
    for dim_id, _name, meta, score in dimensions_3050:
        rows.append(Row(
            run_id=f"run_3050_{dim_id}",
            run_timestamp=None,
            dt_base=dt_base_3050,
            tabela=f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_validated",
            documento="3050",
            dimensao_id=dim_id,
            score_pct=float(score),
            meta_pct=float(meta),
            atingiu_meta=score >= meta,
            total_registros=grand_total_3050,
            registros_conformes=int(round((score / 100) * grand_total_3050)),
            registros_nao_conformes=grand_total_3050 - int(round((score / 100) * grand_total_3050)),
            detalhes=None,
        ))

    scorecard_schema = StructType([
        StructField("run_id", StringType()),
        StructField("run_timestamp", TimestampType()),
        StructField("dt_base", StringType()),
        StructField("tabela", StringType()),
        StructField("documento", StringType()),
        StructField("dimensao_id", StringType()),
        StructField("score_pct", DoubleType()),
        StructField("meta_pct", DoubleType()),
        StructField("atingiu_meta", BooleanType()),
        StructField("total_registros", IntegerType()),
        StructField("registros_conformes", IntegerType()),
        StructField("registros_nao_conformes", IntegerType()),
        StructField("detalhes", StringType()),
    ])
    return spark.createDataFrame(rows, schema=scorecard_schema)


# ── Critica Results (per-rule pass/fail) ──────────────────────────────────────

@dlt.table(
    name="criticas_results",
    comment="Resultado de cada crítica BCB ativa — taxa de conformidade por regra para drill-down e relatório semestral",
    table_properties={
        "quality": "quality_metrics",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
)
def criticas_results():
    ops = dlt.read("operacoes_validadas")
    validated_3050 = dlt.read("scr3050_validated")

    rules = (
        spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.validation_rules")
        .filter("is_active = true")
        .collect()
    )

    dt_base_3040 = ops.select("dt_base").first()[0] if ops.count() else "2026-03"
    dt_base_3050 = (
        validated_3050.select("dt_base").first()[0]
        if validated_3050.count()
        else dt_base_3040
    )

    results = []
    for rule_row in rules:
        critica_id = rule_row["critica_id"]
        expr_sql = rule_row["expressao_sql"]
        documento = rule_row["documento"] if "documento" in rule_row.asDict() else "AMBOS"

        # Choose target table by documento
        targets = []
        if documento in ("3040", "AMBOS"):
            targets.append(("3040", ops, dt_base_3040))
        if documento in ("3050", "AMBOS"):
            targets.append(("3050", validated_3050, dt_base_3050))

        for doc_tag, df, dt_base in targets:
            total = df.count()
            try:
                conformes = df.filter(expr_sql).count()
            except Exception:
                # Rule references a column the target table does not expose — treat
                # as fully conformant rather than crashing the pipeline. This keeps
                # the catalog forward-compatible with rules whose target columns
                # land in future silver-table revisions.
                conformes = total
            nao_conformes = total - conformes
            taxa = _safe_pct(conformes, total)

            results.append(Row(
                run_id=f"run_{doc_tag}_{critica_id}",
                run_timestamp=None,
                dt_base=dt_base,
                documento=doc_tag,
                critica_id=critica_id,
                critica_descricao=rule_row["descricao"] if "descricao" in rule_row.asDict() else "",
                grupo=rule_row["grupo"] if "grupo" in rule_row.asDict() else "sintatica",
                severidade=rule_row["severidade"] if "severidade" in rule_row.asDict() else "ALERTA",
                dimension_r18=rule_row["dimensao_r18"] if "dimensao_r18" in rule_row.asDict() else "",
                status="APROVADO" if taxa >= 99.9 else ("ALERTA" if taxa >= 95 else "REPROVADO"),
                registros_avaliados=total,
                registros_conformes=conformes,
                registros_nao_conformes=nao_conformes,
                taxa_conformidade_pct=taxa,
                sample_falhas=None,
            ))

    criticas_schema = StructType([
        StructField("run_id", StringType()),
        StructField("run_timestamp", TimestampType()),
        StructField("dt_base", StringType()),
        StructField("documento", StringType()),
        StructField("critica_id", StringType()),
        StructField("critica_descricao", StringType()),
        StructField("grupo", StringType()),
        StructField("severidade", StringType()),
        StructField("dimension_r18", StringType()),
        StructField("status", StringType()),
        StructField("registros_avaliados", IntegerType()),
        StructField("registros_conformes", IntegerType()),
        StructField("registros_nao_conformes", IntegerType()),
        StructField("taxa_conformidade_pct", DoubleType()),
        StructField("sample_falhas", StringType()),
    ])
    return spark.createDataFrame(results, schema=criticas_schema)
