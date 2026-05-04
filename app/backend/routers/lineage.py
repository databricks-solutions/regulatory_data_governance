"""Lineage endpoints: graph and column-level lineage."""

from __future__ import annotations

from fastapi import APIRouter, Query

from db import CATALOG, USE_MOCK
from models import (
    ColumnLineageResponse,
    ColumnMapping,
    ExternalSource,
    LineageEdge,
    LineageGraphResponse,
    LineageNode,
    LineageNodeMetadata,
    UpstreamColumn,
)

router = APIRouter()

_MOCK_NODES = [
    LineageNode(id="ext_oracle_tb_operacoes", label="Oracle TB_OPERACOES_CREDITO", type="external_source", layer="source", system="Oracle Core Banking", metadata=LineageNodeMetadata(connection="jdbc:oracle:thin:@core-host:1521/CREDITO", update_frequency="CDC via ROWSCN")),
    LineageNode(id=f"{CATALOG}.bronze.operacoes_raw", label="operacoes_raw", type="table", layer="bronze", catalog=CATALOG, metadata=LineageNodeMetadata(row_count=1500000, last_updated="2026-03-31T23:15:00Z")),
    LineageNode(id=f"{CATALOG}.silver.operacoes_validadas", label="operacoes_validadas", type="table", layer="silver", catalog=CATALOG, metadata=LineageNodeMetadata(row_count=1498500, last_updated="2026-03-31T01:30:00Z", expectations_pass_rate=99.9)),
    LineageNode(id=f"{CATALOG}.gold.posicao_mensal_3040", label="posicao_mensal_3040", type="table", layer="gold", catalog=CATALOG, metadata=LineageNodeMetadata(row_count=1498500, last_updated="2026-03-31T04:00:00Z")),
    LineageNode(id="ext_xml_3040_202603", label="SCR3040_202603.xml", type="external_output", layer="output", system="Validador BCB / STA", metadata=LineageNodeMetadata(file_size_mb=3800, parts=4, validated=True)),
]

_MOCK_EDGES = [
    LineageEdge(source="ext_oracle_tb_operacoes", target=f"{CATALOG}.bronze.operacoes_raw", type="external_lineage", column_mappings=[ColumnMapping(source="CD_CNPJ_IF", target="cnpj_if"), ColumnMapping(source="CD_MODALIDADE", target="mod"), ColumnMapping(source="TP_CLIENTE", target="cli_tp")]),
    LineageEdge(source=f"{CATALOG}.bronze.operacoes_raw", target=f"{CATALOG}.silver.operacoes_validadas", type="uc_automatic", pipeline="scr3040_silver"),
    LineageEdge(source=f"{CATALOG}.silver.operacoes_validadas", target=f"{CATALOG}.gold.posicao_mensal_3040", type="uc_automatic", pipeline="scr3040_gold"),
    LineageEdge(source=f"{CATALOG}.gold.posicao_mensal_3040", target="ext_xml_3040_202603", type="audit_table", audit_ref=f"{CATALOG}.quality.submissao_historico"),
]


@router.get("/graph", response_model=LineageGraphResponse)
async def get_lineage_graph(
    table_name: str | None = Query(None, description="Fully qualified table name to trace"),
    direction: str = Query("both", description="upstream, downstream, or both"),
    depth: int = Query(5, ge=1, le=10),
):
    """Return data lineage graph for frontend SVG visualization."""
    if USE_MOCK:
        nodes = _MOCK_NODES
        edges = _MOCK_EDGES
        if table_name:
            relevant_ids = {table_name}
            for _ in range(depth):
                for e in edges:
                    if direction in ("both", "upstream") and e.target in relevant_ids:
                        relevant_ids.add(e.source)
                    if direction in ("both", "downstream") and e.source in relevant_ids:
                        relevant_ids.add(e.target)
            nodes = [n for n in nodes if n.id in relevant_ids]
            edges = [e for e in edges if e.source in relevant_ids and e.target in relevant_ids]
        return LineageGraphResponse(nodes=nodes, edges=edges)

    from db import execute_query
    nodes_set: set[str] = set()
    edges = []
    try:
        table_rows = await execute_query(
            "SELECT source_table_full_name, target_table_full_name "
            "FROM system.access.table_lineage "
            "WHERE target_table_catalog = :catalog "
            "AND event_time > CURRENT_TIMESTAMP() - INTERVAL 30 DAYS",
            {"catalog": CATALOG},
        )
        for r in table_rows:
            src, tgt = r["source_table_full_name"], r["target_table_full_name"]
            if src is None or tgt is None:
                continue
            nodes_set.add(src)
            nodes_set.add(tgt)
            edges.append(LineageEdge(source=src, target=tgt, type="uc_automatic"))
    except Exception:
        # Workspace user lacks USE SCHEMA on system.access (UC system tables) — return empty
        # graph rather than 500. The mock branch above keeps the demo populated.
        pass
    nodes = [
        LineageNode(
            id=n, label=n.split(".")[-1], type="table",
            layer=n.split(".")[1] if "." in n else "unknown",
            catalog=n.split(".")[0] if "." in n else None,
        )
        for n in nodes_set
    ]
    return LineageGraphResponse(nodes=nodes, edges=edges)


@router.get("/column/{table_name}/{column_name}", response_model=ColumnLineageResponse)
async def get_column_lineage(table_name: str, column_name: str):
    """Return column-level lineage for a specific field."""
    if USE_MOCK:
        if column_name == "ipoc":
            return ColumnLineageResponse(
                target_column=f"{table_name}.{column_name}",
                upstream_columns=[
                    UpstreamColumn(table=f"{CATALOG}.silver.operacoes_validadas", column="ipoc", transformation="passthrough"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column="cnpj_if", transformation="CONCAT(cnpj_if, mod, cli_tp, cli_cd, contrt)"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column="mod", transformation="component of IPOC"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column="cli_tp", transformation="component of IPOC"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column="cli_cd", transformation="component of IPOC"),
                    UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column="contrt", transformation="component of IPOC"),
                ],
                external_sources=[
                    ExternalSource(system="Oracle Core Banking", table="TB_OPERACOES_CREDITO", columns=["CD_CNPJ_IF", "CD_MODALIDADE", "TP_CLIENTE", "CD_CLIENTE", "NR_CONTRATO"], source_type="external_lineage_api"),
                ],
            )
        return ColumnLineageResponse(
            target_column=f"{table_name}.{column_name}",
            upstream_columns=[
                UpstreamColumn(table=f"{CATALOG}.bronze.operacoes_raw", column=column_name, transformation="passthrough"),
            ],
        )

    from db import execute_query
    upstream = []
    try:
        rows = await execute_query(
            "SELECT source_table_full_name, source_column_name, "
            "target_table_full_name, target_column_name "
            "FROM system.access.column_lineage "
            "WHERE target_table_full_name = :table_name",
            {"table_name": table_name},
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
