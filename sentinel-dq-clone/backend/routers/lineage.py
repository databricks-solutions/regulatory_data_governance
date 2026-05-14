"""Lineage router - proxy to Unity Catalog lineage API."""

import logging
from fastapi import APIRouter, HTTPException
from backend.db import get_workspace_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lineage", tags=["lineage"])


@router.get("/{table_fqn:path}")
def get_lineage(table_fqn: str):
    """Get upstream and downstream lineage for a table."""
    try:
        w = get_workspace_client()

        # Use the REST API for lineage
        # The SDK may not have a direct lineage method, so we use the API client
        upstream = []
        downstream = []

        try:
            # Try using the data_governance API
            response = w.api_client.do(
                "GET",
                f"/api/2.0/lineage-tracking/table-lineage",
                query={"table_name": table_fqn, "include_entity_lineage": "true"},
            )
            if response:
                upstream_tables = response.get("upstreams", [])
                downstream_tables = response.get("downstreams", [])

                for t in upstream_tables:
                    table_info = t.get("tableInfo", {})
                    upstream.append({
                        "name": table_info.get("name", ""),
                        "catalog": table_info.get("catalog_name", ""),
                        "schema": table_info.get("schema_name", ""),
                        "full_name": f"{table_info.get('catalog_name', '')}.{table_info.get('schema_name', '')}.{table_info.get('name', '')}",
                    })

                for t in downstream_tables:
                    table_info = t.get("tableInfo", {})
                    downstream.append({
                        "name": table_info.get("name", ""),
                        "catalog": table_info.get("catalog_name", ""),
                        "schema": table_info.get("schema_name", ""),
                        "full_name": f"{table_info.get('catalog_name', '')}.{table_info.get('schema_name', '')}.{table_info.get('name', '')}",
                    })
        except Exception as e:
            logger.warning("Lineage API call failed for %s: %s", table_fqn, e)

        return {
            "table": table_fqn,
            "upstream": upstream,
            "downstream": downstream,
        }

    except Exception as e:
        logger.error("Lineage error for %s: %s", table_fqn, e)
        return {
            "table": table_fqn,
            "upstream": [],
            "downstream": [],
            "error": str(e),
        }
