"""Branding configuration API — logo upload, theme settings, and embedded
external app URLs (e.g., DQX Studio).

The `GET /config` endpoint also surfaces runtime-configurable URLs that the
SPA needs but that the customer overrides per environment via env vars (so
they never get hardcoded into the bundled frontend). Currently:

- ``dqx_studio_url`` — DQX Studio Databricks App URL. Empty string means the
  "Motor de Regras" page renders an empty state with deploy instructions.
- ``dqx_studio_entry_url`` — base + tela de entrada configurável. É o que o
  iframe carrega; separada da base porque a Studio renomeia rotas entre versões
  e o caminho não pode ficar compilado no frontend. Ver `dqx_config`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from dqx_config import dqx_studio_base_url, dqx_studio_entry_url

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


def disabled_modules() -> list[str]:
    """Módulos (menus da sidebar) a ocultar, vindos da env var DISABLED_MODULES.

    Lista CSV de slugs (ex. "lineage,xml,genie"). O bundle injeta a var a
    partir de `var.disabled_modules` (target.yml). O default do bundle é a
    sentinela `__none__` (a Apps API rejeita env vazia — ver CLAUDE.md), que
    aqui normaliza para lista vazia = nada desabilitado. Slugs em snake/kebab,
    case-insensitive, espaços e vazios descartados.
    """
    raw = os.getenv("DISABLED_MODULES", "") or ""
    if raw.strip().lower() in ("", "__none__"):
        return []
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


@router.get("/config")
def get_brand_config():
    config = _load()
    # Surface runtime-configurable embed URLs alongside branding so the SPA
    # only needs one fetch on bootstrap. Empty string = unset; in particular,
    # never expose the bundle's `about:blank` sentinel as an iframe URL.
    config["dqx_studio_url"] = dqx_studio_base_url() or ""
    # O SPA usa a entry no iframe; a base segue exibida como "endpoint
    # configurado" e decide o estado vazio.
    config["dqx_studio_entry_url"] = dqx_studio_entry_url() or ""
    # Módulos desabilitados por ambiente — a sidebar oculta esses menus.
    config["disabled_modules"] = disabled_modules()
    return config


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
