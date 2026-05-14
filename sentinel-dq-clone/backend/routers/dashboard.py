"""Dashboard router - compliance overview."""

from fastapi import APIRouter
from backend.db import query

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard():
    """Aggregate dashboard: overall score, domain scores, KPI summary, recent incidents."""

    # Overall compliance score (average of latest day's scores across all KPIs)
    overall_rows = query("""
        SELECT ROUND(AVG(score)::numeric, 1) AS avg_score
        FROM dq_quality_results
        WHERE result_date = (SELECT MAX(result_date) FROM dq_quality_results)
    """)
    overall_score = float(overall_rows[0]["avg_score"]) if overall_rows and overall_rows[0]["avg_score"] else 0

    # Per-domain compliance (latest day)
    domain_scores = query("""
        SELECT d.id, d.name, d.owner_email,
               ROUND(AVG(r.score)::numeric, 1) AS score
        FROM dq_data_domains d
        JOIN dq_quality_results r ON r.domain_id = d.id
        WHERE r.result_date = (SELECT MAX(result_date) FROM dq_quality_results)
        GROUP BY d.id, d.name, d.owner_email
        ORDER BY d.name
    """)

    # KPI summary (latest day, aggregated across domains)
    kpi_summary = query("""
        SELECT kpi_type,
               ROUND(AVG(score)::numeric, 1) AS avg_score,
               ROUND(MIN(score)::numeric, 1) AS min_score,
               ROUND(MAX(score)::numeric, 1) AS max_score,
               SUM(rules_evaluated) AS total_rules,
               SUM(rules_passed) AS total_passed,
               SUM(rules_failed) AS total_failed
        FROM dq_quality_results
        WHERE result_date = (SELECT MAX(result_date) FROM dq_quality_results)
        GROUP BY kpi_type
        ORDER BY kpi_type
    """)

    # Recent incidents (last 5)
    recent_incidents = query("""
        SELECT i.id, i.title, i.severity, i.status, i.created_at, i.assigned_to,
               d.name AS domain_name
        FROM dq_quality_incidents i
        JOIN dq_data_domains d ON i.domain_id = d.id
        ORDER BY i.created_at DESC
        LIMIT 5
    """)

    # KPI trend (last 30 days overall)
    kpi_trend = query("""
        SELECT result_date,
               ROUND(AVG(score)::numeric, 1) AS avg_score
        FROM dq_quality_results
        WHERE result_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY result_date
        ORDER BY result_date
    """)

    # Total rules and active incidents count
    stats = query("""
        SELECT
          (SELECT COUNT(*) FROM dq_quality_rules WHERE status = 'approved') AS total_rules,
          (SELECT COUNT(*) FROM dq_quality_incidents WHERE status NOT IN ('resolved')) AS open_incidents,
          (SELECT COUNT(*) FROM dq_quality_incidents WHERE severity = 'critical' AND status NOT IN ('resolved')) AS critical_incidents,
          (SELECT COUNT(*) FROM dq_quality_executions WHERE executed_at >= NOW() - INTERVAL '24 hours') AS executions_24h
    """)

    return {
        "overall_score": overall_score,
        "domain_scores": _ser(domain_scores),
        "kpi_summary": _ser(kpi_summary),
        "recent_incidents": _ser(recent_incidents),
        "kpi_trend": _ser(kpi_trend),
        "stats": _ser(stats)[0] if stats else {},
    }


def _ser(rows):
    """Serialize rows for JSON."""
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
