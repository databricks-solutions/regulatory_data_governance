"""FastAPI entrypoint for the R.18 Compliance Accelerator."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (two levels up: app/backend → app → repo root) for
# local dev. In Databricks Apps the runtime env comes from app.yaml; load_dotenv
# is a no-op there because the file isn't bundled.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
if _REPO_ROOT_ENV.exists():
    load_dotenv(_REPO_ROOT_ENV, override=False)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from routers import (
    branding,
    dashboard,
    governance,
    health,
    lineage,
    quality,
    reference,
    submissions,
    validation,
    xml_processing,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("r18_app")

FRONTEND_DIR = Path(__file__).parent / "frontend_dist"
BRAND_STATIC_DIR = Path(__file__).parent / "static" / "brand"
BRAND_STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: setup and teardown."""
    logger.info("R.18 Compliance Accelerator starting up")
    logger.info("USE_MOCK_BACKEND=%s", os.getenv("USE_MOCK_BACKEND", "true"))
    logger.info("CATALOG=%s", os.getenv("DATABRICKS_CATALOG", "rc18_catalog"))
    yield
    # Close the SQL connection pool (no-op in mock mode — pool only initializes
    # lazily on the first real query).
    try:
        from db import close_pool

        close_pool()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao fechar connection pool no shutdown: %s", exc)
    logger.info("R.18 Compliance Accelerator shutting down")


app = FastAPI(
    title="RC18 StarterKit API",
    description="API for BACEN Resolucao Conjunta N.18 compliance accelerator",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# --- CORS middleware for local development ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mount routers per API spec Section 1.4 ---
app.include_router(health.router, prefix="/api/v1", tags=["system"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(quality.router, prefix="/api/v1/quality", tags=["quality"])
app.include_router(validation.router, prefix="/api/v1/validations", tags=["validations"])
app.include_router(lineage.router, prefix="/api/v1/lineage", tags=["lineage"])
app.include_router(xml_processing.router, prefix="/api/v1/xml", tags=["xml"])
app.include_router(reference.router, prefix="/api/v1/reference", tags=["reference"])
app.include_router(submissions.router, prefix="/api/v1/submissions", tags=["submissions"])
app.include_router(governance.router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(branding.router, prefix="/api/v1/brand", tags=["brand"])

# --- Brand static assets (uploaded logos) ---
app.mount("/brand", StaticFiles(directory=str(BRAND_STATIC_DIR)), name="brand_assets")

# --- Static file serving for Svelte frontend ---
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "_app").exists():
    app.mount("/_app", StaticFiles(directory=str(FRONTEND_DIR / "_app")), name="app_assets")
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_spa():
    """Serve the Svelte SPA index.html."""
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse(
        content={
            "message": "R.18 Compliance Accelerator API is running. Frontend not yet built.",
            "docs": "/api/docs",
            "openapi": "/api/openapi.json",
        }
    )


@app.get("/{path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_spa_routes(path: str):
    """SPA fallback for client-side routing — serves index.html for non-API paths."""
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "Endpoint not found"}})
    # Try to serve a static file first
    static_file = FRONTEND_DIR / path
    if static_file.exists() and static_file.is_file():
        return FileResponse(str(static_file))
    # Fall back to SPA index
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse(
        content={
            "message": "R.18 Compliance Accelerator API is running. Frontend not yet built.",
            "docs": "/api/docs",
        }
    )
