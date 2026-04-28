"""Quality dimension endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import CATALOG, USE_MOCK, execute_query
from models import (
    DimensionDetail,
    DimensionDetailResponse,
    QualityDimensionsResponse,
    TrendPoint,
    Violation,
)

router = APIRouter()

_R18_DIMENSIONS = [
    {"id": 1, "code": "acessibilidade", "name": "Acessibilidade", "description": "Condicoes para obter informacoes, incluindo local, forma, prazos e tratamento PcD", "article": "Art. 2, par.2, I"},
    {"id": 2, "code": "acuracia", "name": "Acuracia", "description": "Medida em que a informacao reflete a realidade de forma precisa", "article": "Art. 2, par.2, II"},
    {"id": 3, "code": "atualidade", "name": "Atualidade", "description": "Intervalo entre a ocorrencia e a disponibilizacao da informacao", "article": "Art. 2, par.2, III"},
    {"id": 4, "code": "completude", "name": "Completude", "description": "Abrangencia dos dados em relacao ao esperado", "article": "Art. 2, par.2, IV"},
    {"id": 5, "code": "confidencialidade", "name": "Confidencialidade", "description": "Controle de acesso segundo autorizacoes e legislacao vigente", "article": "Art. 2, par.2, V"},
    {"id": 6, "code": "conformidade", "name": "Conformidade", "description": "Aderencia a regras, padroes e leiautes normativos", "article": "Art. 2, par.2, VI"},
    {"id": 7, "code": "confiabilidade", "name": "Confiabilidade", "description": "Nivel de confianca nos dados em funcao de processos e controles", "article": "Art. 2, par.2, VII"},
    {"id": 8, "code": "consistencia", "name": "Consistencia", "description": "Coerencia entre dados de diferentes fontes e documentos", "article": "Art. 2, par.2, VIII"},
    {"id": 9, "code": "efetividade", "name": "Efetividade", "description": "Capacidade da informacao de produzir resultados pretendidos", "article": "Art. 2, par.2, IX"},
    {"id": 10, "code": "rastreabilidade", "name": "Rastreabilidade", "description": "Capacidade de rastrear a origem, transformacoes e destino do dado", "article": "Art. 2, par.2, X"},
    {"id": 11, "code": "tempestividade", "name": "Tempestividade", "description": "Disponibilizacao dentro dos prazos estabelecidos", "article": "Art. 2, par.2, XI"},
    {"id": 12, "code": "unicidade", "name": "Unicidade", "description": "Ausencia de registros duplicados ou redundantes", "article": "Art. 2, par.2, XII"},
]

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

    rows = await execute_query(
        "SELECT dimensao_id, dimensao_nome, metrica_principal, valor_metrica, "
        "score_pct, meta_pct, status, total_registros, registros_conformes, registros_nao_conformes "
        f"FROM {CATALOG}.gold.qualidade_dimensoes_mensal WHERE dt_base = :data_base",
        {"data_base": data_base},
    )
    dims = [
        DimensionDetail(
            id=r["dimensao_id"], code=_R18_DIMENSIONS[r["dimensao_id"] - 1]["code"],
            name=r["dimensao_nome"], description=_R18_DIMENSIONS[r["dimensao_id"] - 1]["description"],
            score=r["score_pct"], target=r["meta_pct"], status=r["status"],
        )
        for r in rows
    ]
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

    rows = await execute_query(
        "SELECT score_pct, meta_pct, status, metrica_principal, "
        "total_registros, registros_conformes, registros_nao_conformes "
        f"FROM {CATALOG}.gold.qualidade_dimensoes_mensal "
        "WHERE dt_base = :data_base AND dimensao_id = :dimension_id",
        {"data_base": data_base, "dimension_id": dimension_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data for this dimension/data_base")
    r = rows[0]
    return DimensionDetailResponse(
        dimension=d, score=r["score_pct"], target=r["meta_pct"], status=r["status"],
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
        f"FROM {CATALOG}.gold.qualidade_dimensoes_mensal "
        "WHERE dt_base >= :start GROUP BY dt_base ORDER BY dt_base",
        {"start": data_base},
    )
    return {"data_base": data_base, "trend": [{"month": r["dt_base"], "score": round(r["avg_score"], 1)} for r in rows]}
