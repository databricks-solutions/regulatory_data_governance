"""Sentinel DQ - Gestao de Qualidade de Dados (RC 18) - FastAPI Backend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.db import close_pool
from backend.seed import init_db
from backend.routers import dashboard, kpis, rules, executions, incidents, bdr, lineage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
logger.info("FRONTEND_DIR resolved to: %s (exists: %s)", FRONTEND_DIR, FRONTEND_DIR.exists())
if FRONTEND_DIR.exists():
    logger.info("Frontend files: %s", list(FRONTEND_DIR.iterdir()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Sentinel DQ starting up...")
    try:
        init_db()
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
    yield
    logger.info("Sentinel DQ shutting down...")
    close_pool()


app = FastAPI(title="Sentinel DQ", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard.router)
app.include_router(kpis.router)
app.include_router(rules.router)
app.include_router(executions.router)
app.include_router(incidents.router)
app.include_router(bdr.router)
app.include_router(lineage.router)


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "app": "sentinel-dq",
        "frontend_dir": str(FRONTEND_DIR),
        "frontend_exists": FRONTEND_DIR.exists(),
        "frontend_files": [str(f.name) for f in FRONTEND_DIR.iterdir()] if FRONTEND_DIR.exists() else [],
        "assets_exists": (FRONTEND_DIR / "assets").exists() if FRONTEND_DIR.exists() else False,
    }


@app.post("/api/seed")
def trigger_seed():
    """Manually trigger database initialization and seeding."""
    try:
        init_db()
        return {"status": "ok", "message": "Database initialized and seeded"}
    except Exception as e:
        logger.error("Manual seed failed: %s", e)
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any non-API route."""
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
