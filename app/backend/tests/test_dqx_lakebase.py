"""Testes do cliente Lakebase (`app/backend/dqx_lakebase.py`).

Só o que é testável sem Postgres: montagem de identificadores (`check` é palavra
reservada — sem aspas o SELECT quebra em runtime), a sentinela de "desligado", a
classificação da sonda e a degradação para vazio.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.backend import dqx_lakebase


class IdentifierQuotingTest(unittest.TestCase):
    def test_check_column_is_double_quoted(self):
        self.assertEqual(dqx_lakebase.CHECK_COLUMN, '"check"')

    def test_rules_table_is_schema_qualified_and_quoted(self):
        with patch.object(dqx_lakebase, "LAKEBASE_SCHEMA", "dqx_studio"), \
             patch.object(dqx_lakebase, "RULES_TABLE", "dq_quality_rules"):
            self.assertEqual(dqx_lakebase.rules_table(), '"dqx_studio"."dq_quality_rules"')

    def test_embedded_quote_is_escaped(self):
        with patch.object(dqx_lakebase, "LAKEBASE_SCHEMA", 'we"ird'), \
             patch.object(dqx_lakebase, "RULES_TABLE", "t"):
            self.assertEqual(dqx_lakebase.rules_table(), '"we""ird"."t"')

    def test_only_approved_counts_as_active(self):
        """A Studio removeu `active` do enum: `IN ('active','approved')` tinha ramo morto."""
        self.assertEqual(dqx_lakebase.ACTIVE_STATUS, "approved")


class IsConfiguredTest(unittest.TestCase):
    def test_real_endpoint_is_configured(self):
        with patch.object(
            dqx_lakebase, "LAKEBASE_ENDPOINT",
            "projects/dqx-studio-db/branches/dqx/endpoints/primary",
        ):
            self.assertTrue(dqx_lakebase.is_configured())

    def test_sentinels_and_blank_are_not_configured(self):
        for value in ("", "__unset__", "-"):
            with self.subTest(value=value):
                with patch.object(dqx_lakebase, "LAKEBASE_ENDPOINT", value):
                    self.assertFalse(dqx_lakebase.is_configured())


class ProbeRulesAccessTest(unittest.TestCase):
    """A prescrição do diagnóstico depende dessa classificação."""

    def test_not_configured_short_circuits(self):
        with patch.object(dqx_lakebase, "LAKEBASE_ENDPOINT", "__unset__"):
            state, _ = asyncio.run(dqx_lakebase.probe_rules_access())
        self.assertEqual(state, dqx_lakebase.PROBE_NOT_CONFIGURED)

    def test_missing_driver_is_error_not_connect_failure(self):
        """`psycopg` ausente = imagem quebrada, não role faltando.

        Regressão: como `connect_failed`, prescrevia "bundle deploy".
        """
        async def boom():
            raise ImportError("No module named 'psycopg_pool'")

        with patch.object(
            dqx_lakebase, "LAKEBASE_ENDPOINT", "projects/p/branches/b/endpoints/primary"
        ), patch.object(dqx_lakebase, "_ensure_pool", boom):
            state, detail = asyncio.run(dqx_lakebase.probe_rules_access())

        self.assertEqual(state, dqx_lakebase.PROBE_ERROR)
        self.assertIn("psycopg_pool", detail)

    def test_connection_failure_is_connect_failed(self):
        async def boom():
            raise RuntimeError("role \"sp-abc\" does not exist")

        with patch.object(
            dqx_lakebase, "LAKEBASE_ENDPOINT", "projects/p/branches/b/endpoints/primary"
        ), patch.object(dqx_lakebase, "_ensure_pool", boom):
            state, detail = asyncio.run(dqx_lakebase.probe_rules_access())

        self.assertEqual(state, dqx_lakebase.PROBE_CONNECT_FAILED)
        self.assertIn("does not exist", detail)


class QueryOrEmptyTest(unittest.TestCase):
    def test_returns_empty_when_not_configured_without_touching_the_pool(self):
        calls = []

        async def fake_query(sql, params=None):
            calls.append(sql)
            return [{"rule_id": "r1"}]

        with patch.object(dqx_lakebase, "LAKEBASE_ENDPOINT", "__unset__"), \
             patch.object(dqx_lakebase, "query", fake_query):
            rows = asyncio.run(dqx_lakebase.query_or_empty("SELECT 1"))

        self.assertEqual(rows, [])
        self.assertEqual(calls, [], "não deve tentar conectar quando desconfigurado")

    def test_connection_failure_degrades_to_empty(self):
        async def boom(sql, params=None):
            raise RuntimeError("permission denied for table dq_quality_rules")

        with patch.object(
            dqx_lakebase, "LAKEBASE_ENDPOINT",
            "projects/p/branches/b/endpoints/primary",
        ), patch.object(dqx_lakebase, "query", boom):
            rows = asyncio.run(dqx_lakebase.query_or_empty("SELECT 1"))

        self.assertEqual(rows, [])

    def test_successful_query_passes_rows_through(self):
        async def fake_query(sql, params=None):
            return [{"rule_id": "r1", "checks": {"name": "n1"}}]

        with patch.object(
            dqx_lakebase, "LAKEBASE_ENDPOINT",
            "projects/p/branches/b/endpoints/primary",
        ), patch.object(dqx_lakebase, "query", fake_query):
            rows = asyncio.run(dqx_lakebase.query_or_empty("SELECT 1"))

        self.assertEqual(rows, [{"rule_id": "r1", "checks": {"name": "n1"}}])


if __name__ == "__main__":
    unittest.main()
