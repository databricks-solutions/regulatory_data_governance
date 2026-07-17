"""Request locale handling for demo-mode mock data.

The frontend sends the active UI language in the `X-Locale` header (see
app/frontend/src/lib/api.js). In mock mode (USE_MOCK_BACKEND=true, demo bundle
only) routers use `get_locale` to pick a locale-matched fixture set so the demo
reads consistently in the chosen language. Real mode ignores this entirely —
it serves live data from Unity Catalog as-is.

Only locales with a translated mock set are honored; anything else falls back
to the Portuguese-BR default. Today: pt (default) + en.
"""

from __future__ import annotations

from fastapi import Header

DEFAULT_LOCALE = "pt"
# Locales that have a translated mock fixture set available.
SUPPORTED_LOCALES = {"pt", "en"}


def normalize_locale(raw: str | None) -> str:
    """Map an incoming locale string to a supported mock locale, or default."""
    if raw:
        code = raw.strip().lower()[:2]
        if code in SUPPORTED_LOCALES:
            return code
    return DEFAULT_LOCALE


def get_locale(x_locale: str | None = Header(default=None)) -> str:
    """FastAPI dependency: resolve the request locale from the `X-Locale` header."""
    return normalize_locale(x_locale)
