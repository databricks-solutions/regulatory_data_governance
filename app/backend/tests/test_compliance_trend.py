"""A Tendência da Home tem de bater com o Índice R.18 do card.

Antes o `/quality/trend` somava linhas de todos os runs do mês de execução, sem
escopo nem filtro de run publicado, e o ponto do mês divergia do índice do card.
"""

import asyncio
import json
import unittest
from unittest.mock import patch

from app.backend.routers import dashboard as dash
from app.backend.routers import quality as qual

# Os routers importam como módulos de topo (app/backend no sys.path).
import compliance  # noqa: E402
import data_base  # noqa: E402
from models import TableDataBase  # noqa: E402

OPS = "c.silver.scr3040_operacoes"
CLI = "c.silver.scr3040_clientes"

# Mais recente primeiro, como `_published_runs` devolve.
RUNS = {
    OPS: [
        {"run_id": "ops_nov", "source_table_fqn": OPS, "total_rows": 1000, "created_at": "2026-11-20", "db": "2026-11-30"},
        {"run_id": "ops_out", "source_table_fqn": OPS, "total_rows": 1000, "created_at": "2026-10-20", "db": "2026-10-31"},
    ],
    CLI: [
        {"run_id": "cli_nov", "source_table_fqn": CLI, "total_rows": 200, "created_at": "2026-11-21", "db": "2026-11-30"},
    ],
}

# Regra "a" reprova 250 linhas: score por linha daria 75%, o índice não.
METRICS = {
    "ops_nov": [{"check_name": "a", "error_count": 250}, {"check_name": "b", "error_count": 0}],
    "ops_out": [{"check_name": "a", "error_count": 10}, {"check_name": "b", "error_count": 0}],
    "cli_nov": [{"check_name": "c", "error_count": 0}],
}
DIMS = {"a": 8, "b": 2, "c": 6}


class _Index:
    def get(self, table_fqn, check_name):
        return {"dimensao_r18": str(DIMS[check_name])} if check_name in DIMS else None


def _meta_for(check_name, table_fqn=None, user_metadata=None):
    return {"dimension_r18": int(user_metadata["dimensao_r18"])}


def _tdb(run, rows, per):
    return TableDataBase(table_fqn=run["source_table_fqn"], data_base=run["db"], origin="ledger",
                         run_id=run["run_id"], run_started_at=run["created_at"])


async def _metrics_query(sql, params, cache_ns=None):
    return [{"run_id": rid, "check_metrics_json": json.dumps(cm)} for rid, cm in METRICS.items() if f"'{rid}'" in sql]


async def _published(pred, params):
    return RUNS


async def _empty(*a, **k):
    return {}


async def _per():
    return lambda t: "mensal"


async def _scope(col):
    return "1=1", {}


async def _rules():
    return _Index()


class TrendMatchesIndexTest(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(data_base, "_published_runs", _published),
            patch.object(data_base, "load_ledger", _empty),
            patch.object(data_base, "periodicidade_of_table", _per),
            patch.object(data_base, "_table_data_base", _tdb),
            patch.object(compliance, "execute_query", _metrics_query),
            patch.object(compliance, "meta_for", _meta_for),
            patch.object(dash, "load_rule_index", _rules),
            patch.object(qual, "load_rule_index", _rules),
            patch.object(dash, "scope_table_clause", _scope),
            patch.object(qual, "scope_table_clause", _scope),
            patch.object(qual, "USE_MOCK", False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _index(self, month):
        return asyncio.run(dash._build_kpis_from_dqx_studio(month)).compliance_score

    def _trend(self, month):
        return asyncio.run(qual.get_quality_trend(data_base=month, months=6, locale="pt"))["trend"]

    def test_selected_month_point_is_the_index(self):
        trend = self._trend("2026-11")
        self.assertEqual([p["month"] for p in trend], ["2026-10", "2026-11"])
        self.assertEqual(trend[-1]["score"], self._index("2026-11"))
        # 3 dimensões: 8 → 75%, 2 → 100%, 6 → 100% ⇒ 91,67 (e não 75% por linha).
        self.assertEqual(trend[-1]["score"], 91.67)
        self.assertEqual(trend[0]["score"], self._index("2026-10"))

    def test_latest_processing_point_is_the_index(self):
        trend = self._trend("")
        self.assertEqual(trend[-1]["month"], "2026-11")
        self.assertEqual(trend[-1]["score"], self._index(""))

    def test_months_after_the_selected_one_are_left_out(self):
        self.assertEqual([p["month"] for p in self._trend("2026-10")], ["2026-10"])


if __name__ == "__main__":
    unittest.main()
