"""Databricks SQL connection manager.

Provides both real Databricks SQL connections (via a process-wide connection
pool) and a mock mode for local development.

### Por que pooling?

Cada `sql.connect(...)` abre uma sessão no SQL Warehouse — operação cara
(handshake Thrift + auth + alocação de sessão), facilmente ~500ms-1s de
latência percebida no app. Sem pool, todo handler `await execute_query(...)`
paga esse custo, e o devloop fica visivelmente lento.

O pool mantém N conexões pré-abertas (default 5, configurável via
`DATABRICKS_SQL_POOL_SIZE`). Cada `get_sql_cursor()` puxa uma conexão livre
do pool, abre um cursor de curta duração, e devolve a conexão ao pool quando
o `with` block sai. Conexões em mau estado (raise dentro do `with`) são
fechadas e substituídas por novas — recuperação transparente.

A `queue.Queue` do stdlib já é thread-safe, então o pool funciona tanto
em uvicorn single-worker quanto em deploys multi-worker.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"
CATALOG = os.getenv("DATABRICKS_CATALOG", "rc18_catalog")
SCHEMA_BRONZE = os.getenv("SCHEMA_BRONZE", "bronze")
SCHEMA_GOLD = os.getenv("SCHEMA_GOLD", "gold")
SCHEMA_SILVER = os.getenv("SCHEMA_SILVER", "silver")
SCHEMA_QUALITY = os.getenv("SCHEMA_QUALITY", "quality")
SCHEMA_REFERENCE = os.getenv("SCHEMA_REFERENCE", "reference")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
POOL_SIZE = int(os.getenv("DATABRICKS_SQL_POOL_SIZE", "5"))


def _get_real_connection():
    """Create a real Databricks SQL connection using service principal auth."""
    from databricks import sql
    from databricks.sdk.core import Config

    cfg = Config()
    server_hostname = cfg.host.replace("https://", "").replace("http://", "")
    http_path = f"/sql/1.0/warehouses/{WAREHOUSE_ID}"
    return sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
        catalog=CATALOG,
    )


# ─── Connection pool ────────────────────────────────────────────────────────

_pool: queue.Queue | None = None
_pool_lock = threading.Lock()


def _ensure_pool() -> queue.Queue:
    """Lazily initialize the connection pool. Idempotent + thread-safe."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:  # double-checked
            new_pool: queue.Queue = queue.Queue(maxsize=POOL_SIZE)
            for _ in range(POOL_SIZE):
                try:
                    new_pool.put_nowait(_get_real_connection())
                except Exception as exc:  # noqa: BLE001
                    logger.error("Falha ao pré-abrir conexão SQL: %s", exc)
                    raise
            _pool = new_pool
            logger.info("Connection pool aberto com %d conexões.", POOL_SIZE)
    return _pool


def close_pool() -> None:
    """Close every pooled connection. Called from FastAPI lifespan shutdown."""
    global _pool
    with _pool_lock:
        if _pool is None:
            return
        drained = 0
        while True:
            try:
                conn = _pool.get_nowait()
            except queue.Empty:
                break
            try:
                conn.close()
                drained += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao fechar conexão SQL no shutdown: %s", exc)
        _pool = None
        logger.info("Connection pool fechado (%d conexões liberadas).", drained)


@contextmanager
def get_sql_cursor() -> Generator:
    """Context manager that yields a cursor on a pooled connection.

    Comportamento:
    - Bloqueia até uma conexão estar livre (pool exausto = espera).
    - Abre cursor de curta duração; fecha ao sair do `with`.
    - Em caso de erro dentro do `with`, descarta a conexão (pode estar em
      estado inconsistente) e devolve uma conexão NOVA ao pool — assim o
      próximo caller não herda um socket morto.
    """
    pool = _ensure_pool()
    conn = pool.get()  # blocks if all connections are busy
    cursor = None
    healthy = True
    try:
        cursor = conn.cursor()
        yield cursor
    except Exception:
        healthy = False
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                healthy = False
        if healthy:
            pool.put(conn)
        else:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                pool.put(_get_real_connection(), timeout=5)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Falha ao recriar conexão para o pool: %s. "
                    "Próxima chamada criará lazily.",
                    exc,
                )


async def execute_query(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute a parameterized SQL query and return results as list of dicts.

    When USE_MOCK is True, this is not called — routers return mock data directly.
    """
    with get_sql_cursor() as cursor:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]


async def execute_query_or_empty(
    query: str, params: dict[str, Any] | None = None
) -> list[dict]:
    """Like `execute_query` but returns `[]` when the target table/view does
    not exist yet.

    Use on read paths that depend on tables seeded by the setup job
    or produced by downstream pipelines (e.g. quality scorecard tables
    written by an external DQX Studio run). Those tables may not exist
    until the customer runs the corresponding job; a missing table is a
    "not yet" case, not a server error — the UI should render an empty
    state instead of a 500.
    """
    try:
        return await execute_query(query, params)
    except Exception as exc:  # noqa: BLE001 — narrow by inspecting the message
        msg = str(exc)
        if "TABLE_OR_VIEW_NOT_FOUND" in msg or "SCHEMA_NOT_FOUND" in msg:
            logger.warning(
                "Tabela ainda não disponível (rode setup_reference_tables ou "
                "o pipeline silver primeiro): %s",
                msg.splitlines()[0],
            )
            return []
        raise


def fq(schema: str, table: str) -> str:
    """Return a fully qualified table name: catalog.schema.table."""
    return f"{CATALOG}.{schema}.{table}"
