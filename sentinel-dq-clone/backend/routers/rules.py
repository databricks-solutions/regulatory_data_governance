"""Rules router - CRUD for quality rules."""

import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.db import query, execute_returning, execute

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCreate(BaseModel):
    domain_id: int
    name: str
    description: Optional[str] = None
    rule_type: str
    target_table: str
    target_column: Optional[str] = None
    parameters: Optional[dict] = None
    threshold: float = 95.0
    severity: str = "error"
    owner_email: Optional[str] = None
    status: str = "draft"


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    threshold: Optional[float] = None
    severity: Optional[str] = None
    owner_email: Optional[str] = None
    status: Optional[str] = None


@router.get("")
def list_rules(
    domain_id: Optional[int] = None,
    rule_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """List quality rules with optional filters."""
    conditions = ["1=1"]
    params = []

    if domain_id:
        conditions.append("r.domain_id = %s")
        params.append(domain_id)
    if rule_type:
        conditions.append("r.rule_type = %s")
        params.append(rule_type)
    if status:
        conditions.append("r.status = %s")
        params.append(status)

    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT r.*, d.name AS domain_name,
               (SELECT COUNT(*) FROM dq_quality_executions e WHERE e.rule_id = r.id) AS execution_count,
               (SELECT ROUND(AVG(e.score)::numeric, 1) FROM dq_quality_executions e WHERE e.rule_id = r.id AND e.executed_at >= NOW() - INTERVAL '30 days') AS avg_score_30d
        FROM dq_quality_rules r
        JOIN dq_data_domains d ON r.domain_id = d.id
        WHERE {where}
        ORDER BY r.domain_id, r.name
    """, params or None)

    return _ser(rows)


@router.post("")
def create_rule(data: RuleCreate):
    rows = execute_returning(
        """INSERT INTO dq_quality_rules
           (domain_id, name, description, rule_type, target_table, target_column,
            parameters, threshold, severity, owner_email, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (data.domain_id, data.name, data.description, data.rule_type,
         data.target_table, data.target_column,
         json.dumps(data.parameters) if data.parameters else "{}",
         data.threshold, data.severity, data.owner_email, data.status),
    )
    return _ser(rows)[0]


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: RuleUpdate):
    updates = []
    params = []
    if data.name is not None:
        updates.append("name = %s")
        params.append(data.name)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.threshold is not None:
        updates.append("threshold = %s")
        params.append(data.threshold)
    if data.severity is not None:
        updates.append("severity = %s")
        params.append(data.severity)
    if data.owner_email is not None:
        updates.append("owner_email = %s")
        params.append(data.owner_email)
    if data.status is not None:
        updates.append("status = %s")
        params.append(data.status)

    if not updates:
        raise HTTPException(400, "Nenhum campo para atualizar")

    updates.append("updated_at = NOW()")
    params.append(rule_id)

    rows = execute_returning(
        f"UPDATE dq_quality_rules SET {', '.join(updates)} WHERE id = %s RETURNING *",
        tuple(params),
    )
    if not rows:
        raise HTTPException(404, "Regra nao encontrada")
    return _ser(rows)[0]


@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    execute("DELETE FROM dq_quality_executions WHERE rule_id = %s", (rule_id,))
    execute("DELETE FROM dq_quality_rules WHERE id = %s", (rule_id,))
    return {"deleted": True}


@router.post("/{rule_id}/approve")
def approve_rule(rule_id: int):
    rows = execute_returning(
        "UPDATE dq_quality_rules SET status = 'approved', updated_at = NOW(), version = version + 1 WHERE id = %s RETURNING *",
        (rule_id,),
    )
    if not rows:
        raise HTTPException(404, "Regra nao encontrada")
    return _ser(rows)[0]


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
