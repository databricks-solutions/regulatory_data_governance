"""Testes do diagnóstico (`app/backend/diagnostics.py`).

Classificação errada = prescrição errada, pior que não diagnosticar. Cobre as
três bifurcações: conecta e lê (passed) · conecta e não lê (GRANT preenchido) ·
não conecta (aponta para o bundle).
"""

import asyncio
import unittest
from unittest.mock import patch

from app.backend import diagnostics as diag


def _run(coro):
    return asyncio.run(coro)


def _by_id(report):
    return {c.id: c for c in report.checks}


class GrantCommandTest(unittest.TestCase):
    def test_client_id_is_double_quoted(self):
        """O role é um UUID: sem aspas duplas o Postgres recusa."""
        with patch.object(diag.dqx_lakebase, "LAKEBASE_SCHEMA", "dqx_studio"), \
             patch.object(diag.dqx_lakebase, "RULES_TABLE", "dq_quality_rules"):
            cmd = diag._grant_command("00000000-1111-2222-3333-444444444444")
        self.assertIn('TO "00000000-1111-2222-3333-444444444444"', cmd)
        self.assertIn("GRANT USAGE ON SCHEMA dqx_studio", cmd)
        self.assertIn("GRANT SELECT ON TABLE dqx_studio.dq_quality_rules", cmd)

    def test_unknown_client_id_leaves_a_placeholder(self):
        # Placeholder visível > comando que parece pronto e concede a role vazio.
        cmd = diag._grant_command("")
        self.assertIn("<client-id-do-sp-do-app>", cmd)

    def test_psql_command_extracts_project_and_branch_by_name(self):
        with patch.object(
            diag.dqx_lakebase, "LAKEBASE_ENDPOINT",
            "projects/dqx-studio-db/branches/dqx/endpoints/primary",
        ), patch.object(diag.dqx_lakebase, "LAKEBASE_DATABASE", "databricks_postgres"):
            cmd = diag._psql_command()
        self.assertIn("--project dqx-studio-db", cmd)
        self.assertIn("--branch dqx", cmd)
        self.assertIn("-d databricks_postgres", cmd)

    def test_psql_command_degrades_on_unexpected_endpoint_shape(self):
        # Extrair por posição fixa daria comando errado com cara de certo.
        with patch.object(diag.dqx_lakebase, "LAKEBASE_ENDPOINT", "algo/inesperado"):
            cmd = diag._psql_command()
        self.assertIn("<projeto>", cmd)
        self.assertIn("<branch>", cmd)


class ReportTest(unittest.TestCase):
    """Monta o relatório inteiro e checa a prescrição."""

    def _report(self, probe, *, rules_count=7, delta_ok=True):
        async def fake_probe():
            return probe

        async def fake_identity():
            return "00000000-1111-2222-3333-444444444444"

        async def fake_query(sql, params=None):
            return [{"n": rules_count}]

        async def fake_execute(sql, params=None):
            if delta_ok:
                return []
            raise RuntimeError("INSUFFICIENT_PERMISSIONS: SELECT on table dq_validation_runs")

        async def fake_scope(**kwargs):
            return "table_fqn LIKE %(rscope_prefix)s", {"rscope_prefix": "rc18_catalog.%"}

        with patch.object(diag, "USE_MOCK", False), \
             patch.object(diag.dqx_lakebase, "probe_rules_access", fake_probe), \
             patch.object(diag.dqx_lakebase, "identity", fake_identity), \
             patch.object(diag.dqx_lakebase, "query", fake_query), \
             patch.object(diag.dqx_lakebase, "is_configured", lambda: True), \
             patch.object(diag, "execute_query", fake_execute), \
             patch.object(diag, "rule_scope_clause", fake_scope), \
             patch.object(diag, "dqx_studio_base_url", lambda: "https://dqx.example.com"):
            return _run(diag.run_prereq_checks())

    def test_permission_denied_prescribes_the_grant(self):
        report = self._report((diag.dqx_lakebase.PROBE_PERMISSION_DENIED, "permission denied for table"))
        c = _by_id(report)[diag.LAKEBASE_RULES_SELECT]

        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation_kind, "psql")
        # O comando tem de vir com a identidade REAL — é o ponto do módulo.
        self.assertIn("00000000-1111-2222-3333-444444444444", c.remediation)
        self.assertIn("GRANT SELECT", c.remediation)
        self.assertIn("psql", c.params)
        self.assertEqual(report.state, diag.ACTION_REQUIRED)

    def test_permission_denied_does_not_also_blame_missing_rules(self):
        """Sem acesso não se sabe se há regra; prescrever as duas confunde."""
        report = self._report((diag.dqx_lakebase.PROBE_PERMISSION_DENIED, ""))
        self.assertEqual(_by_id(report)[diag.RULES_MATERIALIZED].state, diag.SKIPPED)
        self.assertEqual(_by_id(report)[diag.LAKEBASE_CONNECTION].state, diag.PASSED)

    def test_connect_failure_points_at_the_bundle_not_the_grant(self):
        report = self._report((diag.dqx_lakebase.PROBE_CONNECT_FAILED, "role does not exist"))
        c = _by_id(report)[diag.LAKEBASE_CONNECTION]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation, "databricks bundle deploy")
        self.assertEqual(_by_id(report)[diag.LAKEBASE_RULES_SELECT].state, diag.SKIPPED)

    def test_unexpected_lakebase_error_prescribes_nothing(self):
        """Erro não diagnosticado não vem com comando ao lado.

        Regressão do smoke test: `psycopg` ausente prescrevia `bundle deploy`.
        """
        report = self._report((diag.dqx_lakebase.PROBE_ERROR, "No module named 'psycopg_pool'"))
        c = _by_id(report)[diag.LAKEBASE_CONNECTION]
        self.assertEqual(c.state, diag.FAILED)
        self.assertIsNone(c.remediation)
        self.assertIsNone(c.remediation_kind)
        self.assertEqual(report.state, diag.FAILED)

    def test_access_ok_with_rules_is_all_clear(self):
        report = self._report((diag.dqx_lakebase.PROBE_OK, ""), rules_count=7)
        self.assertEqual(report.state, diag.PASSED)
        self.assertEqual(_by_id(report)[diag.RULES_MATERIALIZED].params["count"], "7")

    def test_access_ok_without_rules_blames_materialization(self):
        """Pegadinha do fluxo novo: a regra fica no Registry."""
        report = self._report((diag.dqx_lakebase.PROBE_OK, ""), rules_count=0)
        c = _by_id(report)[diag.RULES_MATERIALIZED]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(report.state, diag.ACTION_REQUIRED)
        # Não é permissão — o acesso passou.
        self.assertEqual(_by_id(report)[diag.LAKEBASE_RULES_SELECT].state, diag.PASSED)

    def test_delta_permission_failure_is_reported_separately(self):
        """UC e Postgres falham e se corrigem em lugares diferentes."""
        report = self._report((diag.dqx_lakebase.PROBE_OK, ""), delta_ok=False)
        c = _by_id(report)[diag.DELTA_RUNS_SELECT]
        self.assertEqual(c.state, diag.ACTION_REQUIRED)
        self.assertEqual(c.remediation_kind, "sql")
        self.assertIn("GRANT SELECT ON TABLE", c.remediation)

    def test_delta_non_permission_failure_prescribes_nothing(self):
        """Warehouse indisponível não é falta de permissão.

        Regressão do smoke test: MALFORMED_REQUEST prescrevia um GRANT.
        """
        async def boom(sql, params=None):
            raise RuntimeError(
                "Error during request to server: MALFORMED_REQUEST: Path /sql/1.0/warehouses/ must match"
            )

        async def fake_probe():
            return (diag.dqx_lakebase.PROBE_OK, "")

        async def fake_identity():
            return "00000000-1111-2222-3333-444444444444"

        async def fake_query(sql, params=None):
            return [{"n": 7}]

        async def fake_scope(**kwargs):
            return "1=1", {}

        with patch.object(diag, "USE_MOCK", False), \
             patch.object(diag.dqx_lakebase, "probe_rules_access", fake_probe), \
             patch.object(diag.dqx_lakebase, "identity", fake_identity), \
             patch.object(diag.dqx_lakebase, "query", fake_query), \
             patch.object(diag.dqx_lakebase, "is_configured", lambda: True), \
             patch.object(diag, "execute_query", boom), \
             patch.object(diag, "rule_scope_clause", fake_scope), \
             patch.object(diag, "dqx_studio_base_url", lambda: "https://dqx.example.com"):
            report = _run(diag.run_prereq_checks())

        c = _by_id(report)[diag.DELTA_RUNS_SELECT]
        self.assertEqual(c.state, diag.FAILED)
        self.assertIsNone(c.remediation)
        self.assertIn("MALFORMED_REQUEST", c.detail)

    def test_mock_mode_reports_no_action(self):
        # Devloop não tem workspace; alarme aqui seria ruído.
        with patch.object(diag, "USE_MOCK", True):
            report = _run(diag.run_prereq_checks())
        self.assertEqual(report.state, diag.PASSED)


if __name__ == "__main__":
    unittest.main()
