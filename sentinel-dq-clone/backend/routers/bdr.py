"""BDR Conciliation router."""

from fastapi import APIRouter, Query
from typing import Optional
from backend.db import query

router = APIRouter(prefix="/api/bdr", tags=["bdr"])


@router.get("")
def list_conciliations(
    domain_id: Optional[int] = None,
    status: Optional[str] = None,
    days: int = Query(90, le=365),
):
    """List BDR conciliation results."""
    conditions = ["c.conciliation_date >= CURRENT_DATE - INTERVAL '%s days'" % days]
    params = []

    if domain_id:
        conditions.append("c.domain_id = %s")
        params.append(domain_id)
    if status:
        conditions.append("c.status = %s")
        params.append(status)

    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT c.*, d.name AS domain_name
        FROM dq_bdr_conciliation c
        JOIN dq_data_domains d ON c.domain_id = d.id
        WHERE {where}
        ORDER BY c.conciliation_date DESC, c.metric_name
    """, params or None)

    return _ser(rows)


@router.get("/summary")
def bdr_summary():
    """Summary stats for BDR conciliation."""
    rows = query("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status = 'ok') AS ok_count,
          COUNT(*) FILTER (WHERE status = 'warning') AS warning_count,
          COUNT(*) FILTER (WHERE status = 'divergent') AS divergent_count,
          COUNT(*) FILTER (WHERE status = 'resolved') AS resolved_count,
          ROUND(AVG(ABS(divergence_pct))::numeric, 4) AS avg_divergence_pct
        FROM dq_bdr_conciliation
        WHERE conciliation_date >= CURRENT_DATE - INTERVAL '30 days'
    """)
    return _ser(rows)[0] if rows else {}


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
