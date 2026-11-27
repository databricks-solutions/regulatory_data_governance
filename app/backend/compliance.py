"""Índice R.18 a partir de um conjunto de runs da DQX Studio.

Fonte única do Índice da Home (`/dashboard/kpis`) e da Tendência
(`/quality/trend`): o ponto do mês de referência é o próprio índice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from db import DQX_METRICS_TABLE
from db import execute_query_or_empty as execute_query
from dqx_rules import RuleIndex, build_index, load_executed_rules
from rc18_rule_meta import meta_for


R18_DIMENSIONS = range(1, 13)


@dataclass
class ComplianceAgg:
    by_dim: dict[int, dict] = field(default_factory=dict)  # dim → total/invalid/rules
    pending: dict[str, int] = field(default_factory=lambda: {"3040": 0, "3050": 0})


async def load_check_metrics(runs: list[dict]) -> dict[str, list]:
    """run_id → lista `check_metrics` do run (runs sem métrica ficam de fora)."""
    if not runs:
        return {}
    quoted = ",".join(f"'{r['run_id']}'" for r in runs)
    rows = await execute_query(
        "SELECT run_id, metric_value AS check_metrics_json "
        f"FROM {DQX_METRICS_TABLE} "
        f"WHERE metric_name = 'check_metrics' AND run_id IN ({quoted})",
        {},
        cache_ns="dqx",
    )
    out: dict[str, list] = {}
    for m in rows:
        try:
            parsed = json.loads(m["check_metrics_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list):
            out[m["run_id"]] = parsed
    return out


def aggregate(runs: list[dict], metrics_by_run: dict[str, list], rule_um: RuleIndex) -> ComplianceAgg:
    """Soma total/violações por dimensão R.18, uma parcela por (run, regra em vigor)."""
    agg = ComplianceAgg()
    for r in runs:
        total = int(r.get("total_rows") or 0)
        table_fqn = r.get("source_table_fqn") or ""
        low = table_fqn.lower()
        doc = "3040" if "scr3040" in low else "3050" if "scr3050" in low else ""
        for cmrow in metrics_by_run.get(r["run_id"], []):
            check_name = cmrow.get("check_name")
            if not check_name:
                continue
            # Regra fora da versão em vigor não conta — mesma semântica das Críticas.
            um = rule_um.get(table_fqn, check_name)
            if um is None:
                continue
            meta = meta_for(check_name, table_fqn=table_fqn, user_metadata=um)
            affected = int(cmrow.get("error_count") or 0) + int(cmrow.get("warning_count") or 0)
            bucket = agg.by_dim.setdefault(meta["dimension_r18"], {"total": 0, "invalid": 0, "rules": 0})
            bucket["total"] += total
            bucket["invalid"] += affected
            bucket["rules"] += 1
            if affected > 0 and doc in agg.pending:
                agg.pending[doc] += 1
    return agg


def dimension_score(bucket: dict) -> float:
    if not bucket["total"]:
        return 100.0
    return round(100 * (bucket["total"] - bucket["invalid"]) / bucket["total"], 2)


def compliance_index(agg: ComplianceAgg) -> float | None:
    """Média simples das dimensões com regra; None se nenhuma foi medida.

    2 casas, não 1: com 10 dimensões em 100 e duas em 99,9/99,7 a média dá
    99,96667, que em 1 casa virava 100,0 — índice cheio com violação aberta.
    """
    scores = [
        dimension_score(b) for dim, b in agg.by_dim.items() if dim in R18_DIMENSIONS and b["rules"]
    ]
    return round(sum(scores) / len(scores), 2) if scores else None


async def load_rule_index() -> RuleIndex:
    return build_index(await load_executed_rules())
