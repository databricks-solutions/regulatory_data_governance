"""KPIs router - time series and per-domain KPI scores."""

from fastapi import APIRouter, Query
from typing import Optional
from backend.db import query

router = APIRouter(prefix="/api/kpis", tags=["kpis"])


@router.get("")
def get_kpi_timeseries(
    domain_id: Optional[int] = None,
    kpi_type: Optional[str] = None,
    days: int = Query(90, le=365),
):
    """Time series of KPI scores."""
    conditions = ["result_date >= CURRENT_DATE - INTERVAL '%s days'" % days]
    params = []

    if domain_id:
        conditions.append("r.domain_id = %s")
        params.append(domain_id)
    if kpi_type:
        conditions.append("r.kpi_type = %s")
        params.append(kpi_type)

    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT r.result_date, r.kpi_type, r.score, r.rules_evaluated, r.rules_passed, r.rules_failed,
               d.name AS domain_name
        FROM dq_quality_results r
        JOIN dq_data_domains d ON r.domain_id = d.id
        WHERE {where}
        ORDER BY r.result_date, r.kpi_type
    """, params or None)

    return _ser(rows)


@router.get("/summary")
def get_kpi_summary():
    """KPI summary per domain and type (latest date)."""
    rows = query("""
        SELECT d.name AS domain_name, d.id AS domain_id,
               r.kpi_type,
               ROUND(AVG(r.score)::numeric, 1) AS avg_score,
               ROUND(MIN(r.score)::numeric, 1) AS min_score
        FROM dq_quality_results r
        JOIN dq_data_domains d ON r.domain_id = d.id
        WHERE r.result_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY d.name, d.id, r.kpi_type
        ORDER BY d.name, r.kpi_type
    """)
    return _ser(rows)


@router.get("/domains")
def get_domains():
    """List all data domains."""
    rows = query("SELECT * FROM dq_data_domains ORDER BY name")
    return _ser(rows)


def _ser(rows):
    result = []
    for row in rows:
        r = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool, type(None), list, dict)):
                r[k] = v
            else:
                r[k] = str(v)
        result.append(r)
    return result
