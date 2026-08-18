"""Tests for the Lineage graph's anchor selection.

`governance.cadoc_tabelas` is seeded with the vínculos of ALL CADOCs, so a
deployment that ran only one document's pipeline rendered nodes for tables that
don't exist — visually indistinguishable from materialized ones. The anchors are
now intersected with `information_schema.tables`.
"""

import asyncio
import unittest

from app.backend.routers.lineage import _cadoc_anchor_tables

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


if __name__ == "__main__":
    unittest.main()
