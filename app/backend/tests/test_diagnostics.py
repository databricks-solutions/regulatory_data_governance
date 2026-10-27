"""Testes do diagnóstico (`app/backend/diagnostics.py`).

Classificação errada = prescrição errada, pior que não diagnosticar. Cobre a
cadeia: URL da Studio · leitura dos runs (GRANT de UC preenchido, ou falha sem
prescrição) · há regra executada no escopo · histórico de data-base presente e
em dia.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.backend import diagnostics as diag


def _run(coro):
    return asyncio.run(coro)


def _by_id(report):
    return {c.id: c for c in report.checks}


class ReportTest(unittest.TestCase):
    """Monta o relatório inteiro e checa a prescrição."""

    def _report(self, *, rules_count=7, delta_error=None, studio_url="https://dqx.example.com",
                ledger=None, history=None, ledger_error=None):
        async def fake_identity():
            return "00000000-1111-2222-3333-444444444444"

        async def fake_execute(sql, params=None):
            if delta_error:
                raise RuntimeError(delta_error)
            if sql.startswith("DESCRIBE HISTORY"):
                return history or []
            return []

        async def fake_cadoc_tables():
            return {"3040": ["c.s.a"]}, {"c.s.a": "3040"}

        async def fake_ledger(tables, strict=False):
            if ledger_error:
                raise RuntimeError(ledger_error)
            return {"c.s.a": [{"last_seen_version": 3}]} if ledger is None else ledger

        async def fake_rules():
            return [{"table_fqn": "c.s.a", "checks": {"name": f"n{i}"}} for i in range(rules_count)]

        with patch.object(diag, "USE_MOCK", False), \
             patch.object(diag, "_identity", fake_identity), \
             patch.object(diag, "execute_query", fake_execute), \
             patch.object(diag, "load_executed_rules", fake_rules), \
             patch.object(diag, "load_cadoc_tables", fake_cadoc_tables), \
             patch.object(diag, "load_ledger", fake_ledger), \
             patch.object(diag, "dqx_studio_base_url", lambda: studio_url):
            return _run(diag.run_prereq_checks())

    def test_access_ok_with_rules_is_all_clear(self):
        report = self._report(rules_count=7)
        self.assertEqual(report.state, diag.PASSED)
        self.assertEqual(_by_id(report)[diag.RULES_EXECUTED].params["count"], "7")

    def test_no_lakebase_check_is_reported(self):
        """O RC18 não lê mais o Lakebase: prescrever GRANT lá seria trabalho à toa."""
        ids = [c.id for c in self._report().checks]
        self.assertEqual(
            ids, [diag.STUDIO_URL, diag.DELTA_RUNS_SELECT, diag.RULES_EXECUTED, diag.DATA_BASE_HISTORY],
        )

    def test_missing_history_points_at_end_to_end(self):
        """Depois do upgrade, até o pipeline rodar, não há histórico."""
        c = _by_id(self._report(ledger={}))[diag.DATA_BASE_HISTORY]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation, "databricks bundle run rc18_end_to_end")

    def test_ledger_without_select_prescribes_the_grant(self):
        """Quem rodou só o job gold tem a tabela, mas não o GRANT do app."""
        c = _by_id(self._report(ledger_error="[INSUFFICIENT_PERMISSIONS] SELECT on data_base_ledger"))[
            diag.DATA_BASE_HISTORY_GRANT]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertIn("GRANT SELECT ON TABLE", c.remediation)
        self.assertIn("00000000-1111-2222-3333-444444444444", c.remediation)

    def test_ledger_unexpected_error_prescribes_nothing(self):
        c = _by_id(self._report(ledger_error="Connection reset by peer"))[diag.DATA_BASE_HISTORY]
        self.assertEqual(c.state, diag.FAILED)
        self.assertIsNone(c.remediation)

    def test_table_rewritten_outside_gold_flags_lagging_history(self):
        """Versão com dado mais nova que a última vista = silver regravada fora do job."""
        history = [{"version": 5, "operation": "SET TBLPROPERTIES"},
                   {"version": 4, "operation": "CREATE OR REPLACE TABLE AS SELECT"}]
        c = _by_id(self._report(history=history))[diag.DATA_BASE_HISTORY_LAG]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.params["tables"], "s.a")
        self.assertEqual(c.remediation, "databricks bundle run gold")

    def test_non_data_operations_do_not_flag_lag(self):
        """OPTIMIZE/SET TBLPROPERTIES não mudam dado: não atrasam o histórico."""
        history = [{"version": 5, "operation": "OPTIMIZE"},
                   {"version": 3, "operation": "CREATE OR REPLACE TABLE AS SELECT"}]
        c = _by_id(self._report(history=history))[diag.DATA_BASE_HISTORY]
        self.assertEqual(c.state, diag.PASSED)

    def test_access_ok_without_rules_points_at_publish_and_run(self):
        """Aprovar sem rodar não basta: a regra só aparece depois do run."""
        report = self._report(rules_count=0)
        c = _by_id(report)[diag.RULES_EXECUTED]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertIsNone(c.remediation)
        self.assertEqual(report.state, diag.ACTION_REQUIRED)
        # Não é permissão — o acesso passou.
        self.assertEqual(_by_id(report)[diag.DELTA_RUNS_SELECT].state, diag.PASSED)

    def test_delta_permission_failure_prescribes_the_grant(self):
        report = self._report(delta_error="INSUFFICIENT_PERMISSIONS: SELECT on table dq_validation_runs")
        c = _by_id(report)[diag.DELTA_RUNS_SELECT]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation_kind, "sql")
        self.assertIn("GRANT SELECT ON TABLE", c.remediation)
        # O comando tem de vir com a identidade REAL — é o ponto do módulo.
        self.assertIn("00000000-1111-2222-3333-444444444444", c.remediation)

    def test_delta_permission_failure_does_not_also_blame_missing_rules(self):
        """Sem acesso aos runs não se sabe se há regra; prescrever as duas confunde."""
        report = self._report(delta_error="PERMISSION_DENIED: dq_validation_runs")
        self.assertEqual(_by_id(report)[diag.RULES_EXECUTED].state, diag.SKIPPED)

    def test_delta_non_permission_failure_prescribes_nothing(self):
        """Warehouse indisponível não é falta de permissão.

        Regressão do smoke test: MALFORMED_REQUEST prescrevia um GRANT.
        """
        report = self._report(
            delta_error="Error during request to server: MALFORMED_REQUEST: Path /sql/1.0/warehouses/ must match"
        )
        c = _by_id(report)[diag.DELTA_RUNS_SELECT]
        self.assertEqual(c.state, diag.FAILED)
        self.assertIsNone(c.remediation)
        self.assertIn("MALFORMED_REQUEST", c.detail)
        self.assertEqual(report.state, diag.FAILED)

    def test_missing_studio_url_prescribes_the_target_variable(self):
        report = self._report(studio_url="")
        c = _by_id(report)[diag.STUDIO_URL]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation_kind, "yaml")

    def test_mock_mode_reports_no_action(self):
        # Devloop não tem workspace; alarme aqui seria ruído.
        with patch.object(diag, "USE_MOCK", True):
            report = _run(diag.run_prereq_checks())
        self.assertEqual(report.state, diag.PASSED)


if __name__ == "__main__":
    unittest.main()
