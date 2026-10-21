"""Testes do cache em memória (`app/backend/cache.py`) e da sua ligação com `db.py`.

Protegem o que um cache ingênuo quebraria: requests simultâneos repetindo a
mesma consulta, exceção guardada como resultado, invalidação perdida para uma
consulta em andamento e linhas compartilhadas sendo alteradas por quem chama.
"""

import asyncio
import unittest
from unittest.mock import patch

import cache
import request_context
from app.backend import db


class CountingLoader:
    def __init__(self, value="v", error=None, delay=0.0):
        self.value, self.error, self.delay = value, error, delay
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.value


class CacheTest(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_second_call_is_a_hit(self):
        loader = CountingLoader()

        async def run():
            await cache.get_or_load("dqx", "k", loader)
            return await cache.get_or_load("dqx", "k", loader)

        self.assertEqual(asyncio.run(run()), "v")
        self.assertEqual(loader.calls, 1)

    def test_concurrent_calls_share_one_load(self):
        """A home dispara várias rotas que leem as mesmas tabelas ao mesmo tempo."""
        loader = CountingLoader(delay=0.01)

        async def run():
            return await asyncio.gather(*(cache.get_or_load("dqx", "k", loader) for _ in range(5)))

        self.assertEqual(asyncio.run(run()), ["v"] * 5)
        self.assertEqual(loader.calls, 1)

    def test_errors_are_not_cached(self):
        failing = CountingLoader(error=RuntimeError("warehouse"))
        ok = CountingLoader()

        async def run():
            with self.assertRaises(RuntimeError):
                await cache.get_or_load("dqx", "k", failing)
            return await cache.get_or_load("dqx", "k", ok)

        self.assertEqual(asyncio.run(run()), "v")
        self.assertEqual(ok.calls, 1)

    def test_expired_entry_reloads(self):
        loader = CountingLoader()

        async def run():
            await cache.get_or_load("dqx", "k", loader)
            with patch("cache.time.monotonic", return_value=cache.time.monotonic() + cache.TTL_S["dqx"] + 1):
                await cache.get_or_load("dqx", "k", loader)

        asyncio.run(run())
        self.assertEqual(loader.calls, 2)

    def test_invalidate_drops_only_its_namespace(self):
        links, dqx = CountingLoader(), CountingLoader()

        async def run():
            await cache.get_or_load("links", "k", links)
            await cache.get_or_load("dqx", "k", dqx)
            cache.invalidate("links")
            await cache.get_or_load("links", "k", links)
            await cache.get_or_load("dqx", "k", dqx)

        asyncio.run(run())
        self.assertEqual((links.calls, dqx.calls), (2, 1))

    def test_load_in_flight_during_invalidate_is_not_stored(self):
        """Uma escrita no meio da leitura: o resultado pode ser anterior a ela."""
        slow = CountingLoader(value="antigo", delay=0.01)
        fresh = CountingLoader(value="novo")

        async def run():
            pending = asyncio.ensure_future(cache.get_or_load("links", "k", slow))
            await asyncio.sleep(0)
            cache.invalidate("links")
            self.assertEqual(await pending, "antigo")
            return await cache.get_or_load("links", "k", fresh)

        self.assertEqual(asyncio.run(run()), "novo")

    def test_fresh_request_bypasses_the_stored_value(self):
        loader = CountingLoader()

        async def run():
            await cache.get_or_load("dqx", "k", loader)
            request_context.start(fresh=True)
            await cache.get_or_load("dqx", "k", loader)

        asyncio.run(run())
        self.assertEqual(loader.calls, 2)

    def test_unknown_namespace_fails_fast(self):
        with self.assertRaises(KeyError):
            asyncio.run(cache.get_or_load("typo", "k", CountingLoader()))

    def test_request_stats_count_hits_and_misses(self):
        loader = CountingLoader()

        async def run():
            stats = request_context.start()
            await cache.get_or_load("dqx", "k", loader)
            await cache.get_or_load("dqx", "k", loader)
            return stats

        stats = asyncio.run(run())
        self.assertEqual((stats.cache_hits, stats.cache_misses), (1, 1))


class CachedQueryTest(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def _patched(self, fake):
        return patch.object(db, "execute_query", fake)

    def test_same_sql_and_params_hit(self):
        calls = []

        async def fake(query, params=None):
            calls.append(params)
            return [{"a": 1}]

        async def run():
            await db.execute_query_or_empty("SELECT 1", {"x": 1}, cache_ns="dqx")
            await db.execute_query_or_empty("SELECT 1", {"x": 1}, cache_ns="dqx")
            await db.execute_query_or_empty("SELECT 1", {"x": 2}, cache_ns="dqx")

        with self._patched(fake):
            asyncio.run(run())
        self.assertEqual(calls, [{"x": 1}, {"x": 2}])

    def test_callers_get_copies(self):
        async def fake(query, params=None):
            return [{"a": 1}]

        async def run():
            first = await db.execute_query_or_empty("SELECT 1", cache_ns="dqx")
            first[0]["a"] = 99
            first.append({"a": 2})
            return await db.execute_query_or_empty("SELECT 1", cache_ns="dqx")

        with self._patched(fake):
            self.assertEqual(asyncio.run(run()), [{"a": 1}])

    def test_missing_table_is_not_cached(self):
        """A tabela aparece assim que o job a criar, sem esperar o prazo."""
        results = [Exception("[TABLE_OR_VIEW_NOT_FOUND] x"), [{"a": 1}]]

        async def fake(query, params=None):
            item = results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        async def run():
            first = await db.execute_query_or_empty("SELECT 1", cache_ns="reference")
            second = await db.execute_query_or_empty("SELECT 1", cache_ns="reference")
            return first, second

        with self._patched(fake):
            self.assertEqual(asyncio.run(run()), ([], [{"a": 1}]))

    def test_without_namespace_never_caches(self):
        calls = []

        async def fake(query, params=None):
            calls.append(query)
            return []

        async def run():
            await db.execute_query_or_empty("SELECT 1")
            await db.execute_query_or_empty("SELECT 1")

        with self._patched(fake):
            asyncio.run(run())
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
