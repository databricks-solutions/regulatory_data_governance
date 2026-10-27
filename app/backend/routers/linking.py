"""Rule ↔ CADOC ↔ R.18 dimension linking endpoints.

This router backs the `/linking` screen. It lets a user (1) manage CADOC
documents (3040, 3050, or new ones) and associate silver tables to each, and
(2) link DQX rules to a CADOC + one of the 12 R.18 dimensions — replacing the
hand-authored `user_metadata.dimensao_r18` tags and the hard-coded
`silver.scr3040_` prefix.

Persistence lives in RC18-owned tables in `${CATALOG}.governance` (the app has
only SELECT on the DQX Studio catalog, but read+write on its own governance
schema — same as `governance.incidents`):

- `cadoc_documentos` — CADOC registry.
- `cadoc_tabelas`    — CADOC → silver tables (1:N).
- `regra_vinculos`   — rule link. Stores BOTH `rule_id` (stable) and
  `check_name` (the join key to DQX execution metrics), which fixes the silent
  drop of rules authored without an explicit `name`.

All deletes are soft (`is_ativo=false`); every read filters `is_ativo=true`.
Writes reuse the `governance.py` pattern (dedup pre-check → INSERT / dynamic
UPDATE via `db.execute_query`). Reads use the tolerant `execute_query_or_empty`.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db import (
    CATALOG,
    DQX_METRICS_TABLE,
    DQX_VALIDATION_RUNS_TABLE,
    SCHEMA_SILVER,
    USE_MOCK,
)
import cache
from data_base import PERIODICIDADES
from dqx_rules import PUBLISHED_RUN_FILTER, load_executed_rules
from db import execute_query as _execute_query
# Tolerant variant for reads: degrades to [] when a table doesn't exist yet.
from db import execute_query_or_empty as execute_query
from i18n import get_locale
from rc18_rule_meta import _DIM_NAMES, meta_for
from models import (
    CadocCreateRequest,
    CadocDocument,
    CadocListResponse,
    CadocTable,
    CadocTableAssociateRequest,
    CadocTablesResponse,
    CadocUpdateRequest,
    LinkableRule,
    LinkableRulesResponse,
    LinksResponse,
    RegraVinculo,
    RegraVinculoCreateRequest,
    RegraVinculoUpdateRequest,
    SchemaTable,
    SchemaTablesResponse,
)

router = APIRouter()

_DOCS = f"{CATALOG}.governance.cadoc_documentos"
_TBLS = f"{CATALOG}.governance.cadoc_tabelas"
_LINKS = f"{CATALOG}.governance.regra_vinculos"


async def execute_query_strict(query: str, params: dict | None = None) -> list[dict]:
    """Escrita: erro real sobe (ex. permissão negada) e o cache `links` é limpo
    — só neste worker; o outro vê a mudança ao vencer o prazo (`cache.TTL_S`)."""
    try:
        return await _execute_query(query, params)
    finally:
        cache.invalidate("links")

# Schemas the browser is allowed to list (data schemas the app SP can SELECT).
_BROWSABLE_SCHEMAS = {"silver", "bronze", "gold", "reference"}


def _validate_table_fqn(table_fqn: str) -> str:
    """Validate a written `table_fqn` to `{CATALOG}.<browsable_schema>.<table>`.

    Defense-in-depth against a stored value later reaching a query: even though
    all IN-lists are now parameterized, a stored FQN pointing at another
    catalog/schema is a data-integrity + least-privilege concern. Rejects
    anything outside the app's own catalog and allowlisted data schemas, and
    any table name that isn't a plain identifier.
    """
    fqn = (table_fqn or "").strip()
    parts = fqn.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail=f"table_fqn inválido (esperado catalog.schema.tabela): {table_fqn!r}")
    cat, schema, table = parts
    if cat != CATALOG:
        raise HTTPException(status_code=400, detail=f"table_fqn deve estar no catálogo {CATALOG}")
    if schema not in _BROWSABLE_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Schema não permitido: {schema}")
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise HTTPException(status_code=400, detail="Nome de tabela inválido")
    return fqn


def _in_clause(values: list[str], prefix: str) -> tuple[str, dict]:
    """Build a parameterized ``IN (:p0, :p1, ...)`` clause + params dict.

    Never interpolate values (esp. user-supplied `table_fqn`) directly into
    SQL — that is a SQL-injection vector. Returns ("(:p0,:p1)", {"p0":..}).
    Caller must guard against an empty list (produces "()", invalid SQL).
    """
    keys = [f"{prefix}{i}" for i in range(len(values))]
    placeholders = ",".join(f":{k}" for k in keys)
    return f"({placeholders})", {k: v for k, v in zip(keys, values)}


def _caller_email(request: Request) -> str:
    """Best-effort caller identity for the audit trail (mirrors governance.py)."""
    return request.headers.get("X-Forwarded-Email") or "unknown@bankcorp.com"


def _dim_name(dim: int | None) -> str:
    return _DIM_NAMES.get(int(dim), "") if dim else ""


# ── Mock fixtures ────────────────────────────────────────────────────────────
# Mirror the seeded workspace state so the demo build (USE_MOCK_BACKEND=true)
# renders a realistic screen without a Databricks connection.
_MOCK_CADOC_TABLES: dict[str, list[str]] = {
    "3040": [
        f"{CATALOG}.silver.scr3040_operacoes",
        f"{CATALOG}.silver.scr3040_clientes",
        f"{CATALOG}.silver.scr3040_garantias",
        f"{CATALOG}.silver.scr3040_vencimentos",
        f"{CATALOG}.silver.scr3040_cont_4966",
    ],
    "3050": [f"{CATALOG}.silver.scr3050"],
}
_MOCK_CADOCS: list[dict] = [
    {"documento": "3040", "nome": "SCR 3040 - Operações de crédito individualizadas",
     "descricao": "Documento SCR 3040 — operações de crédito detalhadas (130+ campos, IPOC).",
     "leiaute_versao": "V1", "is_ativo": True, "periodicidade": "mensal", "grupo": "SCR"},
    {"documento": "3050", "nome": "SCR 3050 - Estoque mensal agregado",
     "descricao": "Documento SCR 3050 — dados agregados de crédito (TXB/XML).",
     "leiaute_versao": "V11", "is_ativo": True, "periodicidade": "mensal", "grupo": "SCR"},
]
# In-memory link store for mock mode (module-level; resets on reload).
_MOCK_LINKS: list[dict] = []


def _mock_cadoc(doc: dict) -> CadocDocument:
    documento = doc["documento"]
    return CadocDocument(
        table_count=len(_MOCK_CADOC_TABLES.get(documento, [])),
        rule_count=sum(1 for l in _MOCK_LINKS if l.get("documento") == documento and l.get("is_ativo", True)),
        **doc,
    )


def _check_periodicidade(value: str | None) -> None:
    if value and value not in PERIODICIDADES:
        raise HTTPException(
            status_code=400,
            detail=f"periodicidade inválida: {value!r} (use {', '.join(PERIODICIDADES)})",
        )


def _str_or_none(value) -> str | None:
    # `SELECT d.*` devolve TIMESTAMP como datetime; o modelo espera str.
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


# ── CADOC CRUD ───────────────────────────────────────────────────────────────

@router.get("/cadocs", response_model=CadocListResponse)
async def list_cadocs(locale: str = Depends(get_locale)):
    """List registered CADOCs with table + rule counts."""
    if USE_MOCK:
        return CadocListResponse(cadocs=[_mock_cadoc(d) for d in _MOCK_CADOCS])

    # `d.*`: periodicidade/grupo só existem depois do setup_reference_tables, e
    # listar colunas inexistentes esvaziaria a tela de quem atualizou só o app.
    rows = await execute_query(
        "SELECT d.*, "
        f"  (SELECT COUNT(*) FROM {_TBLS} t WHERE t.documento = d.documento AND t.is_ativo) AS table_count, "
        f"  (SELECT COUNT(*) FROM {_LINKS} l WHERE l.documento = d.documento AND l.is_ativo) AS rule_count "
        f"FROM {_DOCS} d WHERE d.is_ativo ORDER BY d.documento",
        {},
    )
    return CadocListResponse(cadocs=[
        CadocDocument(
            documento=r["documento"], nome=r["nome"], descricao=r.get("descricao"),
            leiaute_versao=r.get("leiaute_versao"), is_ativo=bool(r.get("is_ativo")),
            periodicidade=r.get("periodicidade"), grupo=r.get("grupo"),
            table_count=int(r.get("table_count") or 0), rule_count=int(r.get("rule_count") or 0),
            created_at=_str_or_none(r.get("created_at")), created_by=r.get("created_by"),
            updated_at=_str_or_none(r.get("updated_at")), updated_by=r.get("updated_by"),
        )
        for r in rows
    ])


@router.post("/cadocs", response_model=CadocDocument, status_code=201)
async def create_cadoc(body: CadocCreateRequest, request: Request):
    """Register a new CADOC. 409 when `documento` already exists (active)."""
    documento = (body.documento or "").strip()
    if not documento:
        raise HTTPException(status_code=400, detail="documento é obrigatório")
    _check_periodicidade(body.periodicidade)
    actor = _caller_email(request)

    if USE_MOCK:
        if any(d["documento"] == documento for d in _MOCK_CADOCS):
            raise HTTPException(status_code=409, detail={"code": "cadoc_exists", "message": "CADOC já cadastrado.", "documento": documento})
        doc = {"documento": documento, "nome": body.nome, "descricao": body.descricao,
               "leiaute_versao": body.leiaute_versao, "is_ativo": True,
               "periodicidade": body.periodicidade, "grupo": body.grupo}
        _MOCK_CADOCS.append(doc)
        return _mock_cadoc(doc)

    dedup = await execute_query(
        f"SELECT documento FROM {_DOCS} WHERE documento = :documento AND is_ativo LIMIT 1",
        {"documento": documento},
    )
    if dedup:
        raise HTTPException(status_code=409, detail={"code": "cadoc_exists", "message": "CADOC já cadastrado.", "documento": documento})

    # periodicidade/grupo só entram quando informados: sem o setup novo a coluna
    # não existe, e o cadastro sem elas continua funcionando.
    extra = {f: getattr(body, f) for f in ("periodicidade", "grupo") if getattr(body, f)}
    await execute_query_strict(
        f"INSERT INTO {_DOCS} (documento, nome, descricao, leiaute_versao, is_ativo, "
        f"  created_at, created_by, updated_at, updated_by{''.join(f', {f}' for f in extra)}) VALUES ("
        "  :documento, :nome, :descricao, :leiaute_versao, true, "
        f"  current_timestamp(), :actor, current_timestamp(), :actor{''.join(f', :{f}' for f in extra)})",
        {"documento": documento, "nome": body.nome, "descricao": body.descricao,
         "leiaute_versao": body.leiaute_versao, "actor": actor, **extra},
    )
    return CadocDocument(documento=documento, nome=body.nome, descricao=body.descricao,
                         leiaute_versao=body.leiaute_versao, is_ativo=True,
                         periodicidade=body.periodicidade, grupo=body.grupo,
                         created_by=actor, updated_by=actor)


@router.patch("/cadocs/{documento}", response_model=CadocDocument)
async def update_cadoc(documento: str, body: CadocUpdateRequest, request: Request):
    """Update mutable CADOC fields. Dynamic SET like governance.py PATCH."""
    actor = _caller_email(request)
    _check_periodicidade(body.periodicidade)
    if USE_MOCK:
        for d in _MOCK_CADOCS:
            if d["documento"] == documento:
                for f in ("nome", "descricao", "leiaute_versao", "is_ativo", "periodicidade", "grupo"):
                    v = getattr(body, f)
                    if v is not None:
                        d[f] = v
                return _mock_cadoc(d)
        raise HTTPException(status_code=404, detail="CADOC não encontrado")

    sets, params = [], {"documento": documento, "actor": actor}
    for f in ("nome", "descricao", "leiaute_versao", "is_ativo", "periodicidade", "grupo"):
        v = getattr(body, f)
        if v is not None:
            sets.append(f"{f} = :{f}")
            params[f] = v
    if not sets:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    sets += ["updated_at = current_timestamp()", "updated_by = :actor"]
    await execute_query_strict(
        f"UPDATE {_DOCS} SET {', '.join(sets)} WHERE documento = :documento", params,
    )
    rows = await execute_query(
        f"SELECT * FROM {_DOCS} WHERE documento = :documento LIMIT 1", {"documento": documento},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="CADOC não encontrado")
    r = rows[0]
    return CadocDocument(documento=r["documento"], nome=r["nome"], descricao=r.get("descricao"),
                         leiaute_versao=r.get("leiaute_versao"), is_ativo=bool(r.get("is_ativo")),
                         periodicidade=r.get("periodicidade"), grupo=r.get("grupo"))


@router.delete("/cadocs/{documento}", status_code=204)
async def delete_cadoc(documento: str, request: Request):
    """Soft-delete a CADOC. Blocked (409) while it still has active links."""
    actor = _caller_email(request)
    if USE_MOCK:
        if any(l.get("documento") == documento and l.get("is_ativo", True) for l in _MOCK_LINKS):
            raise HTTPException(status_code=409, detail={"code": "cadoc_has_links", "message": "CADOC possui vínculos ativos."})
        _MOCK_CADOCS[:] = [d for d in _MOCK_CADOCS if d["documento"] != documento]
        _MOCK_CADOC_TABLES.pop(documento, None)
        return

    open_links = await execute_query(
        f"SELECT vinculo_id FROM {_LINKS} WHERE documento = :documento AND is_ativo LIMIT 1",
        {"documento": documento},
    )
    if open_links:
        raise HTTPException(status_code=409, detail={"code": "cadoc_has_links", "message": "CADOC possui vínculos ativos; remova-os antes."})
    await execute_query_strict(
        f"UPDATE {_DOCS} SET is_ativo = false, updated_at = current_timestamp(), updated_by = :actor "
        "WHERE documento = :documento", {"documento": documento, "actor": actor},
    )
    await execute_query_strict(
        f"UPDATE {_TBLS} SET is_ativo = false, updated_at = current_timestamp(), updated_by = :actor "
        "WHERE documento = :documento", {"documento": documento, "actor": actor},
    )


# ── CADOC ↔ tables ───────────────────────────────────────────────────────────

@router.get("/cadocs/{documento}/tables", response_model=CadocTablesResponse)
async def list_cadoc_tables(documento: str):
    """List silver tables associated to a CADOC."""
    if USE_MOCK:
        return CadocTablesResponse(documento=documento, tables=[
            CadocTable(documento=documento, table_fqn=t)
            for t in _MOCK_CADOC_TABLES.get(documento, [])
        ])
    rows = await execute_query(
        f"SELECT documento, table_fqn FROM {_TBLS} WHERE documento = :documento AND is_ativo "
        "ORDER BY table_fqn", {"documento": documento},
    )
    return CadocTablesResponse(documento=documento, tables=[
        CadocTable(documento=r["documento"], table_fqn=r["table_fqn"]) for r in rows
    ])


@router.post("/cadocs/{documento}/tables", response_model=CadocTable, status_code=201)
async def associate_cadoc_table(documento: str, body: CadocTableAssociateRequest, request: Request):
    """Associate a silver table to a CADOC (409 on duplicate)."""
    actor = _caller_email(request)
    table_fqn = (body.table_fqn or "").strip()
    if not table_fqn:
        raise HTTPException(status_code=400, detail="table_fqn é obrigatório")
    table_fqn = _validate_table_fqn(table_fqn)

    if USE_MOCK:
        cur = _MOCK_CADOC_TABLES.setdefault(documento, [])
        if table_fqn in cur:
            raise HTTPException(status_code=409, detail={"code": "table_linked", "message": "Tabela já associada."})
        cur.append(table_fqn)
        return CadocTable(documento=documento, table_fqn=table_fqn)

    dedup = await execute_query(
        f"SELECT table_fqn FROM {_TBLS} WHERE documento = :documento AND table_fqn = :table_fqn AND is_ativo LIMIT 1",
        {"documento": documento, "table_fqn": table_fqn},
    )
    if dedup:
        raise HTTPException(status_code=409, detail={"code": "table_linked", "message": "Tabela já associada a este CADOC."})
    await execute_query_strict(
        f"INSERT INTO {_TBLS} (documento, table_fqn, is_ativo, created_at, created_by, updated_at, updated_by) "
        "VALUES (:documento, :table_fqn, true, current_timestamp(), :actor, current_timestamp(), :actor)",
        {"documento": documento, "table_fqn": table_fqn, "actor": actor},
    )
    return CadocTable(documento=documento, table_fqn=table_fqn)


@router.delete("/cadocs/{documento}/tables", status_code=204)
async def disassociate_cadoc_table(documento: str, request: Request, table_fqn: str = Query(...)):
    """Soft-disassociate a table from a CADOC."""
    actor = _caller_email(request)
    if USE_MOCK:
        cur = _MOCK_CADOC_TABLES.get(documento, [])
        _MOCK_CADOC_TABLES[documento] = [t for t in cur if t != table_fqn]
        return
    await execute_query_strict(
        f"UPDATE {_TBLS} SET is_ativo = false, updated_at = current_timestamp(), updated_by = :actor "
        "WHERE documento = :documento AND table_fqn = :table_fqn",
        {"documento": documento, "table_fqn": table_fqn, "actor": actor},
    )


# ── Schema browsing ──────────────────────────────────────────────────────────

@router.get("/schema-tables", response_model=SchemaTablesResponse)
async def browse_schema_tables(
    schema: str = Query("silver"),
    search: str | None = Query(None),
):
    """Browse tables in a data schema of `${CATALOG}` (information_schema).

    Restricted to the granted data schemas. Each table is annotated with the
    CADOC it's already linked to (if any), so the UI can disable/badge it.
    """
    schema = (schema or "silver").strip()
    if schema not in _BROWSABLE_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Schema não navegável: {schema}")

    if USE_MOCK:
        base = [f"scr3040_operacoes", "scr3040_clientes", "scr3040_garantias",
                "scr3040_vencimentos", "scr3040_cont_4966", "scr3050"]
        linked = {t: d for d, ts in _MOCK_CADOC_TABLES.items() for t in ts}
        tables = []
        for name in base:
            if search and search.lower() not in name.lower():
                continue
            fqn = f"{CATALOG}.{schema}.{name}"
            tables.append(SchemaTable(table_fqn=fqn, table_schema=schema, table_name=name,
                                      already_linked_documento=linked.get(fqn)))
        return SchemaTablesResponse(schema_name=schema, tables=tables)

    rows = await execute_query(
        "SELECT table_schema, table_name "
        f"FROM {CATALOG}.information_schema.tables "
        "WHERE table_schema = :schema "
        "  AND (:search IS NULL OR lower(table_name) LIKE '%' || lower(:search) || '%') "
        "ORDER BY table_name",
        {"schema": schema, "search": search},
    )
    # Which of these are already linked (active), to annotate the browser.
    linked_rows = await execute_query(
        f"SELECT table_fqn, documento FROM {_TBLS} WHERE is_ativo", {},
    )
    linked = {r["table_fqn"]: r["documento"] for r in linked_rows}
    tables = []
    for r in rows:
        fqn = f"{CATALOG}.{r['table_schema']}.{r['table_name']}"
        tables.append(SchemaTable(
            table_fqn=fqn, table_schema=r["table_schema"], table_name=r["table_name"],
            already_linked_documento=linked.get(fqn),
        ))
    return SchemaTablesResponse(schema_name=schema, tables=tables)


# ── Linkable rules (DQX rules + effective check_name + link status) ──────────

def _parse_check_def(chk_raw) -> list[dict]:
    """Coerce a rule row's check (dict, or JSON str) into check dicts."""
    try:
        parsed = json.loads(chk_raw) if isinstance(chk_raw, str) else (chk_raw or [])
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return parsed if isinstance(parsed, list) else []


async def _effective_names_by_table(table_fqns: list[str]) -> dict[str, list[str]]:
    """For each table_fqn, the check_names observed in its latest approved run.

    These are the runtime-resolved names (incl. auto-derived ones like
    `parte_not_in_range`) that the user confirms when linking a rule.
    """
    if not table_fqns:
        return {}
    in_tables, tbl_params = _in_clause(table_fqns, "t")
    runs = await execute_query(
        "WITH ranked AS ("
        "  SELECT run_id, source_table_fqn, "
        "         ROW_NUMBER() OVER (PARTITION BY source_table_fqn ORDER BY created_at DESC) AS rn "
        f"  FROM {DQX_VALIDATION_RUNS_TABLE} "
        f"  WHERE {PUBLISHED_RUN_FILTER} AND source_table_fqn IN {in_tables}"
        ") SELECT run_id, source_table_fqn FROM ranked WHERE rn = 1",
        tbl_params,
    )
    if not runs:
        return {}
    run_to_table = {r["run_id"]: r["source_table_fqn"] for r in runs}
    in_runs, run_params = _in_clause(list(run_to_table), "r")
    metrics = await execute_query(
        "SELECT run_id, metric_value AS check_metrics_json "
        f"FROM {DQX_METRICS_TABLE} "
        f"WHERE metric_name = 'check_metrics' AND run_id IN {in_runs}",
        run_params,
    )
    out: dict[str, list[str]] = {}
    for m in metrics:
        table = run_to_table.get(m["run_id"])
        if not table:
            continue
        try:
            cms = json.loads(m["check_metrics_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(cms, list):
            continue
        names = [c.get("check_name") for c in cms if isinstance(c, dict) and c.get("check_name")]
        out.setdefault(table, [])
        for n in names:
            if n not in out[table]:
                out[table].append(n)
    return out


def _vinculo_from_row(r: dict) -> RegraVinculo:
    dim = r.get("dimensao_r18")
    dim = int(dim) if dim is not None else None
    return RegraVinculo(
        vinculo_id=r["vinculo_id"], check_name=r["check_name"], rule_id=r.get("rule_id"),
        table_fqn=r["table_fqn"], documento=r.get("documento"), dimensao_r18=dim,
        dimension_name=_dim_name(dim), critica_id=r.get("critica_id"),
        nivel_verificacao=(int(r["nivel_verificacao"]) if r.get("nivel_verificacao") is not None else None),
        descricao=r.get("descricao"), is_ativo=bool(r.get("is_ativo", True)),
    )


@router.get("/rules", response_model=LinkableRulesResponse)
async def list_linkable_rules(
    document: str | None = Query(None),
    table_fqn: str | None = Query(None),
    linked: bool | None = Query(None),
):
    """List DQX rules for a CADOC's tables, annotated with effective check_names
    (from the latest run) and the current link (if any)."""
    if USE_MOCK:
        rules = [
            LinkableRule(
                key=f"{CATALOG}.silver.scr3040_clientes|b77ca2c5f49a4b34",
                rule_id="b77ca2c5f49a4b34", definition_name="", function="is_in_range",
                arguments_summary="column=parte, min=1, max=1",
                table_fqn=f"{CATALOG}.silver.scr3040_clientes", documento="3040",
                effective_check_names=["parte_not_in_range"],
                current_link=next((_vinculo_from_row(l) for l in _MOCK_LINKS
                                   if l["table_fqn"] == f"{CATALOG}.silver.scr3040_clientes"
                                   and l["check_name"] == "parte_not_in_range" and l.get("is_ativo", True)), None),
            ),
        ]
        if table_fqn:
            rules = [r for r in rules if r.table_fqn == table_fqn]
        if document:
            rules = [r for r in rules if r.documento == document]
        if linked is not None:
            rules = [r for r in rules if (r.current_link is not None) == linked]
        return LinkableRulesResponse(rules=rules)

    # Resolve the target table set from cadoc_tabelas.
    table_map = await execute_query(
        f"SELECT documento, table_fqn FROM {_TBLS} WHERE is_ativo", {},
    )
    doc_by_table = {r["table_fqn"]: r["documento"] for r in table_map}
    if table_fqn:
        target_tables = [table_fqn]
    elif document:
        target_tables = [t for t, d in doc_by_table.items() if d == document]
    else:
        target_tables = list(doc_by_table)
    if not target_tables:
        return LinkableRulesResponse(rules=[])

    # Regras em vigor dessas tabelas (as que rodaram — ver dqx_rules). Regra
    # aprovada que ainda não rodou só aparece depois do primeiro run.
    rule_rows = await load_executed_rules(target_tables)
    eff_names = await _effective_names_by_table(target_tables)
    link_rows = await execute_query(
        f"SELECT vinculo_id, check_name, rule_id, table_fqn, documento, dimensao_r18, "
        f"critica_id, nivel_verificacao, descricao, is_ativo FROM {_LINKS} WHERE is_ativo", {},
    )
    links_by_rule = {r["rule_id"]: r for r in link_rows if r.get("rule_id")}
    links_by_pair = {(r["table_fqn"], r["check_name"]): r for r in link_rows}

    out: list[LinkableRule] = []
    seen_keys: set[str] = set()
    for rr in rule_rows:
        tfqn = rr.get("table_fqn") or ""
        for chk in _parse_check_def(rr.get("checks")):
            if not isinstance(chk, dict):
                continue
            inner = chk.get("check") or {}
            args = inner.get("arguments") or {}
            def_name = chk.get("name") or (args.get("name") if isinstance(args, dict) else None) or ""
            func = inner.get("function") or ""
            arg_summary = ", ".join(f"{k}={v}" for k, v in list(args.items())[:4]) if isinstance(args, dict) else ""
            candidates = eff_names.get(tfqn, [])
            # Current link: prefer explicit name, else rule_id, else any observed name.
            cur = links_by_pair.get((tfqn, def_name)) if def_name else None
            if not cur:
                cur = links_by_rule.get(rr.get("rule_id"))
            if not cur:
                for c in candidates:
                    if (tfqn, c) in links_by_pair:
                        cur = links_by_pair[(tfqn, c)]
                        break
            # Sem vínculo explícito: derive a dimensão que a tela de Críticas/
            # scorecard já usa (tag `user_metadata.dimensao_r18` do check → RC18
            # hard-code → default). Isso sinaliza na UI "via tag" em vez de
            # "Não vinculada", eliminando a impressão contraditória entre telas.
            tag_dim = tag_dim_name = None
            if not cur:
                um = chk.get("user_metadata") if isinstance(chk, dict) else None
                tag_meta = meta_for(def_name or None, table_fqn=tfqn, user_metadata=um)
                if tag_meta["dimension_r18"]:
                    tag_dim = tag_meta["dimension_r18"]
                    tag_dim_name = tag_meta["dimension_name"]
            digest = hashlib.sha1(json.dumps(chk, sort_keys=True, default=str).encode()).hexdigest()[:16]
            key = f"{tfqn}|{digest}"
            n = 1
            while key in seen_keys:  # definição idêntica repetida: a tela não pode ter chave igual
                n += 1
                key = f"{tfqn}|{digest}#{n}"
            seen_keys.add(key)
            out.append(LinkableRule(
                key=key, rule_id=rr.get("rule_id") or "", definition_name=def_name, function=func,
                arguments_summary=arg_summary[:200], table_fqn=tfqn,
                documento=doc_by_table.get(tfqn), effective_check_names=candidates,
                current_link=_vinculo_from_row(cur) if cur else None,
                tag_dimension_r18=tag_dim, tag_dimension_name=tag_dim_name,
            ))
    if linked is not None:
        out = [r for r in out if (r.current_link is not None) == linked]
    return LinkableRulesResponse(rules=out)


# ── Link CRUD ────────────────────────────────────────────────────────────────

@router.get("/links", response_model=LinksResponse)
async def list_links(
    document: str | None = Query(None),
    dimensao_r18: int | None = Query(None),
):
    """List active rule links, optionally filtered by CADOC / dimension."""
    if USE_MOCK:
        links = [_vinculo_from_row(l) for l in _MOCK_LINKS if l.get("is_ativo", True)]
        if document:
            links = [l for l in links if l.documento == document]
        if dimensao_r18:
            links = [l for l in links if l.dimensao_r18 == dimensao_r18]
        return LinksResponse(total=len(links), links=links)

    where = ["is_ativo"]
    params: dict = {}
    if document:
        where.append("documento = :documento")
        params["documento"] = document
    if dimensao_r18:
        where.append("dimensao_r18 = :dimensao_r18")
        params["dimensao_r18"] = dimensao_r18
    rows = await execute_query(
        "SELECT vinculo_id, check_name, rule_id, table_fqn, documento, dimensao_r18, "
        f"critica_id, nivel_verificacao, descricao, is_ativo FROM {_LINKS} "
        f"WHERE {' AND '.join(where)} ORDER BY documento, table_fqn, check_name",
        params,
    )
    links = [_vinculo_from_row(r) for r in rows]
    return LinksResponse(total=len(links), links=links)


@router.post("/links", response_model=RegraVinculo, status_code=201)
async def create_link(body: RegraVinculoCreateRequest, request: Request):
    """Create a rule link. Dedup on (table_fqn, check_name); 409 with existing id."""
    actor = _caller_email(request)
    check_name = (body.check_name or "").strip()
    table_fqn = (body.table_fqn or "").strip()
    if not check_name or not table_fqn:
        raise HTTPException(status_code=400, detail="check_name e table_fqn são obrigatórios")
    table_fqn = _validate_table_fqn(table_fqn)
    if not (1 <= int(body.dimensao_r18) <= 12):
        raise HTTPException(status_code=400, detail="dimensao_r18 deve estar entre 1 e 12")

    if USE_MOCK:
        if any(l["table_fqn"] == table_fqn and l["check_name"] == check_name and l.get("is_ativo", True) for l in _MOCK_LINKS):
            raise HTTPException(status_code=409, detail={"code": "link_exists", "message": "Vínculo já existe."})
        vid = str(uuid.uuid4())
        row = {"vinculo_id": vid, "check_name": check_name, "rule_id": body.rule_id,
               "table_fqn": table_fqn, "documento": body.documento or _mock_doc_for(table_fqn),
               "dimensao_r18": body.dimensao_r18, "critica_id": body.critica_id,
               "nivel_verificacao": body.nivel_verificacao, "descricao": body.descricao, "is_ativo": True}
        _MOCK_LINKS.append(row)
        return _vinculo_from_row(row)

    dedup = await execute_query(
        f"SELECT vinculo_id FROM {_LINKS} WHERE table_fqn = :table_fqn AND check_name = :check_name AND is_ativo LIMIT 1",
        {"table_fqn": table_fqn, "check_name": check_name},
    )
    if dedup:
        existing = dedup[0]["vinculo_id"]
        raise HTTPException(status_code=409, detail={
            "code": "link_exists", "message": "Já existe um vínculo para esta regra nesta tabela.",
            "vinculo_id": existing, "existing_vinculo_id": existing,
        })

    # Resolve documento from cadoc_tabelas if not supplied.
    documento = body.documento
    if not documento:
        drows = await execute_query(
            f"SELECT documento FROM {_TBLS} WHERE table_fqn = :table_fqn AND is_ativo LIMIT 1",
            {"table_fqn": table_fqn},
        )
        documento = drows[0]["documento"] if drows else None

    vid = str(uuid.uuid4())
    await execute_query_strict(
        f"INSERT INTO {_LINKS} (vinculo_id, check_name, rule_id, table_fqn, documento, "
        "  dimensao_r18, critica_id, nivel_verificacao, descricao, is_ativo, "
        "  created_at, created_by, updated_at, updated_by) VALUES ("
        "  :vinculo_id, :check_name, :rule_id, :table_fqn, :documento, "
        "  :dimensao_r18, :critica_id, :nivel_verificacao, :descricao, true, "
        "  current_timestamp(), :actor, current_timestamp(), :actor)",
        {"vinculo_id": vid, "check_name": check_name, "rule_id": body.rule_id,
         "table_fqn": table_fqn, "documento": documento, "dimensao_r18": body.dimensao_r18,
         "critica_id": body.critica_id, "nivel_verificacao": body.nivel_verificacao,
         "descricao": body.descricao, "actor": actor},
    )
    return RegraVinculo(
        vinculo_id=vid, check_name=check_name, rule_id=body.rule_id, table_fqn=table_fqn,
        documento=documento, dimensao_r18=body.dimensao_r18, dimension_name=_dim_name(body.dimensao_r18),
        critica_id=body.critica_id, nivel_verificacao=body.nivel_verificacao,
        descricao=body.descricao, is_ativo=True,
    )


@router.patch("/links/{vinculo_id}", response_model=RegraVinculo)
async def update_link(vinculo_id: str, body: RegraVinculoUpdateRequest, request: Request):
    """Update a link (dynamic SET). dimensao_r18 validated to 1..12 when present."""
    actor = _caller_email(request)
    if body.dimensao_r18 is not None and not (1 <= int(body.dimensao_r18) <= 12):
        raise HTTPException(status_code=400, detail="dimensao_r18 deve estar entre 1 e 12")

    _UPDATABLE = ("check_name", "documento", "dimensao_r18", "critica_id", "nivel_verificacao", "descricao", "is_ativo")
    if USE_MOCK:
        for l in _MOCK_LINKS:
            if l["vinculo_id"] == vinculo_id:
                for f in _UPDATABLE:
                    v = getattr(body, f)
                    if v is not None:
                        l[f] = v
                return _vinculo_from_row(l)
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")

    sets, params = [], {"vinculo_id": vinculo_id, "actor": actor}
    for f in _UPDATABLE:
        v = getattr(body, f)
        if v is not None:
            sets.append(f"{f} = :{f}")
            params[f] = v
    if not sets:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    sets += ["updated_at = current_timestamp()", "updated_by = :actor"]
    await execute_query_strict(
        f"UPDATE {_LINKS} SET {', '.join(sets)} WHERE vinculo_id = :vinculo_id", params,
    )
    rows = await execute_query(
        "SELECT vinculo_id, check_name, rule_id, table_fqn, documento, dimensao_r18, "
        f"critica_id, nivel_verificacao, descricao, is_ativo FROM {_LINKS} "
        "WHERE vinculo_id = :vinculo_id LIMIT 1", {"vinculo_id": vinculo_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return _vinculo_from_row(rows[0])


@router.delete("/links/{vinculo_id}", status_code=204)
async def delete_link(vinculo_id: str, request: Request):
    """Soft-delete a link."""
    actor = _caller_email(request)
    if USE_MOCK:
        for l in _MOCK_LINKS:
            if l["vinculo_id"] == vinculo_id:
                l["is_ativo"] = False
        return
    await execute_query_strict(
        f"UPDATE {_LINKS} SET is_ativo = false, updated_at = current_timestamp(), updated_by = :actor "
        "WHERE vinculo_id = :vinculo_id", {"vinculo_id": vinculo_id, "actor": actor},
    )


def _mock_doc_for(table_fqn: str) -> str | None:
    for d, ts in _MOCK_CADOC_TABLES.items():
        if table_fqn in ts:
            return d
    return None
