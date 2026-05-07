"""Quality dimension endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, SCHEMA_GOLD, USE_MOCK
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

_MOCK_SCORES = [95.0, 92.5, 98.0, 88.0, 100.0, 91.0, 89.5, 85.0, 78.0, 90.0, 93.0, 97.0]
_MOCK_TARGETS = [90.0, 95.0, 95.0, 95.0, 100.0, 95.0, 90.0, 90.0, 85.0, 90.0, 95.0, 95.0]
_MOCK_STATUSES = ["conforme", "atencao", "conforme", "atencao", "conforme", "conforme", "atencao", "atencao", "nao_conforme", "conforme", "conforme", "conforme"]


def _mock_trend(base_score: float) -> list[TrendPoint]:
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
            dims.append(DimensionDetail(
                id=d["id"],
                code=d["code"],
                name=d["name"],
                description=d["description"],
                score=_MOCK_SCORES[i],
                target=_MOCK_TARGETS[i],
                status=_MOCK_STATUSES[i],
                metrics={},
                trend=_mock_trend(_MOCK_SCORES[i]),
            ))
        overall = round(sum(_MOCK_SCORES) / len(_MOCK_SCORES), 1)
        return QualityDimensionsResponse(data_base=data_base, overall_score=overall, dimensions=dims)

    # Note: `valor_metrica` was added by Phase 1 simplification but isn't load-bearing
    # for this endpoint — we don't need to project it.
    rows = await execute_query(
        "SELECT dimensao_id, dimensao_nome, metrica_principal, "
        "score_pct, meta_pct, status, total_registros, registros_conformes, registros_nao_conformes "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.qualidade_dimensoes_mensal WHERE dt_base = :data_base "
        "ORDER BY dimensao_id",
        {"data_base": data_base},
    )
    dims = []
    for r in rows:
        dim_int = _safe_dim_int(r["dimensao_id"])
        meta = _R18_DIMENSIONS[dim_int - 1] if 1 <= dim_int <= 12 else {"code": "", "description": ""}
        dims.append(DimensionDetail(
            id=dim_int, code=meta["code"],
            name=r["dimensao_nome"] or meta.get("name", ""),
            description=meta["description"],
            score=float(r["score_pct"] or 0), target=float(r["meta_pct"] or 0),
            status=r["status"] or "",
        ))
    overall = round(sum(d.score for d in dims) / max(len(dims), 1), 1)
    return QualityDimensionsResponse(data_base=data_base, overall_score=overall, dimensions=dims)


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
        violations = []
        if status in ("atencao", "nao_conforme"):
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
            metrics={"taxa_conformidade_pct": score, "registros_nao_conformes": 42.0},
            violations=violations,
            trend=_mock_trend(score),
        )

    # gold.qualidade_dimensoes_mensal.dimensao_id is a Roman numeral string ('I'..'XII').
    _INT_TO_ROMAN = {v: k for k, v in _DIM_ROMAN_TO_INT.items()}
    roman_id = _INT_TO_ROMAN.get(dimension_id, "")
    rows = await execute_query(
        "SELECT score_pct, meta_pct, status, metrica_principal, "
        "total_registros, registros_conformes, registros_nao_conformes "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.qualidade_dimensoes_mensal "
        "WHERE dt_base = :data_base AND dimensao_id = :dimension_id",
        {"data_base": data_base, "dimension_id": roman_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this dimension/data_base")
    r = rows[0]
    return DimensionDetailResponse(
        dimension=d,
        score=float(r["score_pct"] or 0),
        target=float(r["meta_pct"] or 0),
        status=r["status"] or "",
        metrics={}, violations=[], trend=[],
    )


@router.get("/trend")
async def get_quality_trend(
    data_base: str = Query("2026-03"),
    months: int = Query(6, ge=1, le=24),
):
    """Return overall quality score trend over time."""
    if USE_MOCK:
        overall = round(sum(_MOCK_SCORES) / len(_MOCK_SCORES), 1)
        return {"data_base": data_base, "trend": _mock_trend(overall)}

    rows = await execute_query(
        "SELECT dt_base, AVG(score_pct) as avg_score "
        f"FROM {CATALOG}.{SCHEMA_GOLD}.qualidade_dimensoes_mensal "
        "WHERE dt_base >= :start GROUP BY dt_base ORDER BY dt_base",
        {"start": data_base},
    )
    return {"data_base": data_base, "trend": [{"month": r["dt_base"], "score": round(float(r["avg_score"] or 0), 1)} for r in rows]}
