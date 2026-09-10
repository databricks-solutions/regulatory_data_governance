"""Testes do índice/escopo de regras DQX (`app/backend/dqx_rules.py`).

Protegem duas coisas: `check_name` NÃO é único em `dq_quality_rules` (homônimos
em tabelas diferentes colidiam e trocavam a dimensão exibida), e o predicado
serve duas engines — marcador errado não é erro de sintaxe, o predicado só nunca
casa, zerando as telas em silêncio.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.backend.dqx_rules import (
    RuleIndex,
    build_index,
    check_name_of,
    parse_check_defs,
    scope_clause,
)


def _check(name, dim, **extra):
    return {"name": name, "user_metadata": {"dimensao_r18": dim}, **extra}


class ParseCheckDefsTest(unittest.TestCase):
    def test_single_object_is_wrapped(self):
        self.assertEqual(parse_check_defs('{"name": "a"}'), [{"name": "a"}])

    def test_legacy_array_is_preserved(self):
        self.assertEqual(
            parse_check_defs('[{"name": "a"}, {"name": "b"}]'),
            [{"name": "a"}, {"name": "b"}],
        )

    def test_already_parsed_dict_is_accepted(self):
        self.assertEqual(parse_check_defs({"name": "a"}), [{"name": "a"}])

    def test_invalid_json_degrades_to_empty(self):
        # Uma linha corrompida não pode derrubar a tela inteira.
        self.assertEqual(parse_check_defs("{not json"), [])

    def test_none_is_empty(self):
        self.assertEqual(parse_check_defs(None), [])

    def test_non_dict_items_are_dropped(self):
        self.assertEqual(parse_check_defs('["x", {"name": "a"}]'), [{"name": "a"}])


class CheckNameOfTest(unittest.TestCase):
    def test_top_level_name_wins(self):
        chk = {"name": "explicit", "check": {"arguments": {"name": "inner"}}}
        self.assertEqual(check_name_of(chk), "explicit")

    def test_falls_back_to_arguments_name(self):
        chk = {"check": {"arguments": {"name": "inner"}}}
        self.assertEqual(check_name_of(chk), "inner")

    def test_missing_name_is_none(self):
        self.assertIsNone(check_name_of({"check": {"function": "is_not_null"}}))

    def test_non_dict_is_none(self):
        self.assertIsNone(check_name_of("nope"))


class RuleIndexTest(unittest.TestCase):
    def test_same_check_name_on_two_tables_does_not_collide(self):
        """O bug que motivou o módulo: homônimos em tabelas diferentes."""
        idx = RuleIndex()
        idx.add("cat.silver.a", "saldo_informado", {"dim": "6"})
        idx.add("cat.silver.b", "saldo_informado", {"dim": "2"})

        self.assertEqual(idx.get("cat.silver.a", "saldo_informado"), {"dim": "6"})
        self.assertEqual(idx.get("cat.silver.b", "saldo_informado"), {"dim": "2"})
        self.assertEqual(len(idx), 2)

    def test_name_fallback_when_table_differs(self):
        """`source_table_fqn` (runs) e `table_fqn` (regras) podem divergir.

        Nesse caso o lookup degrada para o nome em vez de zerar a tela.
        """
        idx = RuleIndex()
        idx.add("cat.silver.a", "cnpj_valido", {"dim": "9"})
        self.assertEqual(idx.get("outro.schema.z", "cnpj_valido"), {"dim": "9"})

    def test_unknown_name_is_none(self):
        idx = RuleIndex()
        idx.add("cat.silver.a", "x", {"dim": "1"})
        self.assertIsNone(idx.get("cat.silver.a", "inexistente"))

    def test_pair_wins_over_name_fallback(self):
        idx = RuleIndex()
        idx.add("cat.silver.a", "dup", {"dim": "1"})
        idx.add("cat.silver.b", "dup", {"dim": "8"})
        # Par exato tem precedência sobre o primeiro registrado por nome.
        self.assertEqual(idx.get("cat.silver.b", "dup"), {"dim": "8"})

    def test_name_fallback_keeps_first_occurrence(self):
        idx = RuleIndex()
        idx.add("cat.silver.a", "dup", {"dim": "1"})
        idx.add("cat.silver.b", "dup", {"dim": "8"})
        # Ambíguo por definição: a primeira vence (a última NÃO sobrescreve,
        # que era exatamente o comportamento silencioso anterior).
        self.assertEqual(idx.get("sem.par.conhecido", "dup"), {"dim": "1"})

    def test_has_matches_get(self):
        idx = RuleIndex()
        idx.add("cat.silver.a", "x", {})
        self.assertTrue(idx.has("cat.silver.a", "x"))
        self.assertFalse(idx.has("cat.silver.a", "y"))

    def test_empty_metadata_is_not_confused_with_missing(self):
        """`{}` é um metadado válido (regra sem tag) e difere de ausente."""
        idx = RuleIndex()
        idx.add("cat.silver.a", "sem_tag", {})
        self.assertIsNotNone(idx.get("cat.silver.a", "sem_tag"))
        self.assertTrue(idx.has("cat.silver.a", "sem_tag"))


class BuildIndexTest(unittest.TestCase):
    def test_indexes_rows_by_pair(self):
        rows = [
            {"table_fqn": "cat.silver.a", "checks": '{"name": "n1", "user_metadata": {"dimensao_r18": "6"}}'},
            {"table_fqn": "cat.silver.b", "checks": '{"name": "n1", "user_metadata": {"dimensao_r18": "2"}}'},
        ]
        idx = build_index(rows)
        self.assertEqual(idx.get("cat.silver.a", "n1"), {"dimensao_r18": "6"})
        self.assertEqual(idx.get("cat.silver.b", "n1"), {"dimensao_r18": "2"})

    def test_rule_without_name_is_skipped(self):
        rows = [{"table_fqn": "cat.silver.a", "checks": '{"check": {"function": "is_not_null"}}'}]
        self.assertEqual(len(build_index(rows)), 0)

    def test_custom_value_of_receives_row_and_check(self):
        rows = [{"rule_id": "r1", "table_fqn": "cat.silver.a", "checks": '{"name": "n1"}'}]
        idx = build_index(rows, value_of=lambda row, chk: {**chk, "rule_id": row.get("rule_id")})
        self.assertEqual(idx.get("cat.silver.a", "n1"), {"name": "n1", "rule_id": "r1"})

    def test_missing_user_metadata_defaults_to_empty_dict(self):
        rows = [{"table_fqn": "cat.silver.a", "checks": '{"name": "n1"}'}]
        self.assertEqual(build_index(rows).get("cat.silver.a", "n1"), {})


class ScopeClauseTest(unittest.TestCase):
    """O predicado que impede regras de outro deployment de entrar nas telas."""

    def _run(self, tables_by_doc, **kwargs):
        async def fake_load_cadoc_tables():
            return tables_by_doc, {}

        with patch("app.backend.dqx_rules.load_cadoc_tables", fake_load_cadoc_tables), \
             patch("app.backend.dqx_rules.CATALOG", "meu_catalog"):
            return asyncio.run(scope_clause(**kwargs))

    def test_falls_back_to_catalog_prefix_when_no_registered_tables(self):
        pred, params = self._run({})
        self.assertEqual(pred, "table_fqn LIKE :rscope_prefix")
        self.assertEqual(params, {"rscope_prefix": "meu_catalog.%"})

    def test_registered_tables_are_unioned_and_parameterized(self):
        pred, params = self._run({"3040": ["outro_catalog.silver.x"]})
        self.assertEqual(
            pred,
            "(table_fqn LIKE :rscope_prefix OR table_fqn IN (:rscope0))",
        )
        self.assertEqual(params["rscope0"], "outro_catalog.silver.x")
        # Nunca interpolar FQN direto no SQL.
        self.assertNotIn("outro_catalog.silver.x", pred)

    def test_registered_tables_are_deduped_and_sorted(self):
        pred, params = self._run({"3040": ["c.s.b", "c.s.a"], "3050": ["c.s.a"]})
        self.assertEqual(params["rscope0"], "c.s.a")
        self.assertEqual(params["rscope1"], "c.s.b")
        self.assertNotIn("rscope2", params)

    def test_column_and_prefix_are_configurable(self):
        async def fake_load():
            return {}, {}

        with patch("app.backend.dqx_rules.load_cadoc_tables", fake_load), \
             patch("app.backend.dqx_rules.CATALOG", "c"):
            pred, params = asyncio.run(scope_clause("source_table_fqn", "sc"))
        self.assertEqual(pred, "source_table_fqn LIKE :sc_prefix")
        self.assertIn("sc_prefix", params)

    # ── paramstyle: o MESMO predicado serve Lakebase (psycopg) e Databricks SQL.
    def test_pyformat_marker_for_lakebase(self):
        pred, params = self._run({}, paramstyle="pyformat")
        self.assertEqual(pred, "table_fqn LIKE %(rscope_prefix)s")
        self.assertEqual(params, {"rscope_prefix": "meu_catalog.%"})

    def test_pyformat_marker_in_the_in_list(self):
        pred, params = self._run(
            {"3040": ["outro_catalog.silver.x"]}, paramstyle="pyformat"
        )
        self.assertEqual(
            pred,
            "(table_fqn LIKE %(rscope_prefix)s OR table_fqn IN (%(rscope0)s))",
        )
        self.assertEqual(params["rscope0"], "outro_catalog.silver.x")
        self.assertNotIn("outro_catalog.silver.x", pred)

    def test_param_names_are_identical_across_paramstyles(self):
        """Só o marcador muda: permite reaproveitar o dict de params."""
        tables = {"3040": ["c.s.a", "c.s.b"]}
        _, named = self._run(tables)
        _, pyformat = self._run(tables, paramstyle="pyformat")
        self.assertEqual(named, pyformat)

    def test_unknown_paramstyle_fails_loudly(self):
        # Erro explícito > predicado que nunca casa.
        with self.assertRaises(ValueError):
            self._run({}, paramstyle="qmark")


if __name__ == "__main__":
    unittest.main()
