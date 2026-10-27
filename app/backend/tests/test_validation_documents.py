"""Testes do seletor de documentos das Críticas (`GET /validations/documents`).

Só entram CADOCs com execução aprovada na DQX; cada um com a data-base do último
run de cada tabela. Cadastrados sem execução vêm em `unprocessed`.
"""

import asyncio
import json
import unittest
from unittest.mock import patch

from app.backend.routers import validation as val

# O router importa `models` como módulo de topo (app/backend no sys.path): a classe
# tem de ser a mesma que ele valida, não a de `app.backend.models`.
from models import TableDataBase  # noqa: E402

CLI = "c.silver.scr3040_clientes"
OPS = "c.silver.scr3040_operacoes"
DDR = "c.silver.scr2011_contas"


def _run(run_id, table, created):
    return {"run_id": run_id, "source_table_fqn": table, "total_rows": 10, "invalid_rows": 0,
            "created_at": created, "started_at": created}


class _Index:
    """RuleIndex mínimo: toda regra existe e é bloqueante."""

    def get(self, table_fqn, check_name):
        return {"criticality": "error", "user_metadata": {}, "check": {"function": "sql_expression"}}


def _metrics(run_id, failing):
    checks = [{"check_name": "a", "error_count": 3 if failing else 0, "warning_count": 0},
              {"check_name": "b", "error_count": 0, "warning_count": 0}]
    return {"run_id": run_id, "check_metrics_json": json.dumps(checks)}


class DocumentsRouteTest(unittest.TestCase):
    def _call(self, data_bases, month=None):
        runs = [_run("r_cli", CLI, "2026-10-26T18:48:00"), _run("r_ops", OPS, "2026-10-06T12:44:00"),
                _run("r_ddr", DDR, "2026-10-27T07:30:00")]

        async def fake_tables():
            by_doc = {"3040": [CLI, OPS], "2011": [DDR], "4010": ["c.silver.scr4010_saldos"]}
            return by_doc, {t: d for d, ts in by_doc.items() for t in ts}

        async def fake_docs():
            return {
                "3040": {"documento": "3040", "nome": "SCR 3040", "grupo": "SCR", "periodicidade": "mensal"},
                "2011": {"documento": "2011", "nome": "DDR", "grupo": "Prudencial", "periodicidade": "diaria"},
                "4010": {"documento": "4010", "nome": "COSIF 4010", "grupo": "COSIF", "periodicidade": "mensal"},
            }

        async def fake_select(pred, params, m):
            # Com mês, só ficam as tabelas cuja data-base cai nele.
            tdb = {r["source_table_fqn"]: TableDataBase(
                table_fqn=r["source_table_fqn"], data_base=data_bases[r["source_table_fqn"]],
                origin="historico" if data_bases[r["source_table_fqn"]] else "desconhecida",
                run_id=r["run_id"]) for r in runs}
            keep = [r for r in runs if m is None or (tdb[r["source_table_fqn"]].data_base or "")[:7] == m]
            return val.RunSelection(
                runs=keep, tables={r["source_table_fqn"]: tdb[r["source_table_fqn"]] for r in keep},
                ever={r["source_table_fqn"] for r in runs},
            )

        async def fake_query(sql, params=None, **kw):
            return [_metrics("r_cli", True), _metrics("r_ops", False), _metrics("r_ddr", False)]

        async def fake_rules():
            return _Index()

        async def fake_vinculos():
            return {}, {}

        with patch.object(val, "USE_MOCK", False), \
             patch.object(val, "load_cadoc_tables", fake_tables), \
             patch.object(val, "load_cadoc_documents", fake_docs), \
             patch.object(val, "select_runs", fake_select), \
             patch.object(val, "execute_query", fake_query), \
             patch.object(val, "_load_active_rules", fake_rules), \
             patch.object(val, "load_vinculos", fake_vinculos):
            return asyncio.run(val.list_documents(data_base=month, locale="pt"))

    def test_only_processed_documents_with_their_data_base(self):
        resp = self._call({CLI: "2026-04-30", OPS: "2026-04-30", DDR: "2026-10-27"})
        by_doc = {d.documento: d for d in resp.documents}
        self.assertEqual(sorted(by_doc), ["2011", "3040"])
        self.assertEqual(by_doc["3040"].data_base, "2026-04-30")
        self.assertFalse(by_doc["3040"].mixed)
        self.assertEqual(by_doc["2011"].data_base, "2026-10-27")
        # 4010 está cadastrado mas nunca rodou: vai para o rodapé, não some.
        self.assertEqual([u.documento for u in resp.unprocessed], ["4010"])

    def test_failed_rules_match_the_results_page(self):
        doc = {d.documento: d for d in self._call({CLI: "2026-04-30", OPS: "2026-04-30", DDR: None}).documents}["3040"]
        self.assertEqual((doc.total_rules, doc.failed_rules), (4, 1))

    def test_tables_on_different_data_bases_are_flagged(self):
        """Uma tabela rodou hoje e a outra antes do histórico: o documento ganha o ⚠."""
        doc = {d.documento: d for d in self._call({CLI: "2026-04-30", OPS: None, DDR: None}).documents}["3040"]
        self.assertTrue(doc.mixed)
        self.assertEqual(doc.data_base, "2026-04-30")
        self.assertEqual(doc.last_run_at, "2026-10-26T18:48:00")

    def test_reference_month_keeps_documents_without_run_in_it_as_unprocessed(self):
        """Abril: o 3040 tem run; o DDR (outubro) teve execução, só não neste mês."""
        resp = self._call({CLI: "2026-04-30", OPS: "2026-04-30", DDR: "2026-10-27"}, month="2026-04")
        self.assertEqual([d.documento for d in resp.documents], ["3040"])
        unproc = {u.documento: u for u in resp.unprocessed}
        self.assertTrue(unproc["2011"].ever_processed)
        self.assertFalse(unproc["4010"].ever_processed)
        self.assertEqual(unproc["2011"].grupo, "Prudencial")

    def test_groups_sort_first_and_ungrouped_last(self):
        resp = self._call({CLI: "2026-04-30", OPS: "2026-04-30", DDR: "2026-10-27"})
        self.assertEqual([d.grupo for d in resp.documents], ["Prudencial", "SCR"])


class CadocPeriodicityTest(unittest.TestCase):
    def test_unknown_periodicity_is_rejected(self):
        from fastapi import HTTPException

        from app.backend.routers import linking

        with self.assertRaises(HTTPException) as ctx:
            linking._check_periodicidade("quinzenal")
        self.assertEqual(ctx.exception.status_code, 400)
        linking._check_periodicidade("diaria")
        linking._check_periodicidade(None)


if __name__ == "__main__":
    unittest.main()
