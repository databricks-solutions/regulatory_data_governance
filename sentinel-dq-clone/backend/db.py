"""Database connection helpers for Lakebase (PostgreSQL) and Databricks SQL."""

import json
import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lakebase (PostgreSQL) connection pool
# ---------------------------------------------------------------------------

_pool = None


def _get_oauth_token() -> str:
    """Get an OAuth token from the Databricks SDK for Lakebase authentication."""
    try:
        profile = os.environ.get("DATABRICKS_PROFILE")
        if profile:
            w = WorkspaceClient(profile=profile)
        else:
            w = WorkspaceClient()

        if w.config.token:
            return w.config.token

        headers = w.config.authenticate()
        if headers and "Authorization" in headers:
            return headers["Authorization"].replace("Bearer ", "")
    except Exception as e:
        logger.warning("Failed to get OAuth token for Lakebase: %s", e)
    return ""


def _get_pg_user() -> str:
    """Get the PostgreSQL user."""
    user = (
        os.environ.get("PGUSER")
        or os.environ.get("LAKEBASE_USER")
        or os.environ.get("DATABRICKS_APP_DB_sentinel-db_USER")
    )
    if user:
        return user

    sp_id = os.environ.get("DATABRICKS_CLIENT_ID")
    if sp_id:
        return sp_id

    try:
        profile = os.environ.get("DATABRICKS_PROFILE")
        if profile:
            w = WorkspaceClient(profile=profile)
        else:
            w = WorkspaceClient()
        me = w.current_user.me()
        return me.user_name
    except Exception:
        pass

    return "dq_user"


def _get_pg_config() -> dict:
    """Build PostgreSQL connection config from environment variables."""
    host = (
        os.environ.get("PGHOST")
        or os.environ.get("LAKEBASE_HOST")
        or os.environ.get("DATABRICKS_APP_DB_sentinel-db_HOST")
        or "localhost"
    )
    port = (
        os.environ.get("PGPORT")
        or os.environ.get("LAKEBASE_PORT")
        or os.environ.get("DATABRICKS_APP_DB_sentinel-db_PORT")
        or "5432"
    )
    dbname = (
        os.environ.get("PGDATABASE")
        or os.environ.get("LAKEBASE_DATABASE")
        or os.environ.get("DATABRICKS_APP_DB_sentinel-db_NAME")
        or "databricks_postgres"
    )
    user = _get_pg_user()

    password = (
        os.environ.get("PGPASSWORD")
        or os.environ.get("LAKEBASE_PASSWORD")
        or os.environ.get("DATABRICKS_APP_DB_sentinel-db_PASSWORD")
    )
    if not password:
        logger.info("No Lakebase password found, generating OAuth token...")
        password = _get_oauth_token()

    sslmode = os.environ.get("PGSSLMODE", "require")

    return {
        "host": host,
        "port": int(port),
        "dbname": dbname,
        "user": user,
        "password": password,
        "sslmode": sslmode,
        "options": "-c search_path=dq_rc18,public",
    }


def _is_auth_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "authorization" in msg or "invalid token" in msg or "authentication" in msg


def get_pool():
    """Return or create a threaded connection pool."""
    global _pool
    if _pool is None:
        cfg = _get_pg_config()
        logger.info(
            "Connecting to Lakebase at %s:%s/%s as user=%s",
            cfg["host"], cfg["port"], cfg["dbname"], cfg["user"],
        )
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, **cfg)
        try:
            conn = _pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, current_database(), current_schema()")
                row = cur.fetchone()
                logger.info("Lakebase connected: user=%s db=%s schema=%s", row[0], row[1], row[2])
            conn.commit()
            _pool.putconn(conn)
        except Exception as e:
            logger.error("Lakebase connection verification failed: %s", e)
    return _pool


@contextmanager
def get_conn():
    """Context manager that checks out and returns a connection."""
    global _pool
    pool = get_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
        conn.commit()
    except psycopg2.OperationalError as e:
        if conn:
            try:
                conn.rollback()
                pool.putconn(conn, close=True)
                conn = None
            except Exception:
                pass
        if _is_auth_error(e):
            logger.warning("Lakebase auth error - resetting pool: %s", e)
            _pool = None
        raise
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            try:
                pool.putconn(conn)
            except Exception:
                pass


def query(sql: str, params=None) -> list[dict]:
    """Execute a SELECT and return rows as list of dicts."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def execute(sql: str, params=None):
    """Execute an INSERT/UPDATE/DELETE."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def execute_returning(sql: str, params=None) -> list[dict]:
    """Execute an INSERT ... RETURNING and return rows."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Databricks SQL (Unity Catalog) via WorkspaceClient
# ---------------------------------------------------------------------------

_workspace_client = None


def get_workspace_client() -> WorkspaceClient:
    """Get or create a WorkspaceClient."""
    global _workspace_client
    if _workspace_client is None:
        profile = os.environ.get("DATABRICKS_PROFILE")
        if profile:
            _workspace_client = WorkspaceClient(profile=profile)
        else:
            _workspace_client = WorkspaceClient()
    return _workspace_client


def run_dbsql_query(sql: str, warehouse_id: str = None) -> list[dict]:
    """Execute a SQL statement via Databricks SQL Statement Execution API."""
    wh_id = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID", "c0bae51c5113e9a4")
    w = get_workspace_client()

    logger.info("Executing DBSQL: %s", sql[:200])

    response = w.statement_execution.execute_statement(
        warehouse_id=wh_id, statement=sql, wait_timeout="50s",
    )

    if response.status and response.status.state:
        state = response.status.state.value if hasattr(response.status.state, "value") else str(response.status.state)
        if state == "FAILED":
            error_msg = ""
            if response.status.error:
                error_msg = response.status.error.message or str(response.status.error)
            raise RuntimeError(f"DBSQL query failed: {error_msg}")

    if not response.result or not response.result.data_array:
        return []

    columns = [col.name for col in response.manifest.schema.columns]
    rows = []
    for row_data in response.result.data_array:
        row = {}
        for i, col_name in enumerate(columns):
            val = row_data[i] if i < len(row_data) else None
            row[col_name] = val
        rows.append(row)

    return rows


def close_pool():
    """Close the connection pool (for graceful shutdown)."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
