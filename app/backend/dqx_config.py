"""Runtime configuration helpers for the external DQX Studio app."""

from __future__ import annotations

import os


_UNSET_DQX_STUDIO_URLS = {"", "about:blank"}

# Tela em que o RC18 entra (iframe + linkbacks). Configurável porque a Studio
# renomeia rotas entre versões: o antigo `/rules/active` foi aposentado no
# upstream e o embed passou a mostrar tela deprecada. Como variável de bundle, a
# próxima renomeação não exige rebuild do frontend.
# Alternativas: `/monitored-tables` (regras por tabela) · `/` (home).
_DEFAULT_ENTRY_PATH = "/registry-rules"

# `/` = home da Studio, não "não configurado" — daí não haver sentinela aqui.
_HOME_ENTRY_PATHS = {"", "/"}


def dqx_studio_base_url() -> str | None:
    """Return the configured DQX Studio base URL, or ``None`` when disabled.

    Bundle deployments require a real URL. The sentinel remains supported only
    defensively for legacy/local configurations, and must never leak into API
    responses or URL construction.
    """
    value = (os.getenv("DQX_STUDIO_URL") or "").strip().rstrip("/")
    if value.lower() in _UNSET_DQX_STUDIO_URLS:
        return None
    return value


def dqx_studio_entry_path() -> str:
    """Caminho normalizado; `""` = home.

    Recusa valor com esquema/host: apontaria o iframe para fora da Studio.
    """
    raw = (os.getenv("DQX_STUDIO_ENTRY_PATH") or "").strip()
    if not raw:
        return _DEFAULT_ENTRY_PATH.rstrip("/")
    if "//" in raw or ":" in raw:
        return _DEFAULT_ENTRY_PATH.rstrip("/")
    if raw in _HOME_ENTRY_PATHS:
        return ""
    path = raw if raw.startswith("/") else f"/{raw}"
    path = path.rstrip("/")
    return path or ""


def dqx_studio_entry_url() -> str | None:
    """URL da tela de entrada, ou ``None`` sem Studio configurada.

    Ponto único do iframe e dos linkbacks — antes eram três hardcodes.
    """
    base = dqx_studio_base_url()
    if not base:
        return None
    return f"{base}{dqx_studio_entry_path()}"
