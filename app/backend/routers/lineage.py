"""Lineage endpoints: graph and column-level lineage.

Real mode combines two sources:
  1. BYOL (Bring Your Own Lineage) — External Metadata + External Lineage APIs.
     Covers pre-Databricks sources (Oracle, DB2, Informatica) and post-Databricks
     destinations (BACEN validators, STA/CADIP). Registered by setup_byol_lineage.py.
  2. UC automatic lineage — system.access.table_lineage / column_lineage.
     Covers Bronze -> Silver -> Gold DLT transformations.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Query

import external_lineage_store as store
from db import CATALOG, LINEAGE_OBJECT_PREFIX, USE_MOCK
from models import (
    ColumnLineageResponse,
    ColumnMapping,
    ExternalLineageEndpoint,
    ExternalLineageRelationship,
    ExternalMetadataObject,
    ExternalSource,
    LineageEdge,
    LineageGraphResponse,
    LineageNode,
    LineageNodeMetadata,
    UpstreamColumn,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _uc_layer(full_name: str) -> str:
    parts = full_name.split(".")
    if len(parts) >= 2:
        schema = parts[-2].lower()
        for layer in ("bronze", "silver", "gold", "quality", "landing", "reference"):
            if layer in schema:
                return layer
    return "unknown"


def _short_label(full_name: str) -> str:
    return full_name.split(".")[-1]


# ---------------------------------------------------------------------------
# External object → LineageNode. Layer/system/ingestion are DERIVED FROM the
# object's own ``properties`` (customer-editable via the app form), not from a
# hardcoded lookup — so any topology the customer registers renders correctly.
# ---------------------------------------------------------------------------

def _ext_object_to_node(obj: ExternalMetadataObject) -> LineageNode:
    props = obj.properties or {}
    layer = store.derive_layer(props, obj.entity_type)
    return LineageNode(
        id=obj.name,
        label=props.get("label") or obj.name,
        type=store.derive_node_type(layer, obj.entity_type),
        layer=layer,
        system=props.get("sistema") or props.get("source_system") or obj.system_type,
        system_type=obj.system_type or "OTHER",
        ingestion_mode=props.get("ingestion_mode"),
        properties=props,
        metadata=LineageNodeMetadata(
            connection=obj.url,
            update_frequency=props.get("update_mode") or props.get("update_frequency"),
        ),
    )


def _uc_node(fqn: str, catalog: str) -> LineageNode:
    return LineageNode(
        id=fqn, label=_short_label(fqn), type="table",
        layer=_uc_layer(fqn),
        catalog=fqn.split(".")[0] if "." in fqn else None,
        metadata=LineageNodeMetadata(),
    )


def _endpoint_id(ep: ExternalLineageEndpoint) -> str | None:
    return ep.external_metadata_name or ep.table_name


def _rel_to_edge(rel: ExternalLineageRelationship) -> LineageEdge | None:
    src, tgt = _endpoint_id(rel.source), _endpoint_id(rel.target)
    if not src or not tgt:
        return None
    props = rel.properties or {}
    label = props.get("mechanism") or props.get("transform") or props.get("label")
    return LineageEdge(
        source=src, target=tgt, type="external_lineage", label=label,
        column_mappings=list(rel.columns) if rel.columns else None,
    )


# Internal medallion edges (bronze → silver → gold). These are Databricks-native
# (UC automatic lineage) and are NOT part of the external store; in mock mode we
# synthesize them so the graph tells the full end-to-end story.
def _mock_uc_automatic(catalog: str) -> tuple[list[LineageNode], list[LineageEdge]]:
    def n(schema: str, table: str, **md) -> LineageNode:
        return LineageNode(
            id=f"{catalog}.{schema}.{table}", label=table, type="table",
            layer=schema, catalog=catalog, metadata=LineageNodeMetadata(**md),
        )
    nodes = [
        n("bronze", "raw_3040_doc", row_count=1, last_updated="2026-03-31T23:15:00Z"),
        n("silver", "scr3040_operacoes", row_count=1, last_updated="2026-03-31T01:30:00Z", expectations_pass_rate=99.9),
        n("silver", "scr3040_clientes", row_count=1, last_updated="2026-03-31T01:30:00Z"),
        n("gold", "posicao_3040", row_count=0, last_updated="2026-03-31T04:00:00Z"),
    ]
    def e(s_schema, s_tbl, t_schema, t_tbl, label):
        return LineageEdge(source=f"{catalog}.{s_schema}.{s_tbl}", target=f"{catalog}.{t_schema}.{t_tbl}",
                           type="uc_automatic", label=label)
    edges = [
        e("bronze", "raw_3040_doc", "silver", "scr3040_operacoes", "DLT silver"),
        e("bronze", "raw_3040_doc", "silver", "scr3040_clientes", "DLT silver"),
        e("silver", "scr3040_operacoes", "gold", "posicao_3040", "DLT gold"),
    ]
    return nodes, edges


# ---------------------------------------------------------------------------
# Mock graph — built from the shared external-lineage store so that objects and
# relationships created via the app form appear in the graph immediately.
# ---------------------------------------------------------------------------

def _build_mock(catalog: str) -> LineageGraphResponse:
    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []

    # External metadata objects (customer-managed, from the store)
    for obj in store.list_metadata(catalog):
        nodes[obj.name] = _ext_object_to_node(obj)

    # External lineage relationships (BYOL edges) + their UC table endpoints
    for rel in store.list_relationships(catalog):
        edge = _rel_to_edge(rel)
        if not edge:
            continue
        for ep in (rel.source, rel.target):
            if ep.table_name and ep.table_name not in nodes:
                nodes[ep.table_name] = _uc_node(ep.table_name, catalog)
        edges.append(edge)

    # Internal medallion (UC automatic) — synthesized for the demo story
    uc_nodes, uc_edges = _mock_uc_automatic(catalog)
    for un in uc_nodes:
        nodes.setdefault(un.id, un)
    edges.extend(uc_edges)

    return LineageGraphResponse(nodes=list(nodes.values()), edges=edges)


# ---------------------------------------------------------------------------
# Real mode: merge BYOL + UC automatic lineage
# ---------------------------------------------------------------------------

async def _fetch_real_lineage(catalog: str) -> LineageGraphResponse:
    from databricks.sdk import WorkspaceClient
    from db import execute_query_or_empty as execute_query

    w = WorkspaceClient()
    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []

    def _ensure_uc_node(fqn: str) -> None:
        if fqn not in nodes:
            nodes[fqn] = _uc_node(fqn, catalog)

    # 1 + 2. BYOL external metadata + relationships (namespaced to rc18_*).
    #    Isolated so ANY failure here (e.g. an older databricks-sdk without the
    #    external-lineage endpoints, or missing privileges) NEVER blocks the UC
    #    CADOC lineage below — that was the bug that left the graph blank. All
    #    calls go through the REST api_client, so there is no SDK-version symbol
    #    dependency.
    try:
        _add_byol_from_rest(w, nodes, edges)
    except Exception as e:  # noqa: BLE001
        logger.warning("BYOL external lineage unavailable (skipping): %s", e)

    # 3. UC automatic lineage, ANCHORED on the CADOC-linked tables.
    #
    #    The tables shown are the ones bound to a CADOC in the "Vínculo de
    #    Regras" module (governance.cadoc_tabelas) AND that exist, then their
    #    medallion neighbors (bronze upstream, gold downstream). We expand from
    #    those anchors via the REST table-lineage API instead of
    #    ``system.access.table_lineage`` because the system table requires a
    #    special grant only account admins hold (the app SP can't read it, so the
    #    query returned empty → blank graph). The REST API only needs SELECT on
    #    the table, which the app SP already has.
    anchor_tables = await _cadoc_anchor_tables(catalog, execute_query)
    for fqn in anchor_tables:
        _ensure_uc_node(fqn)

    seen_uc_edges: set[tuple[str, str]] = set()
    # One hop up and down from each anchor covers bronze -> silver -> gold.
    for fqn in list(anchor_tables):
        for direction in ("upstream", "downstream"):
            for neighbor in _rest_table_lineage(w, fqn, direction):
                if not _is_relevant_uc_table(neighbor, catalog):
                    continue
                if neighbor == fqn:
                    continue  # REST API can list a table as its own neighbor
                src, tgt = (neighbor, fqn) if direction == "upstream" else (fqn, neighbor)
                if (src, tgt) in seen_uc_edges:
                    continue
                seen_uc_edges.add((src, tgt))
                _ensure_uc_node(src)
                _ensure_uc_node(tgt)
                edges.append(LineageEdge(source=src, target=tgt, type="uc_automatic", label="pipeline"))

    return LineageGraphResponse(nodes=list(nodes.values()), edges=edges)


# ---------------------------------------------------------------------------
# UC lineage helpers (real mode) — anchor on CADOC tables + REST table-lineage
# ---------------------------------------------------------------------------

# External Metadata / External Lineage REST endpoints. Used directly (not the
# typed SDK) so the code works regardless of the installed databricks-sdk
# version — older SDKs lack the ExternalLineage* dataclasses, and importing them
# at call time raised ImportError that blanked the whole graph.
_EM_PATH = "/api/2.0/lineage-tracking/external-metadata"
_EL_PATH = "/api/2.0/lineage-tracking/external-lineage"


def _table_info_fqn(ti: dict) -> str | None:
    """Reconstruct a full ``catalog.schema.table`` FQN from a table_info object.

    The external-lineage API returns the table as SEPARATE fields
    (``catalog_name``/``schema_name``/``name``) — ``name`` alone is just the
    table. Using ``name`` as the node id created a DUPLICATE node (`raw_3040_doc`
    vs `rc18_catalog.bronze.raw_3040_doc`) disconnected from the medallion graph.
    Rebuild the FQN so BYOL edges land on the SAME node the CADOC lineage uses."""
    if not ti:
        return None
    cat, sch, name = ti.get("catalog_name"), ti.get("schema_name"), ti.get("name")
    if cat and sch and name:
        return f"{cat}.{sch}.{name}"
    return name  # fallback: at least return whatever we have


def _add_byol_from_rest(w, nodes: dict, edges: list) -> None:
    """Add BYOL nodes/edges from External Metadata + External Lineage, scoped to
    the rc18_* namespace, via the REST api_client. Best-effort — the caller wraps
    this so a failure never blocks the CADOC UC lineage."""
    # 1. rc18_* external metadata objects → nodes
    resp = w.api_client.do("GET", _EM_PATH)
    meta_names: list[str] = []
    for d in (resp or {}).get("external_metadata", []) or []:
        name = d.get("name")
        if not name or not name.startswith(LINEAGE_OBJECT_PREFIX):
            continue
        obj = ExternalMetadataObject(
            name=name,
            system_type=d.get("system_type") or "OTHER",
            entity_type=d.get("entity_type") or "TABLE",
            description=d.get("description"),
            url=d.get("url"),
            columns=list(d.get("columns") or []),
            properties=dict(d.get("properties") or {}),
        )
        nodes[name] = _ext_object_to_node(obj)
        meta_names.append(name)

    def _ensure_ext_node(name: str) -> None:
        if name not in nodes:
            nodes[name] = LineageNode(
                id=name, label=_short_label(name), type="external_source",
                layer="source", system_type="OTHER", metadata=LineageNodeMetadata(),
            )

    # 2. Relationships from each rc18_* object, both directions.
    seen_rel: set[str] = set()
    for name in meta_names:
        for direction in ("UPSTREAM", "DOWNSTREAM"):
            try:
                rel_resp = w.api_client.do(
                    "GET", _EL_PATH,
                    query={"object_info.external_metadata.name": name, "lineage_direction": direction},
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("BYOL rel query failed %s %s: %s", name, direction, e)
                continue
            for info in (rel_resp or {}).get("external_lineage_relationships", []) or []:
                rel = info.get("external_lineage_info") or {}
                rid = rel.get("id")
                if rid and rid in seen_rel:
                    continue
                if rid:
                    seen_rel.add(rid)
                em = info.get("external_metadata_info")
                ti = info.get("table_info")
                if em and em.get("name"):
                    neighbor = em["name"]
                    _ensure_ext_node(neighbor)
                elif ti and _table_info_fqn(ti):
                    neighbor = _table_info_fqn(ti)   # full FQN — matches CADOC-lineage node ids
                    if neighbor not in nodes:
                        nodes[neighbor] = _uc_node(neighbor, neighbor.split(".")[0])
                else:
                    continue
                src, tgt = (name, neighbor) if direction == "DOWNSTREAM" else (neighbor, name)
                cols = [ColumnMapping(source=c["source"], target=c["target"])
                        for c in (rel.get("columns") or []) if c.get("source") and c.get("target")]
                props = rel.get("properties") or {}
                label = props.get("mechanism") or props.get("transform") or "BYOL"
                edges.append(LineageEdge(source=src, target=tgt, type="external_lineage",
                                         label=label, column_mappings=cols or None))


# Schemas whose tables are noise in the CADOC lineage view: DQX Studio's own
# storage + its per-run temp views. They are lineage neighbors of the silver
# tables (DQX reads them) but are not part of the RC18 medallion story.
_NOISE_SCHEMA_MARKERS = ("dqx_studio", "_tmp", "information_schema")


def _is_relevant_uc_table(fqn: str | None, catalog: str) -> bool:
    """Keep only real RC18-catalog medallion tables; drop DQX temp/quarantine
    and cross-catalog neighbors."""
    if not fqn or "." not in fqn:
        return False
    parts = fqn.split(".")
    if len(parts) < 3 or parts[0] != catalog:
        return False
    schema = parts[1].lower()
    return not any(marker in schema for marker in _NOISE_SCHEMA_MARKERS)


async def _cadoc_anchor_tables(catalog: str, execute_query) -> list[str]:
    """The tables bound to a CADOC (governance.cadoc_tabelas) that EXIST.

    `cadoc_tabelas` is seeded with all 12 vínculos, so a declared-but-missing
    table means that document's pipeline never ran here — and its node was
    indistinguishable from a materialized one. `information_schema.tables` is
    already privilege-filtered.

    Empty → empty-state. If the filter would wipe a non-empty declared list we
    keep the declared one: likelier a privilege/metadata issue than every table
    being gone, and a blank graph is the worse failure.
    """
    try:
        declared_rows = await execute_query(
            f"SELECT DISTINCT table_fqn FROM {catalog}.governance.cadoc_tabelas "
            "WHERE is_ativo AND table_fqn IS NOT NULL",
            {},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read cadoc_tabelas anchors: %s", e)
        return []

    declared = [r["table_fqn"] for r in declared_rows if r.get("table_fqn")]
    if not declared:
        return []

    try:
        existing_rows = await execute_query(
            "SELECT lower(table_catalog || '.' || table_schema || '.' || table_name) AS fqn "
            f"FROM {catalog}.information_schema.tables",
            {},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("information_schema unreadable, keeping declared anchors: %s", e)
        return declared

    existing = {r["fqn"] for r in existing_rows if r.get("fqn")}
    anchors = [fqn for fqn in declared if fqn.lower() in existing]
    if not anchors:
        logger.warning(
            "None of the %d declared CADOC tables found in %s.information_schema — "
            "keeping the declared list (probable privilege/metadata issue).",
            len(declared), catalog,
        )
        return declared

    if len(anchors) < len(declared):
        logger.info(
            "Lineage: %d of %d declared CADOC table(s) not materialized yet — hidden.",
            len(declared) - len(anchors), len(declared),
        )
    return anchors


def _rest_table_lineage(w, table_fqn: str, direction: str) -> list[str]:
    """Return neighbor table FQNs via the REST table-lineage API
    (``GET /api/2.0/lineage-tracking/table-lineage``). Uses only SELECT on the
    table (no ``system.access`` grant needed). ``direction`` ∈ upstream|downstream."""
    key = "upstreams" if direction == "upstream" else "downstreams"
    try:
        resp = w.api_client.do(
            "GET", "/api/2.0/lineage-tracking/table-lineage",
            query={"table_name": table_fqn, "include_entity_lineage": False},
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("REST table-lineage failed for %s (%s): %s", table_fqn, direction, e)
        return []
    out: list[str] = []
    for item in (resp or {}).get(key, []) or []:
        ti = item.get("tableInfo") or {}
        cat, sch, name = ti.get("catalog_name"), ti.get("schema_name"), ti.get("name")
        if cat and sch and name:
            out.append(f"{cat}.{sch}.{name}")
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/graph", response_model=LineageGraphResponse)
async def get_lineage_graph(
    table_name: str | None = Query(None, description="Fully qualified table name to trace"),
    direction: str = Query("both", description="upstream, downstream, or both"),
    depth: int = Query(5, ge=1, le=10),
):
    """Return the full end-to-end lineage graph (BYOL + UC automatic)."""
    if USE_MOCK:
        response = _build_mock(CATALOG)
        if table_name:
            relevant = {table_name}
            for _ in range(depth):
                for e in response.edges:
                    if direction in ("both", "upstream") and e.target in relevant:
                        relevant.add(e.source)
                    if direction in ("both", "downstream") and e.source in relevant:
                        relevant.add(e.target)
            response.nodes = [n for n in response.nodes if n.id in relevant]
            response.edges = [e for e in response.edges if e.source in relevant and e.target in relevant]
        return response

    return await _fetch_real_lineage(CATALOG)


@router.get("/column/{table_name}/{column_name}", response_model=ColumnLineageResponse)
async def get_column_lineage(table_name: str, column_name: str):
    """Return column-level lineage for a specific field."""
    if USE_MOCK:
        if column_name == "ipoc":
            return ColumnLineageResponse(
                target_column=f"{table_name}.{column_name}",
                upstream_columns=[
                    UpstreamColumn(table=f"{CATALOG}.silver.scr3040_operacoes", column="ipoc", transformation="passthrough"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.raw_3040_doc", column="header.CD_IPOC", transformation="XML parse — cloudFiles native reader"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.raw_3040_doc", column="header.CD_CNPJ_IF", transformation="component of IPOC"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.raw_3040_doc", column="header.CD_MODALIDADE", transformation="component of IPOC"),
                ],
                external_sources=[
                    ExternalSource(system="Oracle Core Banking", table="TB_OPERACOES_CREDITO",
                                   columns=["CD_CNPJ_IF", "CD_MODALIDADE", "TP_CLIENTE", "CD_CLIENTE", "NR_CONTRATO"],
                                   source_type="BYOL (External Lineage API)"),
                    ExternalSource(system="Informatica PowerCenter", table="RC18_SCR3040_EXTRACT",
                                   columns=["cnpj_if", "modalidade", "tipo_cliente", "cd_cliente", "nr_contrato"],
                                   source_type="BYOL (External Lineage API)"),
                ],
            )
        return ColumnLineageResponse(
            target_column=f"{table_name}.{column_name}",
            upstream_columns=[
                UpstreamColumn(table=f"{CATALOG}.bronze.raw_3040_doc", column=column_name, transformation="passthrough"),
            ],
        )

    from db import execute_query_or_empty as execute_query
    upstream = []
    try:
        rows = await execute_query(
            "SELECT source_table_full_name, source_column_name "
            "FROM system.access.column_lineage "
            "WHERE target_table_full_name = :table_name "
            "  AND target_column_name = :col_name "
            "  AND event_time > CURRENT_TIMESTAMP() - INTERVAL 30 DAYS",
            {"table_name": table_name, "col_name": column_name},
        )
        upstream = [
            UpstreamColumn(table=r["source_table_full_name"], column=r["source_column_name"], transformation="derived")
            for r in rows if r["source_table_full_name"] and r["source_column_name"]
        ]
    except Exception:
        # Workspace user lacks USE SCHEMA on system.access (UC system tables) — return empty
        # column lineage rather than 500.
        pass
    return ColumnLineageResponse(target_column=f"{table_name}.{column_name}", upstream_columns=upstream)
