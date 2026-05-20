"""Quality dimension endpoints.

Post-DQX-Studio integration: scores são computados em runtime a partir da
última execução DQX por tabela (`dqx_catalog.dqx_app.dq_validation_runs` +
`dq_metrics`), agrupados por dimensão R.18 conforme metadados do
`rc18_rule_meta`. Não dependemos mais de `gold.qualidade_dimensoes_mensal`
(pipeline silver→gold ainda não aplica DQX inline).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, DQX_CHECKS_TABLE, SCHEMA_GOLD, USE_MOCK
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when gold/silver tables haven't been populated yet (pipelines not run).
from db import execute_query_or_empty as execute_query
from models import (
    DimensionDetail,
    DimensionDetailResponse,
    QualityDimensionsResponse,
    TrendPoint,
    Violation,
)
from rc18_rule_meta import meta_for

router = APIRouter()

# Canonical 12 R.18 dimensions per docs/spec/01_requirements.md §1.2 (Art. 2, §2 of Joint Resolution 18).
# Aligned with the Roman-numeral seed in `notebooks/setup/setup_reference_tables.py`.
# Quality scorecards (when present) are produced externally by DQX Studio.
_R18_DIMENSIONS = [
    {"id": 1, "code": "acessibilidade", "name": "Acessibilidade", "description": "Condicoes para obter informacoes, incluindo local, forma, prazos e tratamento PcD", "article": "Art. 2, par.2, I"},
    {"id": 2, "code": "acuracia", "name": "Acurácia", "description": "Medida em que a informacao reflete a realidade de forma precisa, conforme metodologia", "article": "Art. 2, par.2, II"},
    {"id": 3, "code": "adaptabilidade", "name": "Adaptabilidade", "description": "Capacidade de gerar informações em formato que atenda diversas demandas e mudanças regulamentares", "article": "Art. 2, par.2, III"},
    {"id": 4, "code": "clareza", "name": "Clareza", "description": "Apresentação concisa, compreensível, atendendo às necessidades do usuário", "article": "Art. 2, par.2, IV"},
    {"id": 5, "code": "comparabilidade", "name": "Comparabilidade", "description": "Capacidade de identificar semelhanças e diferenças entre períodos ou domínios", "article": "Art. 2, par.2, V"},
    {"id": 6, "code": "completude", "name": "Completude", "description": "Capacidade de atender integralmente os aspectos requeridos", "article": "Art. 2, par.2, VI"},
    {"id": 7, "code": "confiabilidade", "name": "Confiabilidade", "description": "Ausência de desvio relevante nos dados revisados vs valor inicial", "article": "Art. 2, par.2, VII"},
    {"id": 8, "code": "consistencia", "name": "Consistência", "description": "Informações padronizadas e livres de contradições, mesmo de fontes diferentes", "article": "Art. 2, par.2, VIII"},
    {"id": 9, "code": "integridade", "name": "Integridade", "description": "Garantia de autenticidade e ausência de modificação não autorizada", "article": "Art. 2, par.2, IX"},
    {"id": 10, "code": "rastreabilidade", "name": "Rastreabilidade", "description": "Condições para rastrear a informação desde a origem até a disponibilização ao usuário final", "article": "Art. 2, par.2, X"},
    {"id": 11, "code": "relevancia", "name": "Relevância", "description": "Capacidade de fornecer informações úteis que influenciem tomada de decisões", "article": "Art. 2, par.2, XI"},
    {"id": 12, "code": "tempestividade", "name": "Tempestividade", "description": "Fornecimento em tempo hábil, no prazo estabelecido", "article": "Art. 2, par.2, XII"},
]

# `gold.qualidade_dimensoes_mensal.dimensao_id` is stored as a Roman numeral string
# (matches `reference.dimensoes_r18.dimensao_id`). Map to int for the App's `DimensionDetail.id` int field.
_DIM_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                     "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}


def _safe_dim_int(roman_or_int) -> int:
    """Tolerate either Roman string or int in case the schema evolves."""
    if isinstance(roman_or_int, int):
        return roman_or_int
    return _DIM_ROMAN_TO_INT.get(str(roman_or_int), 0)

# Mock alinhado ao seed atual: apenas II (Acurácia, score=92.0, 1 regra) e III
# (Adaptabilidade, score=96.5, 3 regras) têm regras DQX vinculadas — demais
# dimensões ficam com score=None (sem dados) e status='sem_regras'. A UI
# (DimensionCard.svelte) renderiza score=None como "—" e badge "Sem regras",
# diferenciando "não medido" de "0% conforme".
_MOCK_SCORES: list[float | None] = [None, 92.0, 96.5, None, None, None, None, None, None, None, None, None]
_MOCK_TARGETS = [90.0, 95.0, 90.0, 95.0, 95.0, 95.0, 90.0, 90.0, 85.0, 90.0, 95.0, 95.0]
_MOCK_STATUSES = ["sem_regras", "atencao", "conforme", "sem_regras", "sem_regras", "sem_regras", "sem_regras", "sem_regras", "sem_regras", "sem_regras", "sem_regras", "sem_regras"]
# Regras vinculadas em pipelines/silver/dqx_checks/scr3040.yml por dimensao_id.
_MOCK_RULES: dict[int, list[str]] = {
    2: ["dia_atraso_nao_negativo"],
    3: ["autorzc_in_dominio", "porte_cli_in_dominio_por_tipo", "tp_ctrl_in_dominio"],
}


def _mock_trend(base_score: float | None) -> list[TrendPoint]:
    # Sem score (sem_regras) não há histórico — devolve lista vazia para que o
    # RadarChart/SparkLine renderizem como "—" em vez de uma linha falsa.
    if base_score is None:
        return []
    return [
        TrendPoint(month=f"2025-{m:02d}", score=round(base_score - (6 - i) * 2.5, 1))
        for i, m in enumerate([10, 11, 12])
    ] + [
        TrendPoint(month=f"2026-{m:02d}", score=round(base_score - (3 - i) * 1.5, 1))
        for i, m in enumerate([1, 2, 3])
    ]


@router.get("/dimensions", response_model=QualityDimensionsResponse)
async def get_quality_dimensions(
    data_base: str = Query("2026-03"),
    trend_months: int = Query(6, ge=1, le=24),
):
    """Return scores for all 12 R.18 quality dimensions."""
    if USE_MOCK:
        dims = []
        for i, d in enumerate(_R18_DIMENSIONS):
            score = _MOCK_SCORES[i]
            dims.append(DimensionDetail(
                id=d["id"],
                code=d["code"],
                name=d["name"],
                description=d["description"],
                score=score,
                target=_MOCK_TARGETS[i],
                status=_MOCK_STATUSES[i],
                metrics={},
                rules=_MOCK_RULES.get(d["id"], []),
                trend=_mock_trend(score),
            ))
        measured = [s for s in _MOCK_SCORES if s is not None]
        overall = round(sum(measured) / len(measured), 1) if measured else 0.0
        return QualityDimensionsResponse(data_base=data_base, overall_score=overall, dimensions=dims)

    # Real mode: aggregate per dimension from the latest DQX Studio runs.
    by_dim = await _aggregate_by_dimension()
    target = 95.0  # default; could be sourced from reference.dimensoes_r18
    dims = []
    for d in _R18_DIMENSIONS:
        agg = by_dim.get(d["id"], {"total": 0, "invalid": 0, "rules": 0, "rule_names": []})
        total = agg["total"]
        invalid = agg["invalid"]
        if agg["rules"] == 0:
            # Sem regras vinculadas — score é "não-medido", não 100%.
            score: float | None = None
            status = "sem_regras"
        else:
            score = round(100 * (total - invalid) / total, 1) if total else 100.0
            status = (
                "conforme" if score >= target
                else "atencao" if score >= target - 10
                else "nao_conforme"
            )
        dims.append(DimensionDetail(
            id=d["id"], code=d["code"], name=d["name"],
            description=d["description"],
            score=score, target=target, status=status,
            metrics={
                "total_registros": float(total),
                "registros_conformes": float(total - invalid),
                "registros_nao_conformes": float(invalid),
                "regras_avaliadas": float(agg["rules"]),
            },
            rules=sorted(agg.get("rule_names", [])),
            trend=[],
        ))
    # Overall score = média APENAS das dimensões medidas (com regras). Dims sem
    # regras não distorcem o agregado para cima.
    measured = [d.score for d in dims if d.score is not None]
    overall = round(sum(measured) / len(measured), 1) if measured else 0.0
    return QualityDimensionsResponse(data_base=data_base, overall_score=overall, dimensions=dims)


async def _load_rule_user_metadata() -> dict[str, dict]:
    """Return {check_name: user_metadata_dict} for ALL active/approved rules.

    Used by `_aggregate_by_dimension` to honor the authoritative
    `dimensao_r18` tag authored in DQX Studio (falling back to
    `RC18_RULE_META` only if the tag is missing).
    """
    rows = await execute_query(
        f"SELECT checks FROM {DQX_CHECKS_TABLE} WHERE status IN ('active','approved')",
        {},
    )
    out: dict[str, dict] = {}
    for r in rows:
        raw = r.get("checks")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (json.JSONDecodeError, TypeError):
            continue
        items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
        for chk in items:
            if not isinstance(chk, dict):
                continue
            args = (chk.get("check") or {}).get("arguments") or {}
            name = chk.get("name") or (args.get("name") if isinstance(args, dict) else None)
            if name:
                out[name] = chk.get("user_metadata") or {}
    return out


async def _aggregate_by_dimension() -> dict[int, dict]:
    """Aggregate (total_rows, invalid_rows, n_rules, rule_names) per R.18 dimension.

    For each source_table_fqn, takes the LATEST SUCCESS run, parses its
    `check_metrics` and looks up each check's dimension via `rc18_rule_meta`.
    Rules without a known dimension fall into the "Outras" bucket (id=0).
    """
    # Latest SUCCESS run per source_table_fqn (any RC18 silver table).
    runs = await execute_query(
        "WITH ranked AS ("
        "  SELECT run_id, source_table_fqn, total_rows, created_at,"
        "         ROW_NUMBER() OVER (PARTITION BY source_table_fqn ORDER BY created_at DESC) AS rn"
        "  FROM dqx_catalog.dqx_app.dq_validation_runs"
        "  WHERE status = 'SUCCESS'"
        "    AND source_table_fqn LIKE 'rc18_catalog.silver.%'"
        ") SELECT run_id, source_table_fqn, total_rows FROM ranked WHERE rn = 1",
        {},
    )
    if not runs:
        return {}

    quoted = ",".join(f"'{r['run_id']}'" for r in runs)
    metrics_rows = await execute_query(
        "SELECT run_id, metric_value AS check_metrics_json "
        "FROM dqx_catalog.dqx_app.dq_metrics "
        f"WHERE metric_name = 'check_metrics' AND run_id IN ({quoted})",
        {},
    )
    metrics_by_run = {m["run_id"]: m for m in metrics_rows}

    # Pre-load user_metadata por check_name uma única vez — `dimensao_r18` da
    # DQX Studio é a fonte autoritativa para o agrupamento por dimensão.
    rule_meta_cache = await _load_rule_user_metadata()

    out: dict[int, dict] = {}
    for r in runs:
        total = int(r.get("total_rows") or 0)
        cm = metrics_by_run.get(r["run_id"])
        if not cm:
            continue
        try:
            check_metrics = json.loads(cm["check_metrics_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(check_metrics, list):
            continue
        for cmrow in check_metrics:
            check_name = cmrow.get("check_name")
            if not check_name:
                continue
            # Filtra check_metrics de runs cujas regras foram deletadas de
            # dq_quality_rules — mesma semântica de /validations/*/results
            # e /dashboard/kpis. Sem isso, dimensões podiam ser inflacionadas
            # por execuções históricas de regras stale (source='ui' apagadas).
            if check_name not in rule_meta_cache:
                continue
            um = rule_meta_cache[check_name]
            meta = meta_for(
                check_name,
                table_fqn=r.get("source_table_fqn", ""),
                user_metadata=um,
            )
            dim_id = meta["dimension_r18"]
            err = int(cmrow.get("error_count") or 0)
            warn = int(cmrow.get("warning_count") or 0)
            bucket = out.setdefault(dim_id, {"total": 0, "invalid": 0, "rules": 0, "rule_names": set()})
            bucket["total"] += total
            bucket["invalid"] += (err + warn)
            bucket["rules"] += 1
            bucket["rule_names"].add(check_name)
    # Convert sets to lists so the response can be serialized cleanly.
    for v in out.values():
        v["rule_names"] = sorted(v.get("rule_names", set()))
    return out


@router.get("/dimensions/{dimension_id}", response_model=DimensionDetailResponse)
async def get_quality_dimension_detail(
    dimension_id: int,
    data_base: str = Query("2026-03"),
):
    """Return detailed metrics for a single R.18 dimension."""
    if dimension_id < 1 or dimension_id > 12:
        raise HTTPException(status_code=404, detail="Dimension not found (must be 1-12)")

    d = _R18_DIMENSIONS[dimension_id - 1]
    score = _MOCK_SCORES[dimension_id - 1]
    target = _MOCK_TARGETS[dimension_id - 1]
    status = _MOCK_STATUSES[dimension_id - 1]

    if USE_MOCK:
        # Dimensão sem regras: sem score, sem violações, sem trend.
        if status == "sem_regras":
            return DimensionDetailResponse(
                dimension=d, score=None, target=target, status=status,
                metrics={}, violations=[], trend=[],
            )
        violations = []
        if status in ("atencao", "nao_conforme") and score is not None:
            violations = [
                Violation(
                    rule_id=f"SEM_{dimension_id:03d}",
                    rule_description=f"Violacao na dimensao {d['name']}",
                    severity="error" if status == "nao_conforme" else "warning",
                    count=42 + dimension_id * 10,
                    sample_records=["IPOC_12345678...", "IPOC_87654321..."],
                ),
            ]
        return DimensionDetailResponse(
            dimension=d,
            score=score,
            target=target,
            status=status,
            metrics={"taxa_conformidade_pct": float(score or 0.0), "registros_nao_conformes": 42.0},
            violations=violations,
            trend=_mock_trend(score),
        )

    by_dim = await _aggregate_by_dimension()
    agg = by_dim.get(dimension_id, {"total": 0, "invalid": 0, "rules": 0, "rule_names": []})
    target = 95.0
    if agg["rules"] == 0:
        score = None
        status = "sem_regras"
    else:
        score = round(100 * (agg["total"] - agg["invalid"]) / agg["total"], 1) if agg["total"] else 100.0
        status = (
            "conforme" if score >= target
            else "atencao" if score >= target - 10
            else "nao_conforme"
        )
    return DimensionDetailResponse(
        dimension=d, score=score, target=target, status=status,
        metrics={
            "total_registros": float(agg["total"]),
            "registros_conformes": float(agg["total"] - agg["invalid"]),
            "registros_nao_conformes": float(agg["invalid"]),
            "regras_avaliadas": float(agg["rules"]),
        },
        violations=[], trend=[],
    )


@router.get("/trend")
async def get_quality_trend(
    data_base: str = Query("2026-03"),
    months: int = Query(6, ge=1, le=24),
):
    """Return overall quality score trend over time."""
    if USE_MOCK:
        measured = [s for s in _MOCK_SCORES if s is not None]
        overall = round(sum(measured) / len(measured), 1) if measured else 0.0
        return {"data_base": data_base, "trend": _mock_trend(overall) if measured else []}

    # Trend baseado em dq_metrics: para cada YYYY-MM, agrupa o score overall
    # de TODAS as runs do mes (não apenas latest). Limita ao último ano.
    rows = await execute_query(
        "WITH per_run AS ("
        "  SELECT m.run_id,"
        "         SUBSTRING(date_format(MIN(m.run_time), 'yyyy-MM-dd'), 1, 7) AS month,"
        "         MAX(CASE WHEN metric_name = 'input_row_count'  THEN CAST(metric_value AS BIGINT) END) AS total_rows,"
        "         MAX(CASE WHEN metric_name = 'error_row_count'  THEN CAST(metric_value AS BIGINT) END) AS error_rows,"
        "         MAX(CASE WHEN metric_name = 'warning_row_count' THEN CAST(metric_value AS BIGINT) END) AS warn_rows"
        "  FROM dqx_catalog.dqx_app.dq_metrics m"
        "  WHERE metric_name IN ('input_row_count','error_row_count','warning_row_count')"
        "  GROUP BY m.run_id"
        ") SELECT month, "
        "    ROUND(100.0 * (SUM(total_rows) - SUM(COALESCE(error_rows,0)) - SUM(COALESCE(warn_rows,0))) / NULLIF(SUM(total_rows), 0), 1) AS score "
        "FROM per_run WHERE month IS NOT NULL "
        "GROUP BY month ORDER BY month",
        {},
    )
    return {"data_base": data_base, "trend": [{"month": r["month"], "score": float(r["score"] or 0)} for r in rows]}
