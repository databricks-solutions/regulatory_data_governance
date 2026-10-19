import unittest
from unittest.mock import patch

from databricks.sql import exc as sql_exc

from app.backend import db


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = [("x",)]

    def execute(self, query, params):
        self.conn.executions += 1
        if self.conn.error is not None:
            raise self.conn.error

    def fetchall(self):
        return [(1,)]

    def close(self):
        pass


class FakeConn:
    def __init__(self, error=None):
        self.error = error
        self.executions = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class ExecuteWithRetryTest(unittest.TestCase):
    """Sessão morta pelo auto-stop do warehouse é repetida numa conexão nova;
    erro de SQL e falha ambígua de escrita não."""

    def setUp(self):
        db._discard_idle()
        self.opened = []
        self.next_error = None
        patcher = patch.object(db, "_get_real_connection", self._open)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep = patch.object(db.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.addCleanup(db._discard_idle)

    def _open(self):
        conn = FakeConn(self.next_error)
        self.opened.append(conn)
        return conn

    def _seed_idle(self, n, error):
        for _ in range(n):
            db._idle.put(FakeConn(error))

    def test_opens_connections_on_demand(self):
        self.assertEqual(db._execute_with_retry("SELECT 1", {}), [{"x": 1}])
        self.assertEqual(len(self.opened), 1)

    def test_dead_sessions_are_discarded_and_retried(self):
        dead = sql_exc.DatabaseError("Invalid SessionHandle: SessionHandle [abc]")
        self._seed_idle(5, dead)
        self.assertEqual(db._execute_with_retry("SELECT 1", {}), [{"x": 1}])
        self.assertEqual(len(self.opened), 1)  # as 4 ociosas restantes saíram junto
        self.assertTrue(db._idle.qsize() == 1 and db._idle.get_nowait() is self.opened[0])

    def test_sql_error_is_not_retried_and_keeps_the_connection(self):
        self.next_error = sql_exc.ServerOperationError("[TABLE_OR_VIEW_NOT_FOUND] tabela x")
        with self.assertRaises(sql_exc.ServerOperationError):
            db._execute_with_retry("SELECT * FROM x", {})
        self.assertEqual(self.opened[0].executions, 1)
        self.assertFalse(self.opened[0].closed)

    def test_network_error_on_read_is_retried(self):
        self.next_error = sql_exc.RequestError("Error during request to server")
        with self.assertRaises(sql_exc.RequestError):
            db._execute_with_retry("SELECT 1", {})
        self.assertEqual(len(self.opened), 1 + len(db._RETRY_DELAYS_S))

    def test_network_error_on_write_is_not_retried(self):
        self.next_error = sql_exc.RequestError("Error during request to server")
        with self.assertRaises(sql_exc.RequestError):
            db._execute_with_retry("INSERT INTO t VALUES (1)", {})
        self.assertEqual(len(self.opened), 1)

    def test_dead_session_on_write_is_retried(self):
        self._seed_idle(1, sql_exc.DatabaseError("[INVALID_HANDLE.SESSION_NOT_FOUND] sessão"))
        self.assertEqual(db._execute_with_retry("INSERT INTO t VALUES (1)", {}), [{"x": 1}])

    def test_app_bug_is_not_retried(self):
        self.next_error = KeyError("col")
        with self.assertRaises(KeyError):
            db._execute_with_retry("SELECT 1", {})
        self.assertEqual(len(self.opened), 1)


if __name__ == "__main__":
    unittest.main()
