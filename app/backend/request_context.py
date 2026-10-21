"""Estado por request: contadores de SQL/cache e o bypass `?fresh=1`.

O middleware de `main.py` abre um `RequestStats` por request de API; `db.py` e
`cache.py` o atualizam. O objeto é mutável de propósito: `asyncio.to_thread` e
`asyncio.gather` copiam o contexto, mas a cópia aponta para o mesmo objeto.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestStats:
    fresh: bool = False
    sql_count: int = 0
    sql_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0


_current: ContextVar[RequestStats | None] = ContextVar("rc18_request_stats", default=None)


def start(*, fresh: bool = False) -> RequestStats:
    stats = RequestStats(fresh=fresh)
    _current.set(stats)
    return stats


def current() -> RequestStats | None:
    return _current.get()
