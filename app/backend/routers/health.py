"""System endpoints: health check, user info, app config."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from db import USE_MOCK, CATALOG, SCHEMA_GOLD, SCHEMA_SILVER, SCHEMA_QUALITY, SCHEMA_REFERENCE, genie_space_id
from models import (
    AppConfig,
    DependencyStatus,
    HealthResponse,
    UserContext,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return health status of backend and dependencies."""
    now = datetime.now(timezone.utc).isoformat()

    if USE_MOCK:
        return HealthResponse(
            status="healthy",
            version="1.0.0",
            timestamp=now,
            dependencies={
                "sql_warehouse": DependencyStatus(
                    status="healthy",
                    warehouse_id="mock-warehouse-id",
                    warehouse_name="r18_accelerator (mock)",
                    state="RUNNING",
                    response_time_ms=5,
                ),
                "workspace_api": DependencyStatus(
                    status="healthy",
                    host=os.getenv("DATABRICKS_HOST", "workspace.example.com"),
                    response_time_ms=3,
                ),
            },
        )

    # Real mode: probe Databricks
    deps: dict[str, DependencyStatus] = {}
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        wh_id = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
        wh = w.warehouses.get(wh_id)
        deps["sql_warehouse"] = DependencyStatus(
            status="healthy" if wh.state.value == "RUNNING" else "unhealthy",
            warehouse_id=wh_id,
            warehouse_name=wh.name,
            state=wh.state.value,
            response_time_ms=100,
        )
        deps["workspace_api"] = DependencyStatus(
            status="healthy",
            host=os.getenv("DATABRICKS_HOST", ""),
            response_time_ms=80,
        )
    except Exception as exc:
        deps["sql_warehouse"] = DependencyStatus(
            status="unhealthy",
            error=str(exc),
        )

    overall = "healthy" if all(d.status == "healthy" for d in deps.values()) else "unhealthy"
    return HealthResponse(status=overall, version="1.0.0", timestamp=now, dependencies=deps)


@router.get("/user/me", response_model=UserContext)
async def get_current_user(request: Request):
    """Return the current user's identity from Databricks App OAuth context."""
    if USE_MOCK:
        return UserContext(
            email="analyst@bankcorp.com",
            username="analyst",
            display_name="Ana Silva",
            workspace=os.getenv("DATABRICKS_WORKSPACE_NAME", ""),
            roles=["viewer"],
            preferences={
                "default_data_base": "2026-03",
                "language": "pt-BR",
                "notifications_enabled": True,
            },
        )

    email = request.headers.get("X-Forwarded-Email", "unknown@bankcorp.com")
    username = request.headers.get("X-Forwarded-User", "unknown")
    display_name = request.headers.get("X-Forwarded-Preferred-Username")
    return UserContext(
        email=email,
        username=username,
        display_name=display_name,
        workspace=os.getenv("DATABRICKS_WORKSPACE_NAME", ""),
        roles=["viewer"],
        preferences={
            "default_data_base": "2026-03",
            "language": "pt-BR",
            "notifications_enabled": True,
        },
    )


@router.get("/config", response_model=AppConfig)
async def get_app_config():
    """Return app configuration visible to the frontend."""
    return AppConfig(
        app_name="R.18 Compliance Accelerator",
        app_version="1.0.0",
        workspace=os.getenv("DATABRICKS_WORKSPACE_NAME", ""),
        catalog=CATALOG,
        schemas={
            "bronze": "bronze",
            "silver": SCHEMA_SILVER,
            "gold": SCHEMA_GOLD,
            "reference": SCHEMA_REFERENCE,
            "quality": SCHEMA_QUALITY,
        },
        documents=["3040", "3050"],
        current_layout_versions={"3040": "V1", "3050": "V11"},
        dashboards={
            "compliance": os.getenv("DASHBOARD_ID_CONFORMIDADE", ""),
            "criticas": os.getenv("DASHBOARD_ID_CRITICAS", ""),
        },
        genie_space_id=_genie_space_id(),
        features={
            "xml_viewer": os.getenv("ENABLE_XML_VIEWER", "true").lower() == "true",
            "genie_integration": True,
            "lakeview_embed": True,
            "external_lineage": os.getenv("ENABLE_LINEAGE_VIEW", "true").lower() == "true",
        },
        deadline="2026-12-31",
        language="pt-BR",
    )
