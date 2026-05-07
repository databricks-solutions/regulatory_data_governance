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
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Display metadata for each rc18_* external metadata object
# ---------------------------------------------------------------------------

_EXT_META: dict[str, dict] = {
    # Origin systems (upstream of Oracle/DB2)
    "rc18_los_originacao_credito":      dict(label="LOS: Originacao de Credito",    layer="origin",    system="Loan Origination System", system_type="OTHER"),
    "rc18_crm_cadastro_clientes":       dict(label="CRM: Cadastro de Clientes",     layer="origin",    system="CRM / MDM Clientes",      system_type="OTHER"),
    # Oracle Core Banking
    "rc18_oracle_tb_operacoes_credito": dict(label="Oracle: TB_OPERACOES_CREDITO",  layer="source",    system="Oracle Core Banking",     system_type="ORACLE"),
    "rc18_oracle_tb_garantias":         dict(label="Oracle: TB_GARANTIAS",          layer="source",    system="Oracle Core Banking",     system_type="ORACLE"),
    "rc18_oracle_tb_contratantes":      dict(label="Oracle: TB_CONTRATANTES",       layer="source",    system="Oracle Core Banking",     system_type="ORACLE"),
    "rc18_oracle_tb_cessoes_fidc":      dict(label="Oracle: TB_CESSOES_FIDC",       layer="source",    system="Oracle Core Banking",     system_type="ORACLE"),
    # IBM DB2 Mainframe
    "rc18_db2_clientes_credito":        dict(label="DB2: CLIENTES_CREDITO",         layer="source",    system="IBM DB2 Mainframe",       system_type="OTHER"),
    "rc18_db2_historico_scr":           dict(label="DB2: HISTORICO_SCR",            layer="source",    system="IBM DB2 Mainframe",       system_type="OTHER"),
    "rc18_db2_plano_contas_cosif":      dict(label="DB2: PLANO_CONTAS_COSIF",       layer="source",    system="IBM DB2 Mainframe",       system_type="OTHER"),
    # ETL
    "rc18_etl_scr3040_extractor":       dict(label="Informatica ETL: SCR3040",      layer="etl",       system="Informatica PowerCenter", system_type="OTHER"),
    "rc18_etl_scr3050_aggregator":      dict(label="Informatica ETL: SCR3050",      layer="etl",       system="Informatica PowerCenter", system_type="OTHER"),
    # BACEN validators
    "rc18_bacen_validador_scr3040":     dict(label="Validador BCB: Doc 3040",        layer="validator", system="BACEN Validador3040",     system_type="OTHER"),
    "rc18_bacen_validador_scr3050":     dict(label="Validador BCB: Doc 3050",        layer="validator", system="BACEN ValidadorMDR",      system_type="OTHER"),
    # Final submission
    "rc18_sta_cadip_doc3040":           dict(label="STA/CADIP: Doc 3040",           layer="output",    system="BACEN STA/CADIP",        system_type="OTHER"),
    "rc18_sta_cadip_doc3050":           dict(label="STA/CADIP: Doc 3050",           layer="output",    system="BACEN STA/CADIP",        system_type="OTHER"),
}


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
# Mock data — rich topology matching the BYOL topology, for local dev
# ---------------------------------------------------------------------------

def _build_mock(catalog: str) -> LineageGraphResponse:
    nodes = [
        # Origin systems — upstream of Oracle/DB2
        LineageNode(id="rc18_los_originacao_credito", label="LOS: Originacao de Credito", type="external_source", layer="origin", system="Loan Origination System", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="https://los-prod.bancorp.internal/api/v2", update_frequency="Tempo real — evento de aprovacao de credito")),
        LineageNode(id="rc18_crm_cadastro_clientes",  label="CRM: Cadastro de Clientes",  type="external_source", layer="origin", system="CRM / MDM Clientes",      system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="https://crm.bancorp.internal/sfdc", update_frequency="Batch diario 01h00 + atualizacoes em tempo real")),
        LineageNode(id="rc18_oracle_tb_operacoes_credito", label="Oracle: TB_OPERACOES_CREDITO", type="external_source", layer="source", system="Oracle Core Banking", system_type="ORACLE",
                    metadata=LineageNodeMetadata(connection="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO", update_frequency="CDC via ROWSCN 15 min")),
        LineageNode(id="rc18_oracle_tb_garantias",   label="Oracle: TB_GARANTIAS",    type="external_source", layer="source", system="Oracle Core Banking", system_type="ORACLE",
                    metadata=LineageNodeMetadata(connection="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO", update_frequency="CDC via ROWSCN")),
        LineageNode(id="rc18_oracle_tb_contratantes", label="Oracle: TB_CONTRATANTES", type="external_source", layer="source", system="Oracle Core Banking", system_type="ORACLE",
                    metadata=LineageNodeMetadata(connection="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO", update_frequency="Batch 02h00")),
        LineageNode(id="rc18_oracle_tb_cessoes_fidc", label="Oracle: TB_CESSOES_FIDC", type="external_source", layer="source", system="Oracle Core Banking", system_type="ORACLE",
                    metadata=LineageNodeMetadata(connection="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO", update_frequency="Batch mensal D-1")),
        LineageNode(id="rc18_db2_clientes_credito",   label="DB2: CLIENTES_CREDITO",   type="external_source", layer="source", system="IBM DB2 Mainframe", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="jdbc:db2://mainframe:50000/CLICRED", update_frequency="Batch 00h30")),
        LineageNode(id="rc18_db2_historico_scr",      label="DB2: HISTORICO_SCR",      type="external_source", layer="source", system="IBM DB2 Mainframe", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="jdbc:db2://mainframe:50000/HSCR", update_frequency="Pos-envio BCB")),
        LineageNode(id="rc18_db2_plano_contas_cosif", label="DB2: PLANO_CONTAS_COSIF", type="external_source", layer="source", system="IBM DB2 Mainframe", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="jdbc:db2://mainframe:50000/COSIF", update_frequency="Por publicacao BACEN")),
        LineageNode(id="rc18_etl_scr3040_extractor",  label="Informatica ETL: SCR3040", type="etl_process", layer="etl", system="Informatica PowerCenter", system_type="OTHER",
                    metadata=LineageNodeMetadata(update_frequency="Diario 22h00", connection="RC18_SCR3040_EXTRACT")),
        LineageNode(id="rc18_etl_scr3050_aggregator", label="Informatica ETL: SCR3050", type="etl_process", layer="etl", system="Informatica PowerCenter", system_type="OTHER",
                    metadata=LineageNodeMetadata(update_frequency="Semanal/Mensal 23h00", connection="RC18_SCR3050_AGG")),
        LineageNode(id=f"{catalog}.bronze.raw_3040_doc", label="raw_3040_doc", type="table", layer="bronze", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=1, last_updated="2026-03-31T23:15:00Z")),
        LineageNode(id=f"{catalog}.bronze.raw_3050_doc", label="raw_3050_doc", type="table", layer="bronze", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=1, last_updated="2026-03-31T23:15:00Z")),
        LineageNode(id=f"{catalog}.silver.operacoes", label="operacoes", type="table", layer="silver", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=1, last_updated="2026-03-31T01:30:00Z", expectations_pass_rate=99.9)),
        LineageNode(id=f"{catalog}.silver.clientes", label="clientes", type="table", layer="silver", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=1, last_updated="2026-03-31T01:30:00Z")),
        LineageNode(id=f"{catalog}.silver.quality_scorecard", label="quality_scorecard", type="table", layer="silver", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=15, last_updated="2026-03-31T02:00:00Z")),
        LineageNode(id=f"{catalog}.gold.posicao_mensal_3040", label="posicao_mensal_3040", type="table", layer="gold", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=0, last_updated="2026-03-31T04:00:00Z")),
        LineageNode(id=f"{catalog}.gold.posicao_3050", label="posicao_3050", type="table", layer="gold", catalog=catalog,
                    metadata=LineageNodeMetadata(row_count=0, last_updated="2026-03-31T04:00:00Z")),
        LineageNode(id="rc18_bacen_validador_scr3040", label="Validador BCB: Doc 3040", type="validator", layer="validator", system="BACEN Validador3040", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040")),
        LineageNode(id="rc18_bacen_validador_scr3050", label="Validador BCB: Doc 3050", type="validator", layer="validator", system="BACEN ValidadorMDR", system_type="OTHER",
                    metadata=LineageNodeMetadata(connection="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3050")),
        LineageNode(id="rc18_sta_cadip_doc3040", label="STA/CADIP: Doc 3040", type="external_output", layer="output", system="BACEN STA/CADIP", system_type="OTHER", metadata=LineageNodeMetadata()),
        LineageNode(id="rc18_sta_cadip_doc3050", label="STA/CADIP: Doc 3050", type="external_output", layer="output", system="BACEN STA/CADIP", system_type="OTHER", metadata=LineageNodeMetadata()),
    ]
    edges = [
        # Origin → Oracle/DB2
        LineageEdge(source="rc18_los_originacao_credito", target="rc18_oracle_tb_operacoes_credito", type="external_lineage", label="aprovacao credito",
                    column_mappings=[ColumnMapping(source="NR_PROPOSTA", target="NR_CONTRATO"), ColumnMapping(source="VLR_APROVADO", target="VLR_CONTABIL_BRL"), ColumnMapping(source="CD_PRODUTO", target="CD_MODALIDADE")]),
        LineageEdge(source="rc18_los_originacao_credito", target="rc18_oracle_tb_garantias",    type="external_lineage", label="registro garantia",
                    column_mappings=[ColumnMapping(source="CD_TIPO_GARANTIA", target="CD_TIPO_GARANTIA"), ColumnMapping(source="VLR_GARANTIA", target="VLR_GARANTIA")]),
        LineageEdge(source="rc18_los_originacao_credito", target="rc18_oracle_tb_cessoes_fidc", type="external_lineage", label="cessao FIDC"),
        LineageEdge(source="rc18_crm_cadastro_clientes",  target="rc18_oracle_tb_contratantes", type="external_lineage", label="sync cadastro",
                    column_mappings=[ColumnMapping(source="CD_CNPJ_CPF", target="CD_CNPJ_CPF"), ColumnMapping(source="NM_CLIENTE", target="NM_CLIENTE"), ColumnMapping(source="CD_SEG_PORTE", target="CD_SEG_PORTE")]),
        LineageEdge(source="rc18_crm_cadastro_clientes",  target="rc18_db2_clientes_credito",   type="external_lineage", label="replica mainframe"),
        # Oracle/DB2 → ETL
        LineageEdge(source="rc18_oracle_tb_operacoes_credito", target="rc18_etl_scr3040_extractor", type="external_lineage", label="CDC extract",
                    column_mappings=[ColumnMapping(source="CD_CNPJ_IF", target="cnpj_if"), ColumnMapping(source="CD_IPOC", target="ipoc"), ColumnMapping(source="VLR_CONTABIL_BRL", target="vlr_contabil")]),
        LineageEdge(source="rc18_oracle_tb_garantias",    target="rc18_etl_scr3040_extractor",  type="external_lineage", label="JOIN via IPOC"),
        LineageEdge(source="rc18_oracle_tb_contratantes", target="rc18_etl_scr3040_extractor",  type="external_lineage", label="lookup contratante"),
        LineageEdge(source="rc18_oracle_tb_cessoes_fidc", target="rc18_etl_scr3040_extractor",  type="external_lineage", label="LEFT JOIN cessoes"),
        LineageEdge(source="rc18_db2_clientes_credito",   target="rc18_etl_scr3040_extractor",  type="external_lineage", label="DRDA lookup"),
        LineageEdge(source="rc18_db2_historico_scr",      target="rc18_etl_scr3050_aggregator", type="external_lineage", label="agregacao mensal"),
        LineageEdge(source="rc18_db2_plano_contas_cosif", target="rc18_etl_scr3050_aggregator", type="external_lineage", label="lookup COSIF"),
        LineageEdge(source="rc18_etl_scr3040_extractor",  target=f"{catalog}.bronze.raw_3040_doc", type="external_lineage", label="XML -> Auto Loader",
                    column_mappings=[ColumnMapping(source="ipoc", target="header.CD_IPOC"), ColumnMapping(source="vlr_contabil", target="operacoes[0].VLR_CONTABIL")]),
        LineageEdge(source="rc18_etl_scr3050_aggregator", target=f"{catalog}.bronze.raw_3050_doc", type="external_lineage", label="TXB/XML -> Auto Loader"),
        LineageEdge(source=f"{catalog}.bronze.raw_3040_doc", target=f"{catalog}.silver.operacoes", type="uc_automatic", label="DLT silver pipeline"),
        LineageEdge(source=f"{catalog}.bronze.raw_3040_doc", target=f"{catalog}.silver.clientes",  type="uc_automatic", label="DLT silver pipeline"),
        LineageEdge(source=f"{catalog}.silver.operacoes", target=f"{catalog}.gold.posicao_mensal_3040", type="uc_automatic", label="DLT gold pipeline"),
        LineageEdge(source=f"{catalog}.bronze.raw_3050_doc",        target=f"{catalog}.gold.posicao_3050",        type="uc_automatic", label="DLT gold pipeline"),
        LineageEdge(source=f"{catalog}.silver.quality_scorecard",   target=f"{catalog}.gold.posicao_mensal_3040", type="uc_automatic", label="quality gate"),
        LineageEdge(source=f"{catalog}.gold.posicao_mensal_3040", target="rc18_bacen_validador_scr3040", type="external_lineage", label="export XML"),
        LineageEdge(source=f"{catalog}.gold.posicao_3050",         target="rc18_bacen_validador_scr3050", type="external_lineage", label="export TXB/XML"),
        LineageEdge(source="rc18_bacen_validador_scr3040", target="rc18_sta_cadip_doc3040", type="external_lineage", label="SFTP transmissao"),
        LineageEdge(source="rc18_bacen_validador_scr3050", target="rc18_sta_cadip_doc3050", type="external_lineage", label="SFTP transmissao"),
    ]
    return LineageGraphResponse(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Real mode: merge BYOL + UC automatic lineage
# ---------------------------------------------------------------------------

async def _fetch_real_lineage(catalog: str) -> LineageGraphResponse:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.catalog import (
        ExternalLineageObject, ExternalLineageTable,
        ExternalLineageExternalMetadata, LineageDirection,
    )
    from db import execute_query_or_empty as execute_query

    w = WorkspaceClient()
    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []
    seen_rel_ids: set[str] = set()

    # 1. Load all rc18_* external metadata objects
    try:
        all_meta = list(w.external_metadata.list_external_metadata())
        rc18_meta = {m.name: m for m in all_meta if m.name and m.name.startswith("rc18_")}
        for name, m in rc18_meta.items():
            info = _EXT_META.get(name, {})
            etype = m.entity_type or "TABLE"
            nodes[name] = LineageNode(
                id=name,
                label=info.get("label", name),
                type="etl_process" if etype == "PROCESS" else ("external_output" if etype == "DATASET" else "external_source"),
                layer=info.get("layer", "source"),
                system=info.get("system", m.system_type.value if m.system_type else "OTHER"),
                system_type=info.get("system_type", "OTHER"),
                metadata=LineageNodeMetadata(
                    connection=m.url,
                    update_frequency=(m.properties or {}).get("update_mode"),
                ),
            )
    except Exception as e:
        logger.warning("Could not load external metadata: %s", e)
        rc18_meta = {}

    def _ensure_uc_node(fqn: str) -> None:
        if fqn not in nodes:
            nodes[fqn] = LineageNode(
                id=fqn, label=_short_label(fqn), type="table",
                layer=_uc_layer(fqn),
                catalog=fqn.split(".")[0] if "." in fqn else None,
                metadata=LineageNodeMetadata(),
            )

    def _ensure_ext_node(name: str) -> None:
        if name not in nodes:
            mo = rc18_meta.get(name)
            if mo:
                info = _EXT_META.get(name, {})
                etype = mo.entity_type or "TABLE"
                nodes[name] = LineageNode(
                    id=name,
                    label=info.get("label", name),
                    type="etl_process" if etype == "PROCESS" else ("external_output" if etype == "DATASET" else "external_source"),
                    layer=info.get("layer", "source"),
                    system=info.get("system", "OTHER"),
                    system_type=info.get("system_type", "OTHER"),
                    metadata=LineageNodeMetadata(connection=mo.url),
                )
            else:
                nodes[name] = LineageNode(id=name, label=_short_label(name), type="external_source", layer="source", metadata=LineageNodeMetadata())

    # 2. BYOL relationships for Bronze/Gold boundary tables
    for cat, schema, table in [
        (catalog, "bronze", "raw_3040_doc"),
        (catalog, "bronze", "raw_3050_doc"),
        (catalog, "gold",   "posicao_mensal_3040"),
        (catalog, "gold",   "posicao_3050"),
    ]:
        fqn = f"{cat}.{schema}.{table}"
        _ensure_uc_node(fqn)
        uc_ref = ExternalLineageObject(table=ExternalLineageTable(name=fqn))
        for direction in [LineageDirection.UPSTREAM, LineageDirection.DOWNSTREAM]:
            try:
                for info in w.external_lineage.list_external_lineage_relationships(uc_ref, direction):
                    rel = info.external_lineage_info
                    if not rel or rel.id in seen_rel_ids:
                        continue
                    seen_rel_ids.add(rel.id)
                    if info.external_metadata_info:
                        neighbor = info.external_metadata_info.name
                        _ensure_ext_node(neighbor)
                    elif info.table_info:
                        neighbor = info.table_info.name
                        _ensure_uc_node(neighbor)
                    else:
                        continue
                    src, tgt = (neighbor, fqn) if direction == LineageDirection.UPSTREAM else (fqn, neighbor)
                    col_maps = [ColumnMapping(source=c.source, target=c.target) for c in (rel.columns or []) if c.source and c.target]
                    props = rel.properties or {}
                    label = props.get("mechanism") or props.get("transform") or "BYOL"
                    edges.append(LineageEdge(source=src, target=tgt, type="external_lineage", label=label, column_mappings=col_maps))
            except Exception as e:
                logger.warning("BYOL query failed %s %s: %s", fqn, direction.value, e)

    # 3. External-to-external BYOL edges (sources->ETL, validator->STA/CADIP)
    for name in list(rc18_meta.keys()):
        ext_ref = ExternalLineageObject(external_metadata=ExternalLineageExternalMetadata(name=name))
        try:
            for info in w.external_lineage.list_external_lineage_relationships(ext_ref, LineageDirection.DOWNSTREAM):
                rel = info.external_lineage_info
                if not rel or rel.id in seen_rel_ids:
                    continue
                seen_rel_ids.add(rel.id)
                if info.external_metadata_info:
                    neighbor = info.external_metadata_info.name
                    _ensure_ext_node(neighbor)
                elif info.table_info:
                    neighbor = info.table_info.name
                    _ensure_uc_node(neighbor)
                else:
                    continue
                col_maps = [ColumnMapping(source=c.source, target=c.target) for c in (rel.columns or []) if c.source and c.target]
                props = rel.properties or {}
                label = props.get("transform") or props.get("mechanism") or "BYOL"
                edges.append(LineageEdge(source=name, target=neighbor, type="external_lineage", label=label, column_mappings=col_maps))
        except Exception as e:
            logger.debug("ext-ext BYOL query failed for %s: %s", name, e)

    # 4. UC automatic lineage (DLT Bronze -> Silver -> Gold)
    try:
        rows = await execute_query(
            "SELECT DISTINCT source_table_full_name, target_table_full_name "
            "FROM system.access.table_lineage "
            "WHERE (target_table_catalog = :catalog OR source_table_catalog = :catalog) "
            "  AND event_time > CURRENT_TIMESTAMP() - INTERVAL 30 DAYS "
            "  AND source_table_full_name IS NOT NULL "
            "  AND target_table_full_name IS NOT NULL",
            {"catalog": catalog},
        )
        for r in rows:
            src, tgt = r["source_table_full_name"], r["target_table_full_name"]
            _ensure_uc_node(src)
            _ensure_uc_node(tgt)
            edges.append(LineageEdge(source=src, target=tgt, type="uc_automatic", label="DLT pipeline"))
    except Exception as e:
        logger.warning("UC system table lineage query failed: %s", e)

    return LineageGraphResponse(nodes=list(nodes.values()), edges=edges)


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
                    UpstreamColumn(table=f"{CATALOG}.silver.operacoes", column="ipoc", transformation="passthrough"),
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
