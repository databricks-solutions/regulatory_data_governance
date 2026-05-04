"""Databricks SQL connection manager.

Provides both real Databricks SQL connections and a mock mode for local development.
"""

from __future__ import annotations

import logging
import os
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


@contextmanager
def get_sql_cursor() -> Generator:
    """Context manager that yields a SQL cursor and handles cleanup."""
    conn = _get_real_connection()
    try:
        cursor = conn.cursor()
        yield cursor
    finally:
        cursor.close()
        conn.close()


async def execute_query(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute a parameterized SQL query and return results as list of dicts.

    When USE_MOCK is True, this is not called — routers return mock data directly.
    """
    with get_sql_cursor() as cursor:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def fq(schema: str, table: str) -> str:
    """Return a fully qualified table name: catalog.schema.table."""
    return f"{CATALOG}.{schema}.{table}"
