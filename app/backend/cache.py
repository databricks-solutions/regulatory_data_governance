"""Cache em memória das leituras repetidas no warehouse e na API do workspace.

Compartilhado entre usuários de propósito: o app consulta como o SP dele (não em
nome do usuário), então todos veem os mesmos dados. Se um dia passar a usar o
token do usuário, a identidade tem de entrar na chave.

- Por processo: cada worker do uvicorn tem o seu. Limpar numa escrita só vale
  no worker que a recebeu — o prazo curto limita o atraso no outro.
- Chamadas simultâneas da mesma chave compartilham uma consulta só (a home
  dispara várias rotas que leem as mesmas tabelas ao mesmo tempo).
- Exceção não é guardada: a próxima chamada tenta de novo.
- `?fresh=1` em qualquer rota de API ignora o valor guardado e o substitui.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Hashable

import request_context

# Prazo por namespace, em segundos. `links` é escrito pelo próprio app
# (/linking); os demais, por quem roda fora dele (Studio, pipelines, setup job).
TTL_S = {
    "links": 30,       # governance.cadoc_tabelas / regra_vinculos
    "dqx": 60,         # runs, métricas e regras executadas da DQX Studio
    "pipeline": 120,   # gold.processing_state e data-bases das posições
    "reference": 300,  # reference.* e metadados do workspace
}
_MAX_ENTRIES = 512

Key = tuple[str, Hashable]

_entries: dict[Key, tuple[float, Any]] = {}  # chave → (expira_em, valor)
_inflight: dict[Key, asyncio.Task] = {}
_generation: dict[str, int] = {}  # namespace → contador de invalidações


async def get_or_load(namespace: str, key: Hashable, loader: Callable[[], Awaitable[Any]]) -> Any:
    """Valor de `(namespace, key)`; chama `loader` se não houver um válido."""
    if namespace not in TTL_S:
        raise KeyError(f"namespace de cache desconhecido: {namespace}")
    full_key = (namespace, key)
    stats = request_context.current()
    hit = _entries.get(full_key)
    if hit and hit[0] > time.monotonic() and not (stats and stats.fresh):
        _count(stats, hit=True)
        return hit[1]

    task = _inflight.get(full_key)
    _count(stats, hit=task is not None)
    if task is None:
        task = asyncio.ensure_future(_load(full_key, loader, _generation.get(namespace, 0)))
        _inflight[full_key] = task
        task.add_done_callback(lambda t: _forget(full_key, t))
    # shield: request cancelado (cliente fechou a aba) não cancela a consulta
    # dos outros que esperam a mesma chave.
    return await asyncio.shield(task)


def invalidate(*namespaces: str) -> None:
    """Descarta os valores dos namespaces (neste processo)."""
    for ns in namespaces:
        _generation[ns] = _generation.get(ns, 0) + 1
        for key in [k for k in _entries if k[0] == ns]:
            del _entries[key]
        for key in [k for k in _inflight if k[0] == ns]:
            del _inflight[key]


def clear() -> None:
    invalidate(*{k[0] for k in (*_entries, *_inflight)})


async def _load(full_key: Key, loader: Callable[[], Awaitable[Any]], generation: int) -> Any:
    value = await loader()
    # Invalidado desde o agendamento: o resultado pode ser anterior à escrita.
    if _generation.get(full_key[0], 0) == generation:
        _store(full_key, value)
    return value


def _store(full_key: Key, value: Any) -> None:
    now = time.monotonic()
    if len(_entries) >= _MAX_ENTRIES:
        for k in [k for k, (exp, _v) in _entries.items() if exp <= now]:
            del _entries[k]
        while len(_entries) >= _MAX_ENTRIES:
            del _entries[next(iter(_entries))]  # o mais antigo
    _entries[full_key] = (now + TTL_S[full_key[0]], value)


def _forget(full_key: Key, task: asyncio.Task) -> None:
    if _inflight.get(full_key) is task:
        del _inflight[full_key]
    if not task.cancelled():
        task.exception()  # marca como lida mesmo se ninguém mais esperava


def _count(stats: request_context.RequestStats | None, *, hit: bool) -> None:
    if stats is None:
        return
    if hit:
        stats.cache_hits += 1
    else:
        stats.cache_misses += 1
