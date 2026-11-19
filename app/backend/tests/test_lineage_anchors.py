"""Tests for how the Lineage graph picks and labels its nodes.

  1. Anchor selection — `governance.cadoc_tabelas` is seeded with the vínculos of
     ALL CADOCs, so a deployment that ran only one document's pipeline rendered
     nodes for tables that don't exist, visually indistinguishable from
     materialized ones. Anchors are intersected with `information_schema.tables`.
  2. External-object labels — the deployment prefix is identical on every node,
     so it only crowds the box; it is stripped from the label but kept as the id.
  3. Vínculos in ANOTHER catalog ("Tabelas dos CADOCs") — existence is checked in
     that catalog's own information_schema, and their neighbors may live in any
     catalog. Checking only the RC18 catalog hid those tables from the graph.
"""

import asyncio
import unittest

from app.backend.models import LineageNode, LineageNodeMetadata
from app.backend.routers.lineage import (
    _cadoc_anchor_tables,
    _ext_label,
    _infer_foreign_layers,
    _is_relevant_uc_table,
    _uc_node,
)

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


def _stub(declared, existing=None, existing_raises=False, raising_catalogs=(), seen=None):
    """execute_query stub that answers by inspecting the SQL. `information_schema`
    answers only for the catalog it is queried in, like the real one."""
    async def run(sql, params=None):
        if "cadoc_tabelas" in sql:
            return [{"table_fqn": f} for f in declared]
        if "information_schema.tables" in sql:
            cat = sql.split("FROM `", 1)[1].split("`", 1)[0]
            if seen is not None:
                seen.append(cat)
            if existing_raises or cat in raising_catalogs:
                raise RuntimeError("INSUFFICIENT_PERMISSIONS")
            return [{"fqn": f.lower()} for f in (existing or []) if f.lower().startswith(cat + ".")]
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


EXT = "ext_catalog"
EXT_DOCS = [f"{EXT}.regulatorio.doc9999_operacoes", f"{EXT}.regulatorio.doc9999_contas"]


class ForeignCatalogAnchorsTest(unittest.TestCase):
    def _anchors(self, *a, **kw):
        return asyncio.run(_cadoc_anchor_tables(CAT, _stub(*a, **kw)))

    def test_foreign_table_is_checked_in_its_own_catalog(self):
        """The bug: checking only the RC18 catalog dropped every foreign vínculo
        as "not materialized" while the RC18 tables existed."""
        seen = []
        anchors = self._anchors(DECLARED + EXT_DOCS, DECLARED + EXT_DOCS, seen=seen)
        self.assertEqual(sorted(anchors), sorted(DECLARED + EXT_DOCS))
        self.assertEqual(sorted(seen), sorted([CAT, EXT]))

    def test_missing_foreign_table_is_hidden(self):
        anchors = self._anchors(DECLARED + EXT_DOCS, DECLARED + EXT_DOCS[:1])
        self.assertIn(EXT_DOCS[0], anchors)
        self.assertNotIn(EXT_DOCS[1], anchors)

    def test_fallback_is_per_catalog(self):
        """An unreadable foreign catalog keeps ITS declared tables without
        disabling the filter for the RC18 catalog."""
        anchors = self._anchors(DECLARED + EXT_DOCS, DDR_ONLY, raising_catalogs={EXT})
        for f in EXT_DOCS:
            self.assertIn(f, anchors)
        self.assertNotIn(f"{CAT}.silver.scr3050", anchors)

    def test_invalid_catalog_name_is_not_queried(self):
        seen = []
        anchors = self._anchors(["bad-cat.s.t"], [], seen=seen)
        self.assertEqual(anchors, ["bad-cat.s.t"])
        self.assertEqual(seen, [])


class RelevantNeighborTest(unittest.TestCase):
    OWN = f"{CAT}.silver.scr3040_operacoes"
    FOREIGN = EXT_DOCS[0]

    def test_own_anchor_keeps_only_own_catalog(self):
        self.assertTrue(_is_relevant_uc_table(f"{CAT}.bronze.raw_3040_doc", CAT, anchor=self.OWN))
        self.assertFalse(_is_relevant_uc_table(f"{EXT}.raw.x", CAT, anchor=self.OWN))

    def test_foreign_anchor_keeps_any_catalog(self):
        """The customer's medallion spans catalogs — e.g. upstream in a raw one."""
        self.assertTrue(_is_relevant_uc_table("ext_raw.cargas.doc9999", CAT, anchor=self.FOREIGN))
        self.assertTrue(_is_relevant_uc_table(f"{EXT}.regulatorio.x", CAT, anchor=self.FOREIGN))

    def test_noise_is_dropped_for_any_anchor(self):
        self.assertFalse(_is_relevant_uc_table("dqx.dqx_studio.dq_metrics", CAT, anchor=self.FOREIGN))
        self.assertFalse(_is_relevant_uc_table(f"{EXT}.tmp_tmp.x", CAT, anchor=self.FOREIGN))

    def test_case_insensitive(self):
        self.assertTrue(_is_relevant_uc_table(f"{CAT.upper()}.Bronze.Raw", CAT, anchor=self.OWN))


class InferForeignLayersTest(unittest.TestCase):
    def test_position_decides_for_unlayered_foreign_tables(self):
        up, anc, down = "ext_raw.cargas.a", EXT_DOCS[0], f"{EXT}.relatorios.b"
        own = f"{CAT}.governance.c"
        nodes = {f: _uc_node(f, CAT) for f in (up, anc, down, own)}
        _infer_foreign_layers(nodes, [anc], {up: {"upstream"}, down: {"downstream"}}, CAT)
        self.assertEqual(nodes[up].layer, "bronze")
        self.assertEqual(nodes[anc].layer, "silver")
        self.assertEqual(nodes[down].layer, "gold")
        self.assertEqual(nodes[own].layer, "unknown")  # RC18 catalog: untouched

    def test_schema_layer_wins(self):
        f = f"{EXT}.bronze_9999.a"
        nodes = {f: _uc_node(f, CAT)}
        _infer_foreign_layers(nodes, [], {f: {"downstream"}}, CAT)
        self.assertEqual(nodes[f].layer, "bronze")

    def test_external_objects_untouched(self):
        n = LineageNode(id="x", label="x", type="external_source", layer="unknown",
                        metadata=LineageNodeMetadata())
        _infer_foreign_layers({"x": n}, [], {"x": {"upstream"}}, CAT)
        self.assertEqual(n.layer, "unknown")


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
