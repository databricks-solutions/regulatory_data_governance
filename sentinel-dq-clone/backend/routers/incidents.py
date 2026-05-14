"""Incidents router - quality incident management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.db import query, execute_returning

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


class IncidentCreate(BaseModel):
    domain_id: int
    rule_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    severity: str = "medium"
    assigned_to: Optional[str] = None
    source_table: Optional[str] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    root_cause: Optional[str] = None
    resolution: Optional[str] = None


class ActionCreate(BaseModel):
    action_type: str
    description: str
    owner_email: Optional[str] = None
    deadline: Optional[str] = None


@router.get("")
def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    domain_id: Optional[int] = None,
):
    """List all incidents."""
    conditions = ["1=1"]
    params = []

    if status:
        conditions.append("i.status = %s")
        params.append(status)
    if severity:
        conditions.append("i.severity = %s")
        params.append(severity)
    if domain_id:
        conditions.append("i.domain_id = %s")
        params.append(domain_id)

    where = " AND ".join(conditions)

    rows = query(f"""
        SELECT i.*, d.name AS domain_name, r.name AS rule_name,
               (SELECT COUNT(*) FROM dq_quality_actions a WHERE a.incident_id = i.id) AS action_count,
               (SELECT COUNT(*) FROM dq_quality_actions a WHERE a.incident_id = i.id AND a.status = 'completed') AS actions_completed
        FROM dq_quality_incidents i
        JOIN dq_data_domains d ON i.domain_id = d.id
        LEFT JOIN dq_quality_rules r ON i.rule_id = r.id
        WHERE {where}
        ORDER BY
          CASE i.status
            WHEN 'open' THEN 1
            WHEN 'investigating' THEN 2
            WHEN 'assigned' THEN 3
            WHEN 'resolved' THEN 4
          END,
          CASE i.severity
            WHEN 'critical' THEN 1
            WHEN 'high' THEN 2
            WHEN 'medium' THEN 3
            WHEN 'low' THEN 4
          END,
          i.created_at DESC
    """, params or None)

    return _ser(rows)


@router.get("/{incident_id}")
def get_incident(incident_id: int):
    rows = query("""
        SELECT i.*, d.name AS domain_name, r.name AS rule_name
        FROM dq_quality_incidents i
        JOIN dq_data_domains d ON i.domain_id = d.id
        LEFT JOIN dq_quality_rules r ON i.rule_id = r.id
        WHERE i.id = %s
    """, (incident_id,))
    if not rows:
        raise HTTPException(404, "Incidente nao encontrado")
    return _ser(rows)[0]


@router.post("")
def create_incident(data: IncidentCreate):
    rows = execute_returning(
        """INSERT INTO dq_quality_incidents
           (domain_id, rule_id, title, description, severity, assigned_to, source_table)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (data.domain_id, data.rule_id, data.title, data.description,
         data.severity, data.assigned_to, data.source_table),
    )
    return _ser(rows)[0]


@router.put("/{incident_id}")
def update_incident(incident_id: int, data: IncidentUpdate):
    updates = []
    params = []
    for field in ["title", "description", "severity", "status", "assigned_to", "root_cause", "resolution"]:
        val = getattr(data, field, None)
        if val is not None:
            updates.append(f"{field} = %s")
            params.append(val)

    if not updates:
        raise HTTPException(400, "Nenhum campo para atualizar")

    updates.append("updated_at = NOW()")
    params.append(incident_id)

    rows = execute_returning(
        f"UPDATE dq_quality_incidents SET {', '.join(updates)} WHERE id = %s RETURNING *",
        tuple(params),
    )
    if not rows:
        raise HTTPException(404, "Incidente nao encontrado")
    return _ser(rows)[0]


@router.put("/{incident_id}/resolve")
def resolve_incident(incident_id: int):
    rows = execute_returning(
        """UPDATE dq_quality_incidents
           SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
           WHERE id = %s RETURNING *""",
        (incident_id,),
    )
    if not rows:
        raise HTTPException(404, "Incidente nao encontrado")
    return _ser(rows)[0]


@router.get("/{incident_id}/actions")
def list_actions(incident_id: int):
    rows = query(
        "SELECT * FROM dq_quality_actions WHERE incident_id = %s ORDER BY created_at",
        (incident_id,),
    )
    return _ser(rows)


@router.post("/{incident_id}/actions")
def create_action(incident_id: int, data: ActionCreate):
    rows = execute_returning(
        """INSERT INTO dq_quality_actions
           (incident_id, action_type, description, owner_email, deadline)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (incident_id, data.action_type, data.description, data.owner_email, data.deadline),
    )
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
