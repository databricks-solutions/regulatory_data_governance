"""Branding configuration API — logo upload and theme settings."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()

CONFIG_PATH = Path(__file__).parent.parent / "brand_config.json"
BRAND_STATIC_DIR = Path(__file__).parent.parent / "static" / "brand"

DEFAULT_CONFIG: dict = {
    "name": "BankCorp",
    "primary_color": "#1E293B",
    "accent_color": "#0EA5E9",
    "logo_url": None,
    "theme_preset": "slate",
}


class BrandConfig(BaseModel):
    name: str = "BankCorp"
    primary_color: str = "#1E293B"
    accent_color: str = "#0EA5E9"
    logo_url: str | None = None
    theme_preset: str = "slate"


def _load() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def _save(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


@router.get("/config")
def get_brand_config():
    return _load()


@router.post("/config")
def update_brand_config(config: BrandConfig):
    current = _load()
    data = config.model_dump()
    # Preserve logo_url if not explicitly changed
    if data.get("logo_url") is None and current.get("logo_url"):
        data["logo_url"] = current["logo_url"]
    _save(data)
    return data


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...)):
    allowed = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Tipo não suportado. Use PNG, JPEG, SVG ou WebP.",
        )

    suffix = Path(file.filename or "logo").suffix or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
        suffix = ".png"

    BRAND_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    for old in BRAND_STATIC_DIR.glob("logo.*"):
        old.unlink(missing_ok=True)

    logo_path = BRAND_STATIC_DIR / f"logo{suffix}"
    logo_path.write_bytes(await file.read())

    logo_url = f"/brand/logo{suffix}"
    config = _load()
    config["logo_url"] = logo_url
    _save(config)

    return {"logo_url": logo_url}


@router.delete("/logo")
def delete_logo():
    for old in BRAND_STATIC_DIR.glob("logo.*"):
        old.unlink(missing_ok=True)
    config = _load()
    config["logo_url"] = None
    _save(config)
    return {"logo_url": None}
