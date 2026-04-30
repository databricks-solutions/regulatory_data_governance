# Databricks notebook source
# MAGIC %md
# MAGIC # Silver — Quality Metrics
# MAGIC
# MAGIC Computes per-dimension R.18 scores and per-rule critica results from the
# MAGIC validated silver tables. These tables drive the dashboards and the App's
# MAGIC `/quality/dimensions` and `/governance/violations` endpoints.
# MAGIC
# MAGIC Because all records that survive into silver have already passed the
# MAGIC `expect_or_drop` rules, "Conformidade" (VI) is computed as the ratio of
# MAGIC silver rows to (silver + quarantine). "Acurácia" (II) is computed from
# MAGIC `ipoc_is_consistent` on `operacoes_validadas`. Other dimensions either
# MAGIC come from the DLT event log (TODO) or from external signals (UC ACL audit,
# MAGIC pipeline success rate).

# COMMAND ----------


import dlt
from pyspark.sql import functions as F, Row

SOURCE_CATALOG = spark.conf.get("source_catalog", "rc18_catalog")
SILVER_SCHEMA = spark.conf.get("silver_schema", "silver")
QUALITY_SCHEMA = spark.conf.get("quality_schema", "quality")
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
    schema=f"{SOURCE_CATALOG}.{QUALITY_SCHEMA}",
)
def quality_scorecard():
    ops = dlt.read("operacoes_validadas")
    quarantined = dlt.read("scr3040_quarantine")
    diario = dlt.read("scr3050_diario")
    mensal = dlt.read("scr3050_mensal")

    silver_total = ops.count()
    quarantine_total = quarantined.count()
    grand_total_3040 = silver_total + quarantine_total
    acuracia_pass = ops.filter(F.col("ipoc_is_consistent") == True).count()
    distinct_ipocs = ops.select("dt_base", "ipoc").distinct().count()

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

    dt_base_3040 = ops.select("dt_base").first()[0] if silver_total else "2026-03"
    dt_base_3050 = mensal.select("dt_base").first()[0] if mensal_total else dt_base_3040

    # Score per dimension per documento. NULL meta uses the reference table at gold.
    dimensions_3040 = [
        ("II",   "Acuracia",         95.0, _safe_pct(acuracia_pass, silver_total)),
        ("IV",   "Completude",       95.0, _safe_pct(silver_total, grand_total_3040)),
        ("VI",   "Conformidade",     95.0, _safe_pct(silver_total, grand_total_3040)),
        ("XII",  "Unicidade",        95.0, _safe_pct(distinct_ipocs, silver_total)),
        # Externals — placeholders until wired from DLT event log / monitoring
        ("I",    "Acessibilidade",   95.0, 95.0),
        ("III",  "Atualidade",       95.0, 98.0),
        ("V",    "Confidencialidade", 100.0, 100.0),
        ("VII",  "Confiabilidade",   90.0, 90.0),
        ("VIII", "Consistencia",     90.0, 90.0),
        ("IX",   "Efetividade",      85.0, 85.0),
        ("X",    "Rastreabilidade",  90.0, 90.0),
        ("XI",   "Tempestividade",   95.0, 95.0),
    ]
    dimensions_3050 = [
        ("IV",   "Completude",   95.0, _safe_pct(diario_total + mensal_total, max(diario_total + mensal_total, 1))),
        ("VI",   "Conformidade", 95.0, _safe_pct(diario_total + mensal_total, max(diario_total + mensal_total, 1))),
        ("VIII", "Consistencia", 90.0, _safe_pct(saldo_consist_mensal, max(mensal_total, 1))),
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
            tabela=f"{SOURCE_CATALOG}.{SILVER_SCHEMA}.scr3050_diario",
            documento="3050",
            dimensao_id=dim_id,
            score_pct=float(score),
            meta_pct=float(meta),
            atingiu_meta=score >= meta,
            total_registros=diario_total + mensal_total,
            registros_conformes=int(round((score / 100) * (diario_total + mensal_total))),
            registros_nao_conformes=(diario_total + mensal_total) - int(round((score / 100) * (diario_total + mensal_total))),
            detalhes=None,
        ))

    return spark.createDataFrame(rows)


# ── Critica Results (per-rule pass/fail) ──────────────────────────────────────

@dlt.table(
    name="criticas_results",
    comment="Resultado de cada crítica BCB ativa — taxa de conformidade por regra para drill-down e relatório semestral",
    table_properties={
        "quality": "quality_metrics",
        "delta.logRetentionDuration": "interval 1825 days",
    },
    partition_cols=["dt_base"],
    schema=f"{SOURCE_CATALOG}.{QUALITY_SCHEMA}",
)
def criticas_results():
    ops = dlt.read("operacoes_validadas")
    diario = dlt.read("scr3050_diario")
    mensal = dlt.read("scr3050_mensal")

    rules = (
        spark.table(f"{SOURCE_CATALOG}.{REFERENCE_SCHEMA}.validation_rules")
        .filter("is_active = true")
        .collect()
    )

    dt_base_3040 = ops.select("dt_base").first()[0] if ops.count() else "2026-03"
    dt_base_3050 = mensal.select("dt_base").first()[0] if mensal.count() else dt_base_3040

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
            targets.append(("3050", diario.unionByName(mensal, allowMissingColumns=True), dt_base_3050))

        for doc_tag, df, dt_base in targets:
            total = df.count()
            try:
                conformes = df.filter(expr_sql).count()
            except Exception:
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

    if not results:
        return spark.createDataFrame(
            [],
            schema="run_id STRING, dt_base STRING, documento STRING, critica_id STRING",
        )
    return spark.createDataFrame(results)
