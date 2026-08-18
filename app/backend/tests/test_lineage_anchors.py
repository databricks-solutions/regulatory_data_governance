"""Tests for how the Lineage graph picks and labels its nodes.

  1. Anchor selection — `governance.cadoc_tabelas` is seeded with the vínculos of
     ALL CADOCs, so a deployment that ran only one document's pipeline rendered
     nodes for tables that don't exist, visually indistinguishable from
     materialized ones. Anchors are intersected with `information_schema.tables`.
  2. External-object labels — the deployment prefix is identical on every node,
     so it only crowds the box; it is stripped from the label but kept as the id.
"""

import asyncio
import unittest

from app.backend.routers.lineage import _cadoc_anchor_tables, _ext_label

CAT = "rc18_catalog_02"

# The 12 seeded vínculos (setup_reference_tables.py) …
DECLARED = [
    f"{CAT}.silver.scr3040_operacoes",
    f"{CAT}.silver.scr3040_clientes",
    f"{CAT}.silver.scr3040_garantias",
    f"{CAT}.silver.scr3040_vencimentos",
    f"{CAT}.silver.scr3040_cont_4966",
    f"{CAT}.silver.scr3050",
    f"{CAT}.silver.scr4010_saldos",
    f"{CAT}.silver.scr4016_saldos",
    f"{CAT}.silver.scr2011_contas",
    f"{CAT}.silver.scr2011_detalhamentos",
    f"{CAT}.silver.scr2011_parametros",
    f"{CAT}.gold.criticas_ddr_2011",
]
# … versus what a DDR-only deployment actually materializes.
DDR_ONLY = [
    f"{CAT}.bronze.raw_2011_doc",
    f"{CAT}.silver.scr2011_contas",
    f"{CAT}.silver.scr2011_detalhamentos",
    f"{CAT}.silver.scr2011_parametros",
    f"{CAT}.gold.criticas_ddr_2011",
    f"{CAT}.gold.posicao_2011",
    f"{CAT}.gold.processing_state",
]


def _stub(declared, existing=None, existing_raises=False):
    """execute_query stub that answers by inspecting the SQL."""
    async def run(sql, params=None):
        if "cadoc_tabelas" in sql:
            return [{"table_fqn": f} for f in declared]
        if "information_schema.tables" in sql:
            if existing_raises:
                raise RuntimeError("INSUFFICIENT_PERMISSIONS")
            return [{"fqn": f.lower()} for f in (existing or [])]
        raise AssertionError(f"unexpected query: {sql}")
    return run


class CadocAnchorTablesTest(unittest.TestCase):
    def _anchors(self, *a, **kw):
        return asyncio.run(_cadoc_anchor_tables(CAT, _stub(*a, **kw)))

    def test_hides_declared_but_unmaterialized(self):
        anchors = self._anchors(DECLARED, DDR_ONLY)
        self.assertEqual(
            sorted(anchors),
            sorted([
                f"{CAT}.gold.criticas_ddr_2011",
                f"{CAT}.silver.scr2011_contas",
                f"{CAT}.silver.scr2011_detalhamentos",
                f"{CAT}.silver.scr2011_parametros",
            ]),
        )

    def test_noop_when_everything_exists(self):
        """A full deployment must be unaffected by the filter."""
        self.assertEqual(sorted(self._anchors(DECLARED, DECLARED)), sorted(DECLARED))

    def test_existing_tables_outside_the_vinculos_are_not_anchors(self):
        """`posicao_2011`/`raw_2011_doc` exist but aren't declared — they must
        still come from the 1-hop lineage expansion, not from here."""
        anchors = self._anchors(DECLARED, DDR_ONLY)
        self.assertNotIn(f"{CAT}.gold.posicao_2011", anchors)
        self.assertNotIn(f"{CAT}.bronze.raw_2011_doc", anchors)

    def test_empty_declared_stays_empty(self):
        self.assertEqual(self._anchors([], DDR_ONLY), [])

    def test_keeps_declared_when_filter_would_wipe_everything(self):
        """A blank graph is the worse failure: if information_schema shows none of
        the declared tables, that's likelier a privilege/metadata issue than every
        table being gone, so fall back to the declared list."""
        self.assertEqual(sorted(self._anchors(DECLARED, [])), sorted(DECLARED))

    def test_keeps_declared_when_information_schema_errors(self):
        self.assertEqual(
            sorted(self._anchors(DECLARED, existing_raises=True)), sorted(DECLARED)
        )

    def test_match_is_case_insensitive(self):
        anchors = self._anchors(
            [f"{CAT}.Silver.SCR2011_Contas"], [f"{CAT}.silver.scr2011_contas"]
        )
        self.assertEqual(anchors, [f"{CAT}.Silver.SCR2011_Contas"])


class ExtLabelTest(unittest.TestCase):
    """Prefix comes from the catalog (`rc18_catalog` → `rc18_`) in this env."""

    def test_strips_the_deployment_prefix(self):
        self.assertEqual(_ext_label("rc18_ddr2011_pgm_iexp0174"), "ddr2011_pgm_iexp0174")

    def test_leaves_unprefixed_names_alone(self):
        """Objects the customer created without the prefix must not be mangled."""
        self.assertEqual(_ext_label("mainframe_batch_ddr"), "mainframe_batch_ddr")

    def test_name_equal_to_the_prefix_is_not_emptied(self):
        self.assertEqual(_ext_label("rc18_"), "rc18_")

    def test_strips_only_the_leading_occurrence(self):
        self.assertEqual(_ext_label("rc18_db2_rc18_hist"), "db2_rc18_hist")


if __name__ == "__main__":
    unittest.main()
