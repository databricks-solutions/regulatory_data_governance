"""Tests for the rule↔CADOC↔dimension linking feature.

Covers the two behaviors that matter most:
  1. `resolve_meta` backward-compat — the 4 hard-coded rules resolve identically
     to `meta_for` when no link exists, and a link overrides the dimension.
  2. The linking router in mock mode — CRUD + dedup + the effective-check_name
     candidate flow that resurfaces a rule authored without an explicit `name`.
"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.backend import rc18_rule_meta as m


class RunCompletedAtTypeTest(unittest.TestCase):
    """Regression: `_fetch_studio_results` must return `run_completed_at` as a
    string. The databricks-sql connector returns `created_at` as a datetime in
    prod, and `ValidationResultsResponse.run_completed_at` is typed `str` — a
    raw datetime raised a 500 only on the 3040 path (which has a run)."""

    def test_response_accepts_string_not_datetime(self):
        from app.backend.models import ValidationResultsResponse, ValidationSummary, Pagination
        # A raw datetime must be rejected (documents the contract we rely on).
        with self.assertRaises(Exception):
            ValidationResultsResponse(
                data_base="2026-03", run_id="r", run_status="completed",
                run_completed_at=datetime(2026, 7, 22, tzinfo=timezone.utc),  # wrong type
                summary=ValidationSummary(total_rules=0, passed=0, failed=0, warnings=0, pass_rate_pct=0.0),
                results=[], pagination=Pagination(),
            )
        # An ISO string is accepted.
        ok = ValidationResultsResponse(
            data_base="2026-03", run_id="r", run_status="completed",
            run_completed_at=datetime(2026, 7, 22, tzinfo=timezone.utc).isoformat(),
            summary=ValidationSummary(total_rules=0, passed=0, failed=0, warnings=0, pass_rate_pct=0.0),
            results=[], pagination=Pagination(),
        )
        self.assertIsInstance(ok.run_completed_at, str)


class ResolveMetaTest(unittest.TestCase):
    HARD_CODED = [
        "autorzc_in_dominio",
        "porte_cli_in_dominio_por_tipo",
        "tp_ctrl_in_dominio",
        "dia_atraso_nao_negativo",
    ]

    def test_hardcoded_rules_unchanged_without_link(self):
        # No link maps → resolve_meta must equal meta_for byte-for-byte.
        for cn in self.HARD_CODED:
            a = m.meta_for(cn, table_fqn="rc18_catalog.silver.scr3040_clientes")
            b = m.resolve_meta(cn, table_fqn="rc18_catalog.silver.scr3040_clientes")
            self.assertEqual(a, b, cn)

    def test_link_by_pair_overrides_dimension(self):
        vp = {
            ("rc18_catalog.silver.scr3040_clientes", "parte_not_in_range"): {
                "dimensao_r18": 1, "documento": "3040",
                "critica_id": None, "nivel_verificacao": None, "descricao": "x",
            }
        }
        meta = m.resolve_meta(
            "parte_not_in_range",
            table_fqn="rc18_catalog.silver.scr3040_clientes",
            vinculos_by_pair=vp,
        )
        self.assertEqual(meta["dimension_r18"], 1)
        self.assertEqual(meta["dimension_name"], "Acessibilidade")
        self.assertEqual(meta["document"], "3040")

    def test_link_by_rule_id_fallback_for_unnamed_rule(self):
        # Definition without `name` → parsed check_name is empty; rule_id recovers it.
        vr = {
            "b77ca2c5f49a4b34": {
                "dimensao_r18": 1, "documento": "3040",
                "critica_id": "CAD_001", "nivel_verificacao": 2, "descricao": "y",
            }
        }
        meta = m.resolve_meta(
            "",
            table_fqn="rc18_catalog.silver.scr3040_clientes",
            vinculos_by_rule_id=vr,
            rule_id="b77ca2c5f49a4b34",
        )
        self.assertEqual(meta["dimension_r18"], 1)
        self.assertEqual(meta["critica_id"], "CAD_001")
        self.assertEqual(meta["nivel_verificacao"], 2)

    def test_invalid_dimension_falls_back_to_baseline(self):
        vp = {("t", "c"): {"dimensao_r18": 99, "documento": "", "critica_id": None,
                           "nivel_verificacao": None, "descricao": ""}}
        meta = m.resolve_meta("c", table_fqn="t", vinculos_by_pair=vp)
        self.assertEqual(meta["dimension_r18"], 0)
        self.assertEqual(meta["dimension_name"], "Outras")


class LinkingRouterMockTest(unittest.TestCase):
    def setUp(self):
        os.environ["USE_MOCK_BACKEND"] = "true"
        from fastapi.testclient import TestClient
        from app.backend import main
        # Reset the module-level mock link store between tests.
        from app.backend.routers import linking
        linking._MOCK_LINKS.clear()
        self.client = TestClient(main.app)

    def test_cadocs_seeded(self):
        r = self.client.get("/api/v1/linking/cadocs")
        self.assertEqual(r.status_code, 200)
        docs = {c["documento"] for c in r.json()["cadocs"]}
        self.assertEqual(docs, {"3040", "3050"})

    def test_link_create_dedup_and_surface(self):
        payload = {
            "check_name": "parte_not_in_range",
            "table_fqn": "rc18_catalog.silver.scr3040_clientes",
            "rule_id": "b77ca2c5f49a4b34",
            "dimensao_r18": 1,
        }
        r = self.client.post("/api/v1/linking/links", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["dimension_name"], "Acessibilidade")

        # Dedup → 409
        r2 = self.client.post("/api/v1/linking/links", json=payload)
        self.assertEqual(r2.status_code, 409)

        # Rule now shows current_link
        r3 = self.client.get("/api/v1/linking/rules", params={"linked": "true"})
        self.assertEqual(r3.status_code, 200)
        rules = r3.json()["rules"]
        self.assertTrue(any(x["current_link"] for x in rules))

    def test_dimension_out_of_range_rejected(self):
        r = self.client.post("/api/v1/linking/links", json={
            "check_name": "c", "table_fqn": "rc18_catalog.silver.scr3040_clientes", "dimensao_r18": 13,
        })
        self.assertEqual(r.status_code, 400)

    def test_table_fqn_injection_rejected_on_write(self):
        # A malicious / malformed table_fqn must be rejected at write time
        # (defense-in-depth against stored injection), not stored verbatim.
        for bad in [
            "x') UNION SELECT cpf_cnpj, nome_cliente, '' FROM rc18_catalog.silver.scr3040_clientes -- ",
            "other_catalog.silver.scr3040_clientes",       # wrong catalog
            "rc18_catalog.governance.regra_vinculos",       # non-browsable schema
            "rc18_catalog.silver.tab; DROP TABLE x",        # junk table name
            "rc18_catalog.silver",                           # not 3 parts
        ]:
            r = self.client.post("/api/v1/linking/links", json={
                "check_name": "c", "table_fqn": bad, "dimensao_r18": 1,
            })
            self.assertEqual(r.status_code, 400, f"esperado 400 para {bad!r}, veio {r.status_code}")
            r2 = self.client.post("/api/v1/linking/cadocs/3040/tables", json={"table_fqn": bad})
            self.assertEqual(r2.status_code, 400, f"associate esperava 400 para {bad!r}")

    def test_valid_table_fqn_accepted(self):
        r = self.client.post("/api/v1/linking/links", json={
            "check_name": "some_check", "table_fqn": "rc18_catalog.silver.scr3040_operacoes", "dimensao_r18": 2,
        })
        self.assertEqual(r.status_code, 201, r.text)


if __name__ == "__main__":
    unittest.main()
