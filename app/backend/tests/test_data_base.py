"""Testes de `app/backend/data_base.py` — a data-base que o último run avaliou.

Cenário-base: a silver do 3040 tinha 2026-03 desde 01/03 e ganhou 2026-04 em
05/04. Os horários são o início do run (a linha RUNNING), o que o filtro vê.
"""

import asyncio
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from app.backend import data_base as db_mod


def _ts(day, month=4, hour=12):
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


TABLE = "c.silver.scr3040_operacoes"

LEDGER = [
    {"table_fqn": TABLE, "data_base_month": "2026-03", "dt_base_max": "2026-03",
     "valid_from": _ts(1, 3), "valid_to": None},
    {"table_fqn": TABLE, "data_base_month": "2026-04", "dt_base_max": "2026-04",
     "valid_from": _ts(5), "valid_to": None},
]


class PeriodEndTest(unittest.TestCase):
    def test_monthly_documents_show_the_last_day(self):
        # 3040 grava 'AAAA-MM'; 4010/4016 gravam DATE no dia 1º.
        self.assertEqual(db_mod.period_end("2026-04", "mensal"), "2026-04-30")
        self.assertEqual(db_mod.period_end(date(2026, 4, 1), "mensal"), "2026-04-30")
        self.assertEqual(db_mod.period_end("2025-12-01", "semestral"), "2025-12-31")
        self.assertEqual(db_mod.period_end("2024-02", "mensal"), "2024-02-29")

    def test_daily_and_weekly_keep_the_day(self):
        self.assertEqual(db_mod.period_end("2026-10-27", "diaria"), "2026-10-27")
        self.assertEqual(db_mod.period_end("20261023", "semanal"), "2026-10-23")

    def test_without_periodicity_a_month_still_ends_the_month(self):
        self.assertEqual(db_mod.period_end("2026-03", None), "2026-03-31")
        self.assertEqual(db_mod.period_end("2026-03-31", None), "2026-03-31")

    def test_unrecognized_value_is_none(self):
        self.assertIsNone(db_mod.period_end("março", "mensal"))
        self.assertIsNone(db_mod.period_end("2026-13", "mensal"))
        self.assertIsNone(db_mod.period_end(None, "mensal"))


class EvaluateRunTest(unittest.TestCase):
    def test_run_evaluates_the_max_month_present_at_its_start(self):
        self.assertEqual(db_mod.evaluate_run(_ts(3), LEDGER), ("2026-03", db_mod.ORIGEM_HISTORICO))
        self.assertEqual(db_mod.evaluate_run(_ts(6), LEDGER), ("2026-04", db_mod.ORIGEM_HISTORICO))

    def test_daily_document_returns_the_last_day_of_the_month(self):
        # DDR: o check recorta o mês, mas a data-base exibida é o último dia remetido.
        ledger = [{"data_base_month": "2026-10", "dt_base_max": "2026-10-27",
                   "valid_from": _ts(1, 10), "valid_to": None}]
        self.assertEqual(db_mod.evaluate_run(_ts(28, 10), ledger)[0], "2026-10-27")

    def test_run_before_history_is_unknown_not_guessed(self):
        self.assertEqual(db_mod.evaluate_run(_ts(20, 2), LEDGER), (None, db_mod.ORIGEM_DESCONHECIDA))

    def test_no_history_for_the_table(self):
        self.assertEqual(db_mod.evaluate_run(_ts(6), []), (None, db_mod.SEM_HISTORICO))

    def test_month_removed_before_the_run_is_not_evaluated(self):
        ledger = [LEDGER[0], {**LEDGER[1], "valid_to": _ts(10)}]
        self.assertEqual(db_mod.evaluate_run(_ts(11), ledger)[0], "2026-03")

    def test_naive_and_string_timestamps_are_utc(self):
        # O connector devolve naive ou ISO conforme o ambiente.
        ledger = [{"data_base_month": "2026-04", "dt_base_max": "2026-04",
                   "valid_from": "2026-04-05T12:00:00Z", "valid_to": None}]
        self.assertEqual(db_mod.evaluate_run(datetime(2026, 4, 6), ledger)[0], "2026-04")


class SelectRunsTest(unittest.TestCase):
    """Último processamento vs. mês de referência."""

    RUNS = [
        # abril avaliado em 06/04; março avaliado em 03/04; um run antes do histórico.
        {"run_id": "r_abr", "source_table_fqn": TABLE, "created_at": _ts(6, hour=13), "started_at": _ts(6)},
        {"run_id": "r_mar", "source_table_fqn": TABLE, "created_at": _ts(3, hour=13), "started_at": _ts(3)},
        {"run_id": "r_old", "source_table_fqn": TABLE, "created_at": _ts(20, 2), "started_at": _ts(20, 2)},
    ]

    def _select(self, month):
        async def fake_query(sql, params=None, **kw):
            return self.RUNS if "dq_validation_runs" in sql else LEDGER

        async def fake_periodicidade():
            return lambda _t: "mensal"

        with patch.object(db_mod, "execute_query", fake_query), \
             patch.object(db_mod, "periodicidade_of_table", fake_periodicidade):
            return asyncio.run(db_mod.select_runs("1=1", {}, month))

    def test_without_month_takes_the_latest_run(self):
        sel = self._select(None)
        self.assertEqual([r["run_id"] for r in sel.runs], ["r_abr"])
        self.assertEqual(sel.tables[TABLE].data_base, "2026-04-30")

    def test_month_takes_the_latest_run_that_evaluated_it(self):
        sel = self._select("2026-03")
        self.assertEqual([r["run_id"] for r in sel.runs], ["r_mar"])
        self.assertEqual(sel.tables[TABLE].data_base, "2026-03-31")

    def test_month_without_run_leaves_the_table_out_but_known(self):
        sel = self._select("2026-05")
        self.assertEqual(sel.runs, [])
        self.assertEqual(sel.ever, {TABLE})

    def test_available_months_ignore_unidentified_runs(self):
        async def fake_query(sql, params=None, **kw):
            return self.RUNS if "dq_validation_runs" in sql else LEDGER

        async def fake_periodicidade():
            return lambda _t: "mensal"

        with patch.object(db_mod, "execute_query", fake_query), \
             patch.object(db_mod, "periodicidade_of_table", fake_periodicidade):
            months = asyncio.run(db_mod.available_months("1=1", {}))
        self.assertEqual(months, ["2026-04", "2026-03"])

    def test_reference_month_validation(self):
        self.assertEqual(db_mod.reference_month("2026-04"), "2026-04")
        self.assertIsNone(db_mod.reference_month(""))
        self.assertIsNone(db_mod.reference_month("x' OR 1=1"))


class LedgerUnreadableTest(unittest.TestCase):
    """Histórico ilegível (ex.: SP do app sem SELECT) não pode derrubar as telas."""

    def _fail_on_ledger(self):
        async def fake_query(sql, params=None, **kw):
            if "data_base_ledger" in sql:
                raise RuntimeError("[INSUFFICIENT_PERMISSIONS] User does not have SELECT on Table data_base_ledger")
            return SelectRunsTest.RUNS

        return fake_query

    def test_load_ledger_degrades_to_empty(self):
        with patch.object(db_mod, "execute_query", self._fail_on_ledger()):
            self.assertEqual(asyncio.run(db_mod.load_ledger([TABLE])), {})

    def test_strict_mode_lets_the_error_reach_the_diagnostic(self):
        with patch.object(db_mod, "execute_query", self._fail_on_ledger()):
            with self.assertRaises(RuntimeError):
                asyncio.run(db_mod.load_ledger([TABLE], strict=True))

    def test_screens_keep_the_latest_run_without_data_base(self):
        async def fake_periodicidade():
            return lambda _t: "mensal"

        with patch.object(db_mod, "execute_query", self._fail_on_ledger()), \
             patch.object(db_mod, "periodicidade_of_table", fake_periodicidade):
            sel = asyncio.run(db_mod.select_runs("1=1", {}, None))
        self.assertEqual([r["run_id"] for r in sel.runs], ["r_abr"])
        self.assertEqual(sel.tables[TABLE].origin, db_mod.SEM_HISTORICO)
        self.assertIsNone(sel.tables[TABLE].data_base)


if __name__ == "__main__":
    unittest.main()
