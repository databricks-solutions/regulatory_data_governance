"""External Metadata + External Lineage management (BYOL write surface).

This router turns the Lineage module from a read-only viewer into a management
surface over the Unity Catalog **External Metadata** and **External Lineage**
APIs — mirroring the native Catalog Explorer "New external metadata" dialog so
a user can register external systems (COBOL/mainframe, SQL Server, Oracle, BI
tools, BACEN validators…) and wire lineage relationships without leaving the app.

Endpoints (mounted under ``/api/v1/lineage``):
  GET    /external-metadata                 list objects
  POST   /external-metadata                 create object
  GET    /external-metadata/{name}          get one
  PATCH  /external-metadata/{name}          update (partial)
  DELETE /external-metadata/{name}          delete
  GET    /external-lineage                  list relationships
  POST   /external-lineage                  create relationship
  DELETE /external-lineage/{rel_id}         delete relationship
  GET    /system-types                      dropdown options (value+label+icon)
  GET    /uc-tables                          UC tables for the target picker

Real mode (``USE_MOCK_BACKEND=false``) calls the live REST API via the SDK's
``api_client`` (endpoints ``/api/2.0/lineage-tracking/{external-metadata,
external-lineage}``). Writes run as the **app's service principal**, which must
hold ``CREATE EXTERNAL METADATA`` on the metastore + ``MODIFY`` on the objects
and the appropriate SELECT/MODIFY on the UC tables (see
notebooks/setup/grant_dqx_studio_access.sql). Mock mode uses the shared
in-memory store so the graph reflects edits immediately in the local devloop.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

import external_lineage_store as store
from db import CATALOG, LINEAGE_OBJECT_PREFIX, USE_MOCK
from models import (
    ColumnMapping,
    ExternalLineageEndpoint,
    ExternalLineageListResponse,
    ExternalLineageRelationship,
    ExternalLineageRelationshipRequest,
    ExternalMetadataListResponse,
    ExternalMetadataObject,
    ExternalObjectWithLineageRequest,
    NodeMetadataResponse,
    SystemTypeOption,
    TableColumn,
    UcTableOption,
    UcTablesResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_EM_PATH = "/api/2.0/lineage-tracking/external-metadata"
_EL_PATH = "/api/2.0/lineage-tracking/external-lineage"

# ---------------------------------------------------------------------------
# System type dropdown — mirrors the native "New external metadata" picker.
# ``icon`` is a stable slug the frontend maps to an inline SVG. The list is
# curated (not the full enum) around what an RC18 customer registers; anything
# unknown falls back to the ``custom`` badge. Order roughly matches the native
# dialog (BI + databases + Custom).
# ---------------------------------------------------------------------------
_SYSTEM_TYPES: list[SystemTypeOption] = [
    SystemTypeOption(value="ORACLE", label="Oracle", icon="oracle"),
    SystemTypeOption(value="MICROSOFT_SQL_SERVER", label="Microsoft SQL Server", icon="sqlserver"),
    SystemTypeOption(value="MYSQL", label="MySQL", icon="mysql"),
    SystemTypeOption(value="POSTGRESQL", label="PostgreSQL", icon="postgresql"),
    SystemTypeOption(value="TERADATA", label="Teradata", icon="teradata"),
    SystemTypeOption(value="SNOWFLAKE", label="Snowflake", icon="snowflake"),
    SystemTypeOption(value="AMAZON_REDSHIFT", label="Amazon Redshift", icon="redshift"),
    SystemTypeOption(value="GOOGLE_BIGQUERY", label="Google BigQuery", icon="bigquery"),
    SystemTypeOption(value="AZURE_SYNAPSE", label="Azure Synapse", icon="synapse"),
    SystemTypeOption(value="MICROSOFT_FABRIC", label="Microsoft Fabric", icon="fabric"),
    SystemTypeOption(value="MONGODB", label="MongoDB", icon="mongodb"),
    SystemTypeOption(value="SAP", label="SAP", icon="sap"),
    SystemTypeOption(value="SALESFORCE", label="Salesforce", icon="salesforce"),
    SystemTypeOption(value="WORKDAY", label="Workday", icon="workday"),
    SystemTypeOption(value="SERVICENOW", label="ServiceNow", icon="servicenow"),
    SystemTypeOption(value="POWER_BI", label="Power BI", icon="powerbi"),
    SystemTypeOption(value="TABLEAU", label="Tableau", icon="tableau"),
    SystemTypeOption(value="LOOKER", label="Looker", icon="looker"),
    SystemTypeOption(value="KAFKA", label="Apache Kafka", icon="kafka"),
    SystemTypeOption(value="CONFLUENT", label="Confluent", icon="confluent"),
    SystemTypeOption(value="DATABRICKS", label="Databricks", icon="databricks"),
    # Catch-all — used for COBOL / mainframe / DB2 z/OS and anything not in the
    # native enum. The customer's real system name goes in the ``sistema`` property.
    SystemTypeOption(value="OTHER", label="Custom / Outro", icon="custom"),
]
_VALID_SYSTEM_TYPES = {s.value for s in _SYSTEM_TYPES}


def _w():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


# ---------------------------------------------------------------------------
# System types + UC table picker
# ---------------------------------------------------------------------------


@router.get("/system-types", response_model=list[SystemTypeOption])
async def get_system_types():
    """Options for the System type dropdown (value + label + icon slug)."""
    return _SYSTEM_TYPES


@router.get("/uc-tables", response_model=UcTablesResponse)
async def get_uc_tables(
    schema: str | None = Query(None, description="Restrict to one schema (bronze/silver/gold)"),
):
    """Unity Catalog tables usable as a relationship endpoint (target picker)."""
    if USE_MOCK:
        seed = [
            ("bronze", "raw_3040_doc"), ("bronze", "raw_3050_doc"),
            ("silver", "scr3040_operacoes"), ("silver", "scr3040_clientes"),
            ("gold", "posicao_3040"), ("gold", "posicao_3050"),
        ]
        tables = [
            UcTableOption(full_name=f"{CATALOG}.{s}.{t}", schema_name=s, table_name=t)
            for s, t in seed if not schema or s == schema
        ]
        return UcTablesResponse(tables=tables)

    from db import execute_query_or_empty as execute_query

    where = "table_catalog = :catalog"
    params: dict[str, str] = {"catalog": CATALOG}
    if schema:
        where += " AND table_schema = :schema"
        params["schema"] = schema
    else:
        where += " AND table_schema IN ('bronze','silver','gold')"
    rows = await execute_query(
        "SELECT table_schema, table_name "
        "FROM system.information_schema.tables "
        f"WHERE {where} ORDER BY table_schema, table_name",
        params,
    )
    tables = [
        UcTableOption(
            full_name=f"{CATALOG}.{r['table_schema']}.{r['table_name']}",
            schema_name=r["table_schema"],
            table_name=r["table_name"],
        )
        for r in rows
    ]
    return UcTablesResponse(tables=tables)


# ---------------------------------------------------------------------------
# Node metadata — full details for a clicked graph node
# ---------------------------------------------------------------------------


@router.get("/node-metadata", response_model=NodeMetadataResponse)
async def get_node_metadata(id: str = Query(..., description="Node id: a UC table FQN or an external metadata name")):
    """Return full metadata for a clicked node.

    A ``catalog.schema.table`` id is resolved as a Unity Catalog table (columns,
    comment, owner, row count, CADOC bindings). Anything else is resolved as a
    registered external metadata object (system_type, entity_type, url, properties).
    """
    looks_like_table = id.count(".") >= 2

    if USE_MOCK:
        if looks_like_table:
            short = id.split(".")[-1]
            return NodeMetadataResponse(
                id=id, kind="uc_table", label=short,
                catalog=id.split(".")[0], schema_name=id.split(".")[1], table_name=short,
                table_type="MANAGED", comment="Tabela do medallion RC18 (mock).",
                owner="rc18-app", row_count=12345,
                updated_at="2026-03-31T04:00:00Z",
                columns=[
                    TableColumn(name="ipoc", type="STRING", comment="Identificador da operação (IPOC)"),
                    TableColumn(name="cnpj_if", type="STRING", comment="CNPJ da instituição"),
                    TableColumn(name="modalidade", type="STRING"),
                    TableColumn(name="vlr_contabil", type="DECIMAL(18,2)"),
                    TableColumn(name="dt_base", type="DATE"),
                ],
                cadocs=["3040"] if "3040" in short else (["3050"] if "3050" in short else []),
            )
        obj = store.get_metadata(CATALOG, id)
        if not obj:
            raise HTTPException(status_code=404, detail="Nó não encontrado")
        return NodeMetadataResponse(
            id=id, kind="external", label=(obj.properties or {}).get("label") or obj.name,
            system_type=obj.system_type, entity_type=obj.entity_type, url=obj.url,
            comment=obj.description, properties=obj.properties,
            columns=[TableColumn(name=c) for c in (obj.columns or [])],
        )

    # ── Real mode ──────────────────────────────────────────────────────────
    if looks_like_table:
        return await _uc_table_metadata(id)
    return _external_metadata_node(id)


async def _uc_table_metadata(fqn: str) -> NodeMetadataResponse:
    from db import execute_query_or_empty as execute_query

    short = fqn.split(".")[-1]
    resp: dict = {}
    try:
        # REST tables API — works on any SDK version; needs only SELECT/USE on the table.
        resp = _w().api_client.do("GET", f"/api/2.1/unity-catalog/tables/{fqn}") or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("UC table metadata failed for %s: %s", fqn, exc)

    columns = [
        TableColumn(name=c.get("name", ""), type=c.get("type_text") or c.get("type_name"),
                    comment=c.get("comment"))
        for c in (resp.get("columns") or [])
    ]

    # Best-effort row count — a cheap COUNT(*), tolerant if the SP can't read it.
    row_count = None
    try:
        rows = await execute_query(f"SELECT COUNT(*) AS n FROM {fqn}", {})
        if rows:
            row_count = int(rows[0]["n"])
    except Exception:  # noqa: BLE001
        pass

    # Which CADOCs is this table bound to?
    cadocs: list[str] = []
    try:
        rows = await execute_query(
            f"SELECT DISTINCT documento FROM {CATALOG}.governance.cadoc_tabelas "
            "WHERE is_ativo AND table_fqn = :fqn ORDER BY documento",
            {"fqn": fqn},
        )
        cadocs = [r["documento"] for r in rows if r.get("documento")]
    except Exception:  # noqa: BLE001
        pass

    updated_ms = resp.get("updated_at")
    created_ms = resp.get("created_at")

    def _iso(ms):
        if not ms:
            return None
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa: BLE001
            return None

    return NodeMetadataResponse(
        id=fqn, kind="uc_table", label=short,
        catalog=resp.get("catalog_name") or fqn.split(".")[0],
        schema_name=resp.get("schema_name") or fqn.split(".")[1],
        table_name=resp.get("name") or short,
        table_type=resp.get("table_type"),
        comment=resp.get("comment"),
        owner=resp.get("owner"),
        row_count=row_count,
        created_at=_iso(created_ms),
        updated_at=_iso(updated_ms),
        columns=columns,
        cadocs=cadocs,
    )


def _external_metadata_node(name: str) -> NodeMetadataResponse:
    try:
        d = _w().api_client.do("GET", f"{_EM_PATH}/{name}") or {}
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Nó não encontrado")
    props = dict(d.get("properties") or {})
    return NodeMetadataResponse(
        id=name, kind="external", label=props.get("label") or d.get("name") or name,
        system_type=d.get("system_type"), entity_type=d.get("entity_type"),
        url=d.get("url"), comment=d.get("description"), owner=d.get("owner"),
        properties=props,
        columns=[TableColumn(name=c) for c in (d.get("columns") or [])],
    )


# ---------------------------------------------------------------------------
# External metadata CRUD
# ---------------------------------------------------------------------------


def _obj_from_api(d: dict) -> ExternalMetadataObject:
    return ExternalMetadataObject(
        name=d.get("name", ""),
        system_type=d.get("system_type") or "OTHER",
        entity_type=d.get("entity_type") or "TABLE",
        description=d.get("description"),
        url=d.get("url"),
        owner=d.get("owner"),
        columns=list(d.get("columns") or []),
        properties=dict(d.get("properties") or {}),
        id=d.get("id"),
        created_at=d.get("create_time"),
        updated_at=d.get("update_time"),
    )


def _obj_to_body(obj: ExternalMetadataObject) -> dict:
    body: dict = {
        "name": obj.name,
        "system_type": obj.system_type or "OTHER",
        "entity_type": obj.entity_type or "TABLE",
    }
    if obj.description:
        body["description"] = obj.description
    if obj.url:
        body["url"] = obj.url
    # NOTE: `owner` is NOT sent — the create/update API sets it server-side to the
    # caller and rejects a supplied owner with "Must not supply an owner".
    if obj.columns:
        body["columns"] = obj.columns
    if obj.properties:
        body["properties"] = obj.properties
    return body


@router.get("/external-metadata", response_model=ExternalMetadataListResponse)
async def list_external_metadata():
    if USE_MOCK:
        return ExternalMetadataListResponse(objects=store.list_metadata(CATALOG))
    try:
        resp = _w().api_client.do("GET", _EM_PATH)
        items = resp.get("external_metadata", []) if isinstance(resp, dict) else []
        # Scope to the RC18 namespace: UC external metadata is metastore-wide, so
        # without this filter the manager list and relationship pickers would show
        # (and offer to delete) objects from other projects the app SP can't manage.
        scoped = [d for d in items if (d.get("name") or "").startswith(LINEAGE_OBJECT_PREFIX)]
        return ExternalMetadataListResponse(objects=[_obj_from_api(d) for d in scoped])
    except Exception as exc:  # noqa: BLE001
        logger.warning("list external_metadata failed: %s", exc)
        return ExternalMetadataListResponse(objects=[])


@router.get("/external-metadata/{name}", response_model=ExternalMetadataObject)
async def get_external_metadata(name: str):
    if USE_MOCK:
        obj = store.get_metadata(CATALOG, name)
        if not obj:
            raise HTTPException(status_code=404, detail="Metadado externo não encontrado")
        return obj
    try:
        d = _w().api_client.do("GET", f"{_EM_PATH}/{name}")
        return _obj_from_api(d)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"Metadado externo não encontrado: {exc}")


def _ensure_scoped(name: str) -> None:
    """Reject writes to objects outside the RC18 namespace prefix.

    Defense in depth: the app only lists namespaced objects, but a hand-crafted
    request could still target an out-of-namespace object the app SP doesn't own
    (which would fail late with a raw "does not have MANAGE" from UC). Fail early
    and clearly instead."""
    if not name.startswith(LINEAGE_OBJECT_PREFIX):
        raise HTTPException(
            status_code=403,
            detail=(
                f"O app RC18 só gerencia objetos de linhagem com o prefixo "
                f"'{LINEAGE_OBJECT_PREFIX}'. '{name}' pertence a outro namespace e "
                f"deve ser gerenciado no Catalog Explorer."
            ),
        )


def _namespaced(name: str) -> str:
    """Auto-prefix a user-typed name with the deployment namespace so everything
    the app creates stays manageable by the app SP. Idempotent — a name already
    carrying the prefix is left as-is. So "cobol_batch" → "rc18_cobol_batch", and
    "rc18_cobol_batch" stays unchanged. The user never has to type the prefix."""
    n = name.strip()
    return n if n.startswith(LINEAGE_OBJECT_PREFIX) else f"{LINEAGE_OBJECT_PREFIX}{n}"


@router.post("/external-metadata", response_model=ExternalMetadataObject, status_code=201)
async def create_external_metadata(obj: ExternalMetadataObject):
    if not obj.name.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if obj.system_type not in _VALID_SYSTEM_TYPES:
        raise HTTPException(status_code=400, detail=f"system_type inválido: {obj.system_type}")
    # Auto-prefix instead of rejecting — the namespace is enforced transparently.
    obj.name = _namespaced(obj.name)

    if USE_MOCK:
        try:
            return store.create_metadata(CATALOG, obj)
        except KeyError:
            raise HTTPException(status_code=409, detail=f"Já existe um metadado externo '{obj.name}'")

    try:
        d = _w().api_client.do("POST", _EM_PATH, body=_obj_to_body(obj))
        return _obj_from_api(d)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=_status_from_exc(exc), detail=_friendly_error(exc))


@router.patch("/external-metadata/{name}", response_model=ExternalMetadataObject)
async def update_external_metadata(name: str, patch: ExternalMetadataObject):
    _ensure_scoped(name)
    if USE_MOCK:
        updated = store.update_metadata(CATALOG, name, patch.model_dump(exclude={"name", "id", "created_at", "updated_at"}))
        if not updated:
            raise HTTPException(status_code=404, detail="Metadado externo não encontrado")
        return updated

    # PATCH requires an update_mask query param listing the fields to change.
    # `owner` is intentionally excluded — the API rejects a client-supplied owner.
    fields = [f for f in ("system_type", "entity_type", "description", "url", "columns", "properties")
              if getattr(patch, f) not in (None, [], {})]
    if not fields:
        raise HTTPException(status_code=400, detail="Nada para atualizar")
    body = {f: getattr(patch, f) for f in fields}
    try:
        d = _w().api_client.do(
            "PATCH", f"{_EM_PATH}/{name}",
            query={"update_mask": ",".join(fields)}, body=body,
        )
        return _obj_from_api(d)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=_status_from_exc(exc), detail=_friendly_error(exc))


@router.delete("/external-metadata/{name}", status_code=204)
async def delete_external_metadata(name: str):
    _ensure_scoped(name)
    if USE_MOCK:
        if not store.delete_metadata(CATALOG, name):
            raise HTTPException(status_code=404, detail="Metadado externo não encontrado")
        return None
    try:
        _w().api_client.do("DELETE", f"{_EM_PATH}/{name}")
        return None
    except Exception as exc:  # noqa: BLE001
        # An object created by a PREVIOUS deploy's app SP (now destroyed) is an
        # ORPHAN (owner=unknown) — delete fails with "does not have MANAGE". The
        # current app SP can reclaim it by taking ownership (PATCH owner), then
        # retry the delete. Only attempted for the app's own namespace.
        if "DOES NOT HAVE MANAGE" in str(exc).upper():
            try:
                _w().api_client.do(
                    "PATCH", f"{_EM_PATH}/{name}",
                    query={"update_mask": "owner"},
                    body={"owner": _current_principal()},
                )
                _w().api_client.do("DELETE", f"{_EM_PATH}/{name}")
                return None
            except Exception as exc2:  # noqa: BLE001
                raise HTTPException(status_code=_status_from_exc(exc2), detail=_friendly_error(exc2))
        raise HTTPException(status_code=_status_from_exc(exc), detail=_friendly_error(exc))


def _current_principal() -> str:
    """Identity to reclaim orphan ownership with — the app's own service
    principal. Falls back to the SDK's current user if unavailable."""
    try:
        return _w().current_user.me().user_name
    except Exception:  # noqa: BLE001
        import os
        return os.getenv("DATABRICKS_CLIENT_ID", "")


# ---------------------------------------------------------------------------
# External lineage relationships
# ---------------------------------------------------------------------------


def _endpoint_to_body(ep: ExternalLineageEndpoint) -> dict:
    if ep.external_metadata_name:
        return {"external_metadata": {"name": ep.external_metadata_name}}
    if ep.table_name:
        return {"table": {"name": ep.table_name}}
    raise HTTPException(status_code=400, detail="Endpoint precisa de external_metadata_name ou table_name")


def _endpoint_from_api(d: dict) -> ExternalLineageEndpoint:
    em = d.get("external_metadata") or {}
    tb = d.get("table") or {}
    return ExternalLineageEndpoint(
        external_metadata_name=em.get("name"),
        table_name=tb.get("name"),
    )


@router.get("/external-lineage", response_model=ExternalLineageListResponse)
async def list_external_lineage(
    object_name: str | None = Query(None, description="Restrict to relationships of this external object"),
):
    """List external lineage relationships (mock store, or real via REST).

    In real mode we walk relationships from each rc18_* external metadata object
    (both directions) — scoped to the namespace so we never surface other
    projects' edges. ``object_name`` narrows to a single object (used by the
    side panel to list a node's edges)."""
    if USE_MOCK:
        rels = store.list_relationships(CATALOG)
        if object_name:
            rels = [r for r in rels
                    if object_name in (r.source.external_metadata_name, r.target.external_metadata_name)]
        return ExternalLineageListResponse(relationships=rels)

    # ── Real mode ──────────────────────────────────────────────────────────
    if object_name:
        names = [object_name] if object_name.startswith(LINEAGE_OBJECT_PREFIX) else []
    else:
        try:
            resp = _w().api_client.do("GET", _EM_PATH)
            names = [d["name"] for d in (resp or {}).get("external_metadata", []) or []
                     if (d.get("name") or "").startswith(LINEAGE_OBJECT_PREFIX)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("list external_lineage: could not list objects: %s", exc)
            names = []

    rels: list[ExternalLineageRelationship] = []
    seen: set[str] = set()
    for name in names:
        for direction in ("UPSTREAM", "DOWNSTREAM"):
            try:
                rr = _w().api_client.do(
                    "GET", _EL_PATH,
                    query={"object_info.external_metadata.name": name, "lineage_direction": direction},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("list external_lineage %s %s: %s", name, direction, exc)
                continue
            for info in (rr or {}).get("external_lineage_relationships", []) or []:
                rel = info.get("external_lineage_info") or {}
                rid = rel.get("id")
                if rid and rid in seen:
                    continue
                if rid:
                    seen.add(rid)
                neighbor_em = info.get("external_metadata_info") or {}
                neighbor_tb = info.get("table_info") or {}
                # table_info returns catalog/schema/name separately — rebuild the
                # full FQN so the endpoint matches the graph node ids.
                tb_name = None
                if neighbor_tb:
                    cat, sch, nm = neighbor_tb.get("catalog_name"), neighbor_tb.get("schema_name"), neighbor_tb.get("name")
                    tb_name = f"{cat}.{sch}.{nm}" if (cat and sch and nm) else nm
                neighbor = ExternalLineageEndpoint(
                    external_metadata_name=neighbor_em.get("name"),
                    table_name=tb_name,
                )
                this = ExternalLineageEndpoint(external_metadata_name=name)
                src, tgt = (this, neighbor) if direction == "DOWNSTREAM" else (neighbor, this)
                rels.append(ExternalLineageRelationship(
                    id=rid, source=src, target=tgt,
                    columns=[ColumnMapping(source=c["source"], target=c["target"])
                             for c in (rel.get("columns") or []) if c.get("source") and c.get("target")],
                    properties=dict(rel.get("properties") or {}),
                ))
    return ExternalLineageListResponse(relationships=rels)


def _create_relationship(
    source: ExternalLineageEndpoint, target: ExternalLineageEndpoint,
    columns: list[ColumnMapping], properties: dict[str, str],
) -> ExternalLineageRelationship:
    """Create one lineage relationship (mock store or real REST). Shared by the
    standalone and the atomic-create endpoints."""
    if USE_MOCK:
        return store.create_relationship(CATALOG, ExternalLineageRelationship(
            source=source, target=target, columns=columns, properties=properties,
        ))
    body: dict = {"source": _endpoint_to_body(source), "target": _endpoint_to_body(target)}
    if columns:
        body["columns"] = [{"source": c.source, "target": c.target} for c in columns]
    if properties:
        body["properties"] = properties
    d = _w().api_client.do("POST", _EL_PATH, body=body)
    return ExternalLineageRelationship(
        id=d.get("id"),
        source=_endpoint_from_api(d.get("source", {})),
        target=_endpoint_from_api(d.get("target", {})),
        columns=[ColumnMapping(source=c.get("source", ""), target=c.get("target", ""))
                 for c in (d.get("columns") or [])],
        properties=dict(d.get("properties") or {}),
    )


@router.post("/external-lineage", response_model=ExternalLineageRelationship, status_code=201)
async def create_external_lineage(req: ExternalLineageRelationshipRequest):
    try:
        return _create_relationship(req.source, req.target, req.columns, req.properties)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=_status_from_exc(exc), detail=_friendly_error(exc))


@router.post("/external-object-with-lineage", response_model=ExternalLineageRelationship, status_code=201)
async def create_external_object_with_lineage(req: ExternalObjectWithLineageRequest):
    """Atomic: register the external object AND wire one lineage relationship.

    This is the unified create flow — the object is never left orphaned, and the
    namespace is enforced by auto-prefixing the object name. ``connect_direction``
    decides whether the new object is upstream (source) or downstream (target) of
    ``connect_to``."""
    if req.connect_direction not in ("source", "target"):
        raise HTTPException(status_code=400, detail="connect_direction deve ser 'source' ou 'target'")
    if not (req.connect_to.external_metadata_name or req.connect_to.table_name):
        raise HTTPException(status_code=400, detail="connect_to precisa de um node (tabela UC ou objeto externo)")

    # 1. Create the object (auto-prefixed).
    created = await create_external_metadata(req.object)
    this_ep = ExternalLineageEndpoint(external_metadata_name=created.name)

    # 2. Wire the relationship in the requested direction.
    source, target = (this_ep, req.connect_to) if req.connect_direction == "source" else (req.connect_to, this_ep)
    try:
        return _create_relationship(source, target, req.columns, req.relationship_properties)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # The object was created but the edge failed — surface clearly so the user
        # can retry the relationship without a duplicate-object error.
        raise HTTPException(
            status_code=_status_from_exc(exc),
            detail=f"Objeto '{created.name}' criado, mas o relacionamento falhou: {_friendly_error(exc)}",
        )


def _endpoint_query_params(prefix: str, ep: ExternalLineageEndpoint) -> dict:
    """Flatten an endpoint into the DELETE query params the API expects, e.g.
    external_lineage_relationship.source.external_metadata.name=<x>."""
    base = f"external_lineage_relationship.{prefix}"
    if ep.external_metadata_name:
        return {f"{base}.external_metadata.name": ep.external_metadata_name}
    if ep.table_name:
        return {f"{base}.table.name": ep.table_name}
    raise HTTPException(status_code=400, detail=f"Endpoint {prefix} precisa de external_metadata_name ou table_name")


@router.delete("/external-lineage", status_code=204)
async def delete_external_lineage(
    rel_id: str | None = Query(None, description="Relationship id (mock store)"),
    source_external: str | None = Query(None),
    source_table: str | None = Query(None),
    target_external: str | None = Query(None),
    target_table: str | None = Query(None),
):
    """Delete an external lineage relationship.

    Real mode identifies the edge by its source+target (the REST API has no
    delete-by-id); mock mode also accepts ``rel_id``. The frontend passes the
    endpoints it already has from the graph/list."""
    source = ExternalLineageEndpoint(external_metadata_name=source_external, table_name=source_table)
    target = ExternalLineageEndpoint(external_metadata_name=target_external, table_name=target_table)

    if USE_MOCK:
        if rel_id and store.delete_relationship(CATALOG, rel_id):
            return None
        # Fall back to source/target match.
        for r in store.list_relationships(CATALOG):
            if (r.source.external_metadata_name == source.external_metadata_name
                    and r.source.table_name == source.table_name
                    and r.target.external_metadata_name == target.external_metadata_name
                    and r.target.table_name == target.table_name):
                store.delete_relationship(CATALOG, r.id)
                return None
        raise HTTPException(status_code=404, detail="Relacionamento não encontrado")

    # ── Real mode: DELETE by flattened source/target query params ───────────
    # Guard: at least one endpoint must be a namespaced external object, so the
    # app never deletes edges it doesn't own.
    ext_names = [n for n in (source.external_metadata_name, target.external_metadata_name) if n]
    if not any(n.startswith(LINEAGE_OBJECT_PREFIX) for n in ext_names):
        raise HTTPException(
            status_code=403,
            detail=f"Só é possível remover relacionamentos de objetos do namespace '{LINEAGE_OBJECT_PREFIX}'.",
        )
    query = {**_endpoint_query_params("source", source), **_endpoint_query_params("target", target)}
    try:
        _w().api_client.do("DELETE", _EL_PATH, query=query)
        return None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=_status_from_exc(exc), detail=_friendly_error(exc))


# ---------------------------------------------------------------------------
# Error helpers — turn SDK/REST exceptions into actionable messages
# ---------------------------------------------------------------------------


def _status_from_exc(exc: Exception) -> int:
    msg = str(exc).upper()
    if ("PERMISSION_DENIED" in msg or "INSUFFICIENT_PERMISSIONS" in msg
            or "DOES NOT HAVE" in msg or "403" in msg):
        return 403
    if "ALREADY_EXISTS" in msg or "409" in msg:
        return 409
    if "NOT_FOUND" in msg or "404" in msg:
        return 404
    return 400


def _sanitize(msg: str) -> str:
    """Strip the databricks-sdk Config dump (``Config: host=…, client_id=…,
    client_secret=***, …``) that SDK exceptions append — it leaks the app SP's
    client_id and auth details into the UI. Keep only the message before it."""
    for marker in (". Config:", " Config:", "\nConfig:"):
        idx = msg.find(marker)
        if idx != -1:
            return msg[:idx].rstrip(". ").strip()
    return msg


def _friendly_error(exc: Exception) -> str:
    msg = _sanitize(str(exc))
    upper = msg.upper()
    # Order matters — check the SPECIFIC causes before the generic "does not have".
    if "CREATE EXTERNAL METADATA" in upper or "ON METASTORE" in upper:
        return (
            "O service principal do app não tem o privilégio 'CREATE EXTERNAL METADATA' "
            "no metastore. Conceda-o ao SP do app (seção 'GRANT BYOL' em "
            "notebooks/setup/grant_dqx_studio_access.sql) — é uma configuração única "
            "por workspace. Detalhe: " + msg
        )
    if "MUST NOT SUPPLY AN OWNER" in upper:
        return (
            "O campo 'Proprietário' não pode ser enviado na criação — ele é definido "
            "automaticamente. Deixe-o em branco. Detalhe: " + msg
        )
    if "DOES NOT HAVE MANAGE" in upper:
        return (
            "O service principal do app não é dono deste objeto de linhagem externa "
            "(ou não tem MANAGE sobre ele) — provavelmente foi criado por outro projeto/"
            "usuário. O app RC18 só gerencia objetos que ele próprio criou. Detalhe: " + msg
        )
    if "PERMISSION_DENIED" in upper or "INSUFFICIENT_PERMISSIONS" in upper or "DOES NOT HAVE" in upper:
        return (
            "O service principal do app não tem privilégio para gravar metadados/linhagem "
            "externa. Conceda 'CREATE EXTERNAL METADATA' no metastore e 'MODIFY' nas tabelas "
            "de fronteira (ver notebooks/setup/grant_dqx_studio_access.sql). Detalhe: " + msg
        )
    return msg
