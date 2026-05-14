"""Executions router - quality rule execution history."""

from fastapi import APIRouter, Query
from typing import Optional
from backend.db import query

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("")
def list_executions(
    domain_id: Optional[int] = None,
    rule_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
):
    """List execution history."""
    conditions = ["1=1"]
    params = []

    if domain_id:
        conditions.append("e.domain_id = %s")
        params.append(domain_id)
    if rule_id:
        conditions.append("e.rule_id = %s")
        params.append(rule_id)
    if status:
        conditions.append("e.status = %s")
        params.append(status)

    where = " AND ".join(conditions)
    params.append(limit)

    rows = query(f"""
        SELECT e.*, r.name AS rule_name, r.rule_type, d.name AS domain_name
        FROM dq_quality_executions e
        JOIN dq_quality_rules r ON e.rule_id = r.id
        JOIN dq_data_domains d ON e.domain_id = d.id
        WHERE {where}
        ORDER BY e.executed_at DESC
        LIMIT %s
    """, params)

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
