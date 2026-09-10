"""Leitura somente-leitura de `dq_quality_rules` no Lakebase Postgres da DQX Studio.

Desde a DQX 0.15/0.16 as regras saíram do UC; runs/métricas seguem em Delta
(`db.py`). Espelha o `pg_executor.py` da Studio: o endpoint é a única entrada
(resolve host E emite credencial, então nunca dessincronizam), usuário = client
id do SP do app, token OAuth de 1h renovado em background.

Difere da Studio em três pontos deliberados: pool assíncrono (os call sites já
são `await`), `default_transaction_read_only=on`, e degradação para `[]` quando
não configurado. O pre-ping do pool é obrigatório — o endpoint escala a zero e
mata as conexões.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Defaults iguais aos do bundle da Studio — deploy padrão dela não exige config.
LAKEBASE_ENDPOINT = (os.getenv("DQX_LAKEBASE_ENDPOINT") or "").strip()
LAKEBASE_DATABASE = os.getenv("DQX_LAKEBASE_DATABASE", "databricks_postgres")
LAKEBASE_SCHEMA = os.getenv("DQX_LAKEBASE_SCHEMA", "dqx_studio")
RULES_TABLE = os.getenv("DQX_RULES_TABLE", "dq_quality_rules")

POOL_MIN_SIZE = int(os.getenv("DQX_LAKEBASE_POOL_MIN_SIZE", "1"))
POOL_MAX_SIZE = int(os.getenv("DQX_LAKEBASE_POOL_MAX_SIZE", "5"))
TOKEN_REFRESH_MINUTES = int(os.getenv("DQX_LAKEBASE_TOKEN_REFRESH_MINUTES", "50"))
CONNECT_TIMEOUT_SECONDS = float(os.getenv("DQX_LAKEBASE_CONNECT_TIMEOUT", "30"))

# "Desligado" é sentinela, nunca vazio: a Apps API rejeita env sem `value`.
_UNSET_ENDPOINTS = {"", "__unset__", "-"}


def is_configured() -> bool:
    """Há endpoint utilizável? Falso ⇒ leituras devolvem `[]` em vez de erro."""
    return LAKEBASE_ENDPOINT.lower() not in _UNSET_ENDPOINTS


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def rules_table() -> str:
    """FQN citado, ex. `"dqx_studio"."dq_quality_rules"`."""
    return f"{_quote_ident(LAKEBASE_SCHEMA)}.{_quote_ident(RULES_TABLE)}"


# Palavra reservada, e a Studio declara a coluna assim (`"check" JSONB`).
CHECK_COLUMN = '"check"'

# A Studio removeu `active` do enum (draft|pending_approval|approved|rejected,
# com CHECK constraint): o antigo `IN ('active','approved')` tinha ramo morto.
ACTIVE_STATUS = "approved"


# ─── Pool ───────────────────────────────────────────────────────────────────

_pool: Any = None  # AsyncConnectionPool, importado lazily
_connect_kwargs: dict[str, Any] = {}
_endpoint_in_use: str = ""
_refresher: asyncio.Task | None = None
_pool_lock = asyncio.Lock()


def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _resolve_connection_blocking() -> tuple[str, str, str]:
    """(host, usuário, token) do MESMO endpoint. Sync — rodar em `to_thread`."""
    ws = _workspace_client()

    endpoint_obj = ws.postgres.get_endpoint(name=LAKEBASE_ENDPOINT)
    status = getattr(endpoint_obj, "status", None)
    hosts = getattr(status, "hosts", None)
    host = getattr(hosts, "host", None)
    if not host:
        raise RuntimeError(
            f"O endpoint Lakebase {LAKEBASE_ENDPOINT!r} não expôs host de "
            "leitura/escrita. O branch/endpoint do projeto está provisionado?"
        )

    me = ws.current_user.me()
    # Para um SP de App, `user_name` é o client id = nome do role Postgres.
    username = me.user_name or me.id or ""
    if not username:
        raise RuntimeError("Não foi possível determinar a identidade do workspace para o Lakebase")

    return host, username, _generate_token_blocking(ws)


def _generate_token_blocking(ws=None) -> str:
    """Token OAuth do endpoint (TTL 1h)."""
    ws = ws or _workspace_client()
    cred = ws.postgres.generate_database_credential(endpoint=LAKEBASE_ENDPOINT)
    token = getattr(cred, "token", None)
    if not token:
        raise RuntimeError(
            f"A resposta de credencial do Lakebase não trouxe token (endpoint={LAKEBASE_ENDPOINT})"
        )
    return token


async def _token_refresh_loop() -> None:
    """Renova a senha antes do token vencer.

    Só a PRÓXIMA conexão usa o token novo (o Postgres valida no handshake, não
    por query); `max_lifetime` recicla as vivas na mesma janela.
    """
    interval = TOKEN_REFRESH_MINUTES * 60
    while True:
        try:
            await asyncio.sleep(interval)
            token = await asyncio.to_thread(_generate_token_blocking)
            _connect_kwargs["password"] = token
            logger.info("Token do Lakebase renovado (endpoint=%s).", _endpoint_in_use)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Não derruba o loop: o token vigente ainda vale, e o pre-ping cobre.
            logger.warning("Falha ao renovar o token do Lakebase: %s", exc)


async def _ensure_pool():
    """Abre o pool na primeira leitura. Idempotente.

    Falha deixa `_pool` None e a próxima requisição retenta — é o que faz o app
    se recuperar sozinho quando o role/GRANT aparece, sem restart.
    """
    global _pool, _refresher, _endpoint_in_use

    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:  # double-checked
            return _pool

        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        host, username, token = await asyncio.to_thread(_resolve_connection_blocking)

        _connect_kwargs.clear()
        _connect_kwargs.update(
            {
                "host": host,
                "port": 5432,
                "dbname": LAKEBASE_DATABASE,
                "user": username,
                "password": token,
                "sslmode": "require",
                # read_only: cinto de segurança — o RC18 nunca escreve na Studio.
                "options": (
                    f"-c search_path={LAKEBASE_SCHEMA} "
                    "-c default_transaction_read_only=on"
                ),
                "row_factory": dict_row,
            }
        )

        pool = AsyncConnectionPool(
            conninfo="",
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            max_lifetime=TOKEN_REFRESH_MINUTES * 60,
            check=AsyncConnectionPool.check_connection,
            open=False,
            kwargs=_connect_kwargs,
            timeout=CONNECT_TIMEOUT_SECONDS,
            name="rc18-dqx-lakebase",
        )
        await pool.open(wait=True, timeout=CONNECT_TIMEOUT_SECONDS)

        _pool = pool
        _endpoint_in_use = LAKEBASE_ENDPOINT
        _refresher = asyncio.create_task(_token_refresh_loop(), name="rc18-dqx-lakebase-token-refresh")
        logger.info(
            "Pool Lakebase aberto (host=%s db=%s schema=%s user=%s).",
            host,
            LAKEBASE_DATABASE,
            LAKEBASE_SCHEMA,
            username,
        )
        return _pool


async def close_pool() -> None:
    """Fecha o pool e cancela o refresher. Chamado no shutdown do FastAPI."""
    global _pool, _refresher

    if _refresher is not None:
        _refresher.cancel()
        try:
            await _refresher
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _refresher = None

    if _pool is not None:
        try:
            await _pool.close()
            logger.info("Pool Lakebase fechado.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao fechar o pool Lakebase no shutdown: %s", exc)
        _pool = None


# ─── API de leitura ─────────────────────────────────────────────────────────


async def query(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Roda um SELECT no Lakebase e devolve lista de dicts.

    Paramstyle é o do psycopg — `%(nome)s`, NÃO o `:nome` do Databricks SQL.
    Colunas JSONB (como `check`) voltam já desserializadas em objetos Python.
    """
    pool = await _ensure_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params or {})
            return list(await cur.fetchall())


async def identity() -> str:
    """Client id com que o app conecta = alvo do GRANT.

    Mesma fonte que a conexão usa, então o comando que o diagnóstico imprime não
    pode divergir da identidade real.
    """
    def _me() -> str:
        me = _workspace_client().current_user.me()
        return me.user_name or me.id or ""

    try:
        return await asyncio.to_thread(_me)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível resolver a identidade do app: %s", exc)
        return ""


# Estados da sonda, na ordem em que a cadeia quebra.
PROBE_OK = "ok"
PROBE_NOT_CONFIGURED = "not_configured"
PROBE_CONNECT_FAILED = "connect_failed"
PROBE_PERMISSION_DENIED = "permission_denied"
PROBE_ERROR = "error"

# 42501 = insufficient_privilege: conecta mas não lê ⇒ GRANT pendente.
_SQLSTATE_INSUFFICIENT_PRIVILEGE = "42501"


async def probe_rules_access() -> tuple[str, str]:
    """(estado, detalhe) do acesso de leitura — para o diagnóstico.

    `query_or_empty` degrada para `[]`, o que apaga a causa; aqui ela é
    classificada.
    """
    if not is_configured():
        return PROBE_NOT_CONFIGURED, ""

    try:
        pool = await _ensure_pool()
    except ImportError as exc:
        # `psycopg` ausente é imagem quebrada, não role faltando: prescrever
        # "bundle deploy" aqui mandaria o operador para o lugar errado.
        return PROBE_ERROR, str(exc).strip()
    except Exception as exc:  # noqa: BLE001
        return PROBE_CONNECT_FAILED, str(exc).strip().splitlines()[0] if str(exc).strip() else ""

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # LIMIT 0 basta: o privilégio é checado no planejamento.
                await cur.execute(f"SELECT 1 FROM {rules_table()} LIMIT 0")
        return PROBE_OK, ""
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        if getattr(exc, "sqlstate", None) == _SQLSTATE_INSUFFICIENT_PRIVILEGE:
            return PROBE_PERMISSION_DENIED, detail
        return PROBE_ERROR, detail


async def query_or_empty(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Como `query`, mas `[]` quando o Lakebase não está utilizável.

    Endpoint ausente ou GRANT pendente são estado esperado, não erro: a tela
    renderiza vazia em vez de 500. Para saber QUAL é o caso, ver `diagnostics`.
    """
    if not is_configured():
        logger.debug("DQX_LAKEBASE_ENDPOINT não configurado — leitura de regras devolvendo vazio.")
        return []
    try:
        return await query(sql, params)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Leitura de regras no Lakebase falhou (endpoint=%s): %s. "
            "Ver notebooks/setup/grant_dqx_lakebase_access.sql.",
            LAKEBASE_ENDPOINT,
            exc,
        )
        return []
