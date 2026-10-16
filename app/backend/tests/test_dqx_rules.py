"""Testes do índice/escopo de regras DQX (`app/backend/dqx_rules.py`).

Protegem três coisas: `check_name` NÃO é único entre tabelas (homônimos
colidiam e trocavam a dimensão exibida), o escopo por deployment, e o recorte
das regras em vigor a partir dos runs.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.backend.dqx_rules import (
    PUBLISHED_RUN_FILTER,
    RuleIndex,
    build_index,
    check_name_of,
    load_executed_rules,
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


class LoadExecutedRulesTest(unittest.TestCase):
    """Regras em vigor = as que rodaram na última versão aprovada (contorno DQX #1575)."""

    def _run(self, rows, table_fqns=None):
        seen = {}

        async def fake_query(sql, params=None):
            seen["sql"], seen["params"] = sql, params
            return rows

        async def fake_load():
            return {}, {}

        with patch("app.backend.dqx_rules.execute_query_or_empty", fake_query), \
             patch("app.backend.dqx_rules.load_cadoc_tables", fake_load), \
             patch("app.backend.dqx_rules.CATALOG", "c"):
            out = asyncio.run(load_executed_rules(table_fqns))
        return out, seen

    def test_only_approved_runs_count(self):
        """Run de rascunho e preview ad-hoc não são evidência da versão aprovada."""
        _, seen = self._run([])
        self.assertIn(PUBLISHED_RUN_FILTER, seen["sql"])
        self.assertIn("run_mode'), 'published') = 'published'", PUBLISHED_RUN_FILTER)
        self.assertIn("<> 'preview'", PUBLISHED_RUN_FILTER)
        self.assertIn("status = 'SUCCESS'", PUBLISHED_RUN_FILTER)

    def test_unions_all_runs_of_the_latest_binding_version(self):
        """O "Run" manual pode escolher só algumas regras: o último run sozinho mostra um subconjunto."""
        _, seen = self._run([])
        self.assertIn("MAX(binding_version) OVER (PARTITION BY source_table_fqn)", seen["sql"])
        self.assertIn("binding_version = latest_version OR (latest_version IS NULL AND rn = 1)", seen["sql"])

    def test_default_scope_is_the_deployment(self):
        _, seen = self._run([])
        self.assertIn("source_table_fqn LIKE :rscope_prefix", seen["sql"])
        self.assertEqual(seen["params"], {"rscope_prefix": "c.%"})

    def test_explicit_tables_are_parameterized(self):
        _, seen = self._run([], ["c.silver.a", "c.silver.b"])
        self.assertIn("source_table_fqn IN (:et0,:et1)", seen["sql"])
        self.assertEqual(seen["params"], {"et0": "c.silver.a", "et1": "c.silver.b"})
        self.assertNotIn("c.silver.a", seen["sql"])

    def test_empty_table_list_skips_the_query(self):
        out, seen = self._run([{"table_fqn": "x", "checks": '{"name": "n"}'}], [])
        self.assertEqual(out, [])
        self.assertNotIn("sql", seen)

    def test_dedupes_by_table_and_name_keeping_the_most_recent(self):
        """Runs da mesma versão podem diferir em valor resolvido na hora."""
        rows = [  # já vêm por created_at DESC
            {"table_fqn": "c.s.a", "checks": '{"name": "n1", "user_metadata": {"pass_threshold": "90"}}'},
            {"table_fqn": "c.s.a", "checks": '{"name": "n1", "user_metadata": {"pass_threshold": "80"}}'},
            {"table_fqn": "c.s.b", "checks": '{"name": "n1"}'},
        ]
        out, _ = self._run(rows)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["checks"]["user_metadata"]["pass_threshold"], "90")
        self.assertEqual([r["table_fqn"] for r in out], ["c.s.a", "c.s.b"])

    def test_unnamed_checks_are_kept_apart(self):
        """Sem `name`, a chave é o próprio check — dois distintos não se fundem."""
        rows = [
            {"table_fqn": "c.s.a", "checks": '{"check": {"function": "is_not_null"}}'},
            {"table_fqn": "c.s.a", "checks": '{"check": {"function": "is_unique"}}'},
        ]
        out, _ = self._run(rows)
        self.assertEqual(len(out), 2)

    def test_rows_feed_the_index(self):
        rows = [{"table_fqn": "c.s.a", "checks": '{"name": "n1", "user_metadata": {"dimensao_r18": "6"}}'}]
        out, _ = self._run(rows)
        self.assertEqual(build_index(out).get("c.s.a", "n1"), {"dimensao_r18": "6"})


if __name__ == "__main__":
    unittest.main()
