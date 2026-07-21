"""Runtime configuration helpers for the external DQX Studio app."""

from __future__ import annotations

import os


_UNSET_DQX_STUDIO_URLS = {"", "about:blank"}


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
