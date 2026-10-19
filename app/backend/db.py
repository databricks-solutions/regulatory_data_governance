"""Databricks SQL connection manager.

Provides both real Databricks SQL connections (via a process-wide connection
pool) and a mock mode for local development.

### Por que pooling?

Cada `sql.connect(...)` abre uma sessão no SQL Warehouse — operação cara
(handshake Thrift + auth + alocação de sessão), facilmente ~500ms-1s de
latência percebida no app. Sem pool, todo handler `await execute_query(...)`
paga esse custo, e o devloop fica visivelmente lento.

O pool guarda até N conexões, abertas sob demanda (default 5, configurável
via `DATABRICKS_SQL_POOL_SIZE`). Cada `get_sql_cursor()` puxa uma conexão
ociosa (ou abre uma), abre um cursor de curta duração, e devolve a conexão ao
pool quando o `with` block sai. Falhas transitórias (sessão morta pelo
auto-stop do warehouse, rede) descartam a conexão e são repetidas por
`execute_query` — recuperação transparente.

O pool é por processo: cada worker do uvicorn tem o seu.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"
CATALOG = os.getenv("DATABRICKS_CATALOG", "rc18_catalog")

# Namespace prefix scoping which External Metadata objects the app lists/manages.
# UC external metadata is metastore-wide: sem prefixo, a página de Linhagem puxaria
# objetos de outros projetos no mesmo metastore e falharia no delete/edit (o SP do
# app não é owner). Derivado do catálogo do deployment (`<base>_catalog` → `<base>_`)
# para ser multi-tenant sem configuração. Override: LINEAGE_OBJECT_PREFIX.
def _derive_lineage_prefix(catalog: str) -> str:
    base = catalog[:-len("_catalog")] if catalog.endswith("_catalog") else catalog
    base = base.strip("_") or "rc18"
    return f"{base}_"


LINEAGE_OBJECT_PREFIX = os.getenv("LINEAGE_OBJECT_PREFIX") or _derive_lineage_prefix(CATALOG)
SCHEMA_BRONZE = os.getenv("SCHEMA_BRONZE", "bronze")
SCHEMA_GOLD = os.getenv("SCHEMA_GOLD", "gold")
SCHEMA_SILVER = os.getenv("SCHEMA_SILVER", "silver")
SCHEMA_QUALITY = os.getenv("SCHEMA_QUALITY", "quality")
SCHEMA_REFERENCE = os.getenv("SCHEMA_REFERENCE", "reference")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
POOL_SIZE = int(os.getenv("DATABRICKS_SQL_POOL_SIZE", "5"))

# Catálogo/schema DELTA da DQX Studio. ⚠️ Desde a DQX 0.15/0.16 hospeda APENAS as
# tabelas de execução (append-only, escritas pelo task runner). As definições de
# regra também saem daqui, do `checks_json` dos runs — ver `dqx_rules.py`.
# Vem de `var.dqx_catalog`/`var.dqx_schema`; fallback = catálogo RC18 (dev local).
DQX_CATALOG = os.getenv("DQX_CATALOG", CATALOG)
DQX_SCHEMA = os.getenv("DQX_SCHEMA", SCHEMA_QUALITY)
_DQX_SCHEMA_FQN = f"{DQX_CATALOG}.{DQX_SCHEMA}"

# Tabelas de execução mantidas em Delta pela DQX Studio.
DQX_VALIDATION_RUNS_TABLE = os.getenv(
    "DQX_VALIDATION_RUNS_TABLE", f"{_DQX_SCHEMA_FQN}.dq_validation_runs"
)
DQX_METRICS_TABLE = os.getenv("DQX_METRICS_TABLE", f"{_DQX_SCHEMA_FQN}.dq_metrics")

# Genie Space ID. O app.yml usa o default `__unset__` (não pode ser string
# vazia: a Apps API rejeita env sem `value` — ver CLAUDE.md "Bundle gotchas").
# `__unset__` e "" significam "Genie não provisionado" → o app mostra o
# placeholder "disponível após deploy". Depois de criar o space via o bundle
# `genie/`, defina `genie_space_id` no target.yml do core e redeploy.
_GENIE_UNSET = {"", "__unset__"}


def genie_space_id() -> str:
    raw = (os.getenv("GENIE_SPACE_ID") or "").strip()
    return "" if raw in _GENIE_UNSET else raw


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
# Conexões abertas sob demanda até POOL_SIZE: a primeira query espera uma
# sessão (~2-3s), não as POOL_SIZE em sequência. LIFO reusa a mais recente.

_idle: queue.LifoQueue = queue.LifoQueue()
_slots = threading.BoundedSemaphore(POOL_SIZE)

# Retry de falha transitória: sessão invalidada pelo auto-stop do warehouse
# (todas as do pool morrem juntas) ou rede. A partida do warehouse em si o
# conector já espera (repete 429/503 até 900s).
_RETRY_DELAYS_S = (1.0, 3.0)
_ERROR_CLASS_RE = re.compile(r"\[([A-Z][A-Z0-9_]+(?:\.[A-Z0-9_]+)*)\]")
_SESSION_MARKERS = ("INVALID_HANDLE", "SessionHandle", "SESSION_NOT_FOUND", "SESSION_CLOSED")
_READ_PREFIXES = ("SELECT", "WITH", "SHOW", "DESCRIBE")


def _is_session_error(exc: Exception) -> bool:
    """Sessão morta: o statement nem chegou a rodar — seguro repetir até escrita."""
    msg = str(exc)
    return any(m in msg for m in _SESSION_MARKERS)


def _is_transient(exc: Exception) -> bool:
    """Falha de conexão/sessão, não do SQL. Erro com classe Spark (`[TABLE_OR_VIEW_NOT_FOUND]`,
    `[INSUFFICIENT_PERMISSIONS]`, ...) é determinístico e não se repete."""
    from databricks.sql import exc as sql_exc

    if not isinstance(exc, (sql_exc.Error, OSError)):
        return False  # bug do próprio app (KeyError, TypeError...)
    if _is_session_error(exc):
        return True
    return _ERROR_CLASS_RE.search(str(exc)) is None


def _discard_idle() -> None:
    while True:
        try:
            conn = _idle.get_nowait()
        except queue.Empty:
            return
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def close_pool() -> None:
    """Close every idle connection. Called from FastAPI lifespan shutdown."""
    _discard_idle()
    logger.info("Connection pool fechado.")


@contextmanager
def get_sql_cursor() -> Generator:
    """Context manager that yields a cursor on a pooled connection.

    Comportamento:
    - Bloqueia se POOL_SIZE conexões já estão em uso.
    - Reusa uma conexão ociosa ou abre uma nova.
    - Erro de SQL mantém a conexão (a sessão segue boa). Falha transitória a
      descarta junto com as ociosas — se o warehouse parou, morreram todas.
    """
    _slots.acquire()
    conn = None
    healthy = True
    try:
        try:
            conn = _idle.get_nowait()
        except queue.Empty:
            conn = _get_real_connection()
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            try:
                cursor.close()
            except Exception:  # noqa: BLE001
                healthy = False
    except Exception as exc:
        if _is_transient(exc):
            healthy = False
            _discard_idle()
        raise
    finally:
        if conn is not None:
            if healthy:
                _idle.put(conn)
            else:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
        _slots.release()


def _execute_query_sync(query: str, params: dict[str, Any] | None) -> list[dict]:
    with get_sql_cursor() as cursor:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def _execute_with_retry(query: str, params: dict[str, Any] | None) -> list[dict]:
    # Escrita só repete em sessão morta: com falha de rede no meio, o INSERT
    # pode ter rodado.
    is_read = query.lstrip().upper().startswith(_READ_PREFIXES)
    for delay in (*_RETRY_DELAYS_S, None):
        try:
            return _execute_query_sync(query, params)
        except Exception as exc:
            retryable = _is_transient(exc) if is_read else _is_session_error(exc)
            if delay is None or not retryable:
                raise
            logger.warning("Falha transitória no SQL, nova tentativa em %.0fs: %s",
                           delay, str(exc).splitlines()[0][:200])
            time.sleep(delay)


async def execute_query(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute a parameterized SQL query and return results as list of dicts.

    O conector SQL é síncrono: roda numa thread para não travar o event loop —
    sem isso o app atende uma requisição por vez e o pool nunca é usado em
    paralelo. Falha transitória é repetida (`_execute_with_retry`). When
    USE_MOCK is True, this is not called — routers return mock data directly.
    """
    return await asyncio.to_thread(_execute_with_retry, query, params)


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
