"""In-memory store for External Metadata + External Lineage, used ONLY in mock
mode (``USE_MOCK_BACKEND=true``).

Why a store (and not a static fixture)?
The Lineage module is now a read/write surface: the app lets a user register
external systems and lineage relationships that write through to the Unity
Catalog External Metadata / External Lineage APIs. For the local devloop to be
useful, creating an object in the form must immediately show up in the graph —
so the CRUD endpoints and the graph builder must share one source of truth.

In real mode (``USE_MOCK_BACKEND=false``) this store is never touched; the
router talks to the live UC APIs instead.

The seed models a **mixed-integration** RC18 topology (per the customer choice
"real por fonte"): a COBOL/mainframe source that crosses the boundary as a file
drop + Auto Loader, an Oracle Core Banking source federated via Lakehouse
Federation, and a SQL Server cadastro ingested via Lakeflow Connect — plus the
post-Databricks BACEN validators and STA/CADIP delivery. It is intentionally
smaller than the old 16-object fixture: it is a starting point the user edits,
not the truth.
"""

from __future__ import annotations

import copy
import threading

from models import (
    ColumnMapping,
    ExternalLineageEndpoint,
    ExternalLineageRelationship,
    ExternalMetadataObject,
)

# ---------------------------------------------------------------------------
# Graph vocabulary shared with the frontend layout (LAYER_ORDER in +page.svelte)
# ---------------------------------------------------------------------------

# The 8 medallion-flanking layers, left → right. Stored on each external object
# as the ``camada`` property so the user controls placement from the form.
LAYERS = ["origin", "source", "etl", "bronze", "silver", "gold", "validator", "output"]

# How an external source crosses the Databricks boundary. Drives the crossing
# edge style/legend and reflects the mixed-integration reality.
INGESTION_MODES = ["file_autoloader", "federation", "lakeflow_connect"]

# camada → graph layer fallback when ``camada`` is not already a known layer.
_CAMADA_ALIAS = {
    "origem": "source",
    "orquestracao-legada": "etl",
    "calculo-legado": "etl",
    "formatacao-legada": "etl",
    "persistencia-legada": "source",
    "integracao": "etl",
    "consumo": "output",
    "entregavel": "output",
    "entregavel-legado": "output",
    "entregavel-databricks": "gold",
    "validador": "validator",
    "saida": "output",
}


def derive_layer(properties: dict[str, str] | None, entity_type: str | None) -> str:
    """Best-effort graph layer for an external object.

    Priority: explicit known layer in ``camada`` → aliased camada → entity_type
    heuristic → ``source``.
    """
    props = properties or {}
    camada = (props.get("camada") or props.get("layer") or "").strip().lower()
    if camada in LAYERS:
        return camada
    if camada in _CAMADA_ALIAS:
        return _CAMADA_ALIAS[camada]
    et = (entity_type or "").strip().upper()
    if et in ("PROCESS", "JOB"):
        return "etl"
    if et in ("DATASET", "FILE"):
        return "output"
    return "source"


def derive_node_type(layer: str, entity_type: str | None) -> str:
    """Map (layer, entity_type) to the frontend node ``type`` used for styling.

    Layer wins over entity_type: a COBOL JOB sitting in the ``origin`` layer is
    a source of data, not an ETL step, so it renders as ``external_source``.
    Only objects explicitly placed in the ``etl`` layer render as processes.
    """
    et = (entity_type or "").strip().upper()
    if layer == "validator":
        return "validator"
    if layer == "output":
        return "external_output"
    if layer == "etl" or (layer not in ("origin", "source") and et in ("PROCESS", "JOB")):
        return "etl_process"
    return "external_source"


# ---------------------------------------------------------------------------
# Demo seed — mixed-integration RC18 chain
# ---------------------------------------------------------------------------

def _seed_objects() -> dict[str, ExternalMetadataObject]:
    objs = [
        # ── Legacy mainframe (COBOL) — crosses boundary as file drop + Auto Loader
        ExternalMetadataObject(
            name="rc18_cobol_scr_batch",
            system_type="OTHER",
            entity_type="JOB",
            description=(
                "Rotina COBOL batch (z/OS) que extrai as operações de crédito do "
                "core legado e grava o arquivo posicional do CADOC 3040. Origem "
                "fora do Spark — entra no Databricks como arquivo no volume landing."
            ),
            url="mainframe://prod/SCRBATCH/PGM3040",
            columns=["CD_IPOC", "CD_CNPJ_IF", "CD_MODALIDADE", "VLR_CONTABIL", "DT_CONTRATACAO"],
            properties={
                "camada": "origin",
                "sistema": "IBM z/OS COBOL",
                "ingestion_mode": "file_autoloader",
                "update_mode": "Batch diário 22h00 — arquivo posicional EBCDIC",
                "data_owner": "TI — Sistemas Legados",
            },
        ),
        # ── Oracle Core Banking — Lakehouse Federation (foreign catalog)
        ExternalMetadataObject(
            name="rc18_oracle_tb_operacoes_credito",
            system_type="ORACLE",
            entity_type="TABLE",
            description=(
                "Tabela de operações de crédito no Core Banking Oracle. Exposta ao "
                "Databricks via Lakehouse Federation (foreign catalog) — leitura "
                "federada sem cópia física para o bronze."
            ),
            url="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO",
            columns=["CD_IPOC", "CD_CNPJ_IF", "CD_MODALIDADE", "VLR_CONTABIL_BRL", "DT_CONTRATACAO", "CD_TIPO_RISCO"],
            properties={
                "camada": "source",
                "sistema": "Oracle Core Banking 19c",
                "ingestion_mode": "federation",
                "update_mode": "Federado — leitura on-demand via foreign catalog",
                "data_owner": "Diretoria de Crédito",
            },
        ),
        # ── SQL Server cadastro — Lakeflow Connect managed ingestion
        ExternalMetadataObject(
            name="rc18_sqlserver_cadastro_clientes",
            system_type="MICROSOFT_SQL_SERVER",
            entity_type="TABLE",
            description=(
                "Cadastro mestre de clientes em Microsoft SQL Server. Ingerido no "
                "Databricks via Lakeflow Connect (conector gerenciado) — CDC "
                "incremental para o bronze."
            ),
            url="jdbc:sqlserver://cadastro-prod.bancorp.internal:1433;database=MDM",
            columns=["CD_CLIENTE", "CD_CNPJ_CPF", "NM_CLIENTE", "CD_SEG_PORTE", "CD_MUNICIPIO"],
            properties={
                "camada": "source",
                "sistema": "Microsoft SQL Server 2022",
                "ingestion_mode": "lakeflow_connect",
                "update_mode": "CDC via Lakeflow Connect — incremental 15 min",
                "data_owner": "Diretoria de Relacionamento",
            },
        ),
        # ── Output side — BACEN validators + STA/CADIP
        ExternalMetadataObject(
            name="rc18_bacen_validador_scr3040",
            system_type="OTHER",
            entity_type="PROCESS",
            description=(
                "Validador oficial BACEN (Validador3040). Aplica críticas "
                "sintáticas/semânticas antes do envio ao STA/CADIP."
            ),
            url="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040",
            columns=["arquivo_xml", "resultado", "cnt_criticas", "dt_validacao"],
            properties={
                "camada": "validator",
                "sistema": "BACEN Validador3040",
                "r18_compliance": "Validação obrigatória antes do STA/CADIP",
            },
        ),
        ExternalMetadataObject(
            name="rc18_sta_cadip_doc3040",
            system_type="OTHER",
            entity_type="DATASET",
            description=(
                "Canal STA/CADIP do BACEN — destino final do CADOC 3040 validado. "
                "Fecha a cadeia de rastreabilidade exigida pela R.18."
            ),
            url="https://www.bcb.gov.br/acessoinformacao/legenda_sistemas_informacoes#STA",
            columns=["cd_protocolo_bcb", "dt_envio", "dt_competencia", "status_processamento_bcb"],
            properties={
                "camada": "output",
                "sistema": "BACEN STA/CADIP",
                "retention": "5 anos — R.18 Art. 6",
            },
        ),
    ]
    return {o.name: o for o in objs}


def _seed_relationships(catalog: str) -> list[ExternalLineageRelationship]:
    def ext(n: str) -> ExternalLineageEndpoint:
        return ExternalLineageEndpoint(external_metadata_name=n)

    def tbl(schema: str, table: str) -> ExternalLineageEndpoint:
        return ExternalLineageEndpoint(table_name=f"{catalog}.{schema}.{table}")

    def cm(pairs: list[tuple[str, str]]) -> list[ColumnMapping]:
        return [ColumnMapping(source=s, target=t) for s, t in pairs]

    return [
        # Legacy COBOL → bronze (file drop + Auto Loader)
        ExternalLineageRelationship(
            id="seed-cobol-bronze",
            source=ext("rc18_cobol_scr_batch"),
            target=tbl("bronze", "raw_3040_doc"),
            columns=cm([("CD_IPOC", "header.CD_IPOC"), ("VLR_CONTABIL", "operacoes[0].VLR_CONTABIL")]),
            properties={"mechanism": "Arquivo posicional → Auto Loader (cloudFiles)", "ingestion_mode": "file_autoloader"},
        ),
        # Oracle (federation) → bronze
        ExternalLineageRelationship(
            id="seed-oracle-bronze",
            source=ext("rc18_oracle_tb_operacoes_credito"),
            target=tbl("bronze", "raw_3040_doc"),
            columns=cm([("CD_IPOC", "header.CD_IPOC"), ("VLR_CONTABIL_BRL", "operacoes[0].VLR_CONTABIL")]),
            properties={"mechanism": "Lakehouse Federation — leitura federada", "ingestion_mode": "federation"},
        ),
        # SQL Server (Lakeflow Connect) → bronze
        ExternalLineageRelationship(
            id="seed-sqlserver-bronze",
            source=ext("rc18_sqlserver_cadastro_clientes"),
            target=tbl("bronze", "raw_3040_doc"),
            columns=cm([("CD_CNPJ_CPF", "header.CD_CNPJ_CPF"), ("NM_CLIENTE", "clientes[0].NM_CLIENTE")]),
            properties={"mechanism": "Lakeflow Connect — ingestão gerenciada CDC", "ingestion_mode": "lakeflow_connect"},
        ),
        # gold → validador (export)
        ExternalLineageRelationship(
            id="seed-gold-validador",
            source=tbl("gold", "posicao_3040"),
            target=ext("rc18_bacen_validador_scr3040"),
            columns=cm([("cnpj_if", "CD_CNPJ_IF"), ("ipoc", "CD_IPOC"), ("vlr_contabil", "VLR_CONTABIL")]),
            properties={"mechanism": "Exportação XML a partir do Gold → Validador3040"},
        ),
        # validador → STA/CADIP (final delivery)
        ExternalLineageRelationship(
            id="seed-validador-sta",
            source=ext("rc18_bacen_validador_scr3040"),
            target=ext("rc18_sta_cadip_doc3040"),
            properties={"mechanism": "SFTP/HTTPS → portal STA BCB", "precondition": "Zero críticas de ERRO"},
        ),
    ]


# ---------------------------------------------------------------------------
# Store state (mock mode only) — guarded by a lock for multi-worker safety
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_meta: dict[str, ExternalMetadataObject] | None = None
_rels: list[ExternalLineageRelationship] | None = None
_rel_seq = 0


def _ensure(catalog: str) -> None:
    global _meta, _rels
    if _meta is None or _rels is None:
        _meta = _seed_objects()
        _rels = _seed_relationships(catalog)


# ── External metadata CRUD ────────────────────────────────────────────────

def list_metadata(catalog: str) -> list[ExternalMetadataObject]:
    with _lock:
        _ensure(catalog)
        return [copy.deepcopy(o) for o in _meta.values()]


def get_metadata(catalog: str, name: str) -> ExternalMetadataObject | None:
    with _lock:
        _ensure(catalog)
        o = _meta.get(name)
        return copy.deepcopy(o) if o else None


def create_metadata(catalog: str, obj: ExternalMetadataObject) -> ExternalMetadataObject:
    with _lock:
        _ensure(catalog)
        if obj.name in _meta:
            raise KeyError(obj.name)
        stored = copy.deepcopy(obj)
        stored.id = stored.id or f"mock-{obj.name}"
        _meta[obj.name] = stored
        return copy.deepcopy(stored)


def update_metadata(catalog: str, name: str, patch: dict) -> ExternalMetadataObject | None:
    with _lock:
        _ensure(catalog)
        existing = _meta.get(name)
        if not existing:
            return None
        data = existing.model_dump()
        for k, v in patch.items():
            if v is not None:
                data[k] = v
        updated = ExternalMetadataObject(**data)
        _meta[name] = updated
        return copy.deepcopy(updated)


def delete_metadata(catalog: str, name: str) -> bool:
    with _lock:
        _ensure(catalog)
        if name not in _meta:
            return False
        del _meta[name]
        # Cascade: drop relationships that referenced this object.
        _rels[:] = [
            r for r in _rels
            if r.source.external_metadata_name != name and r.target.external_metadata_name != name
        ]
        return True


# ── External lineage relationships ────────────────────────────────────────

def list_relationships(catalog: str) -> list[ExternalLineageRelationship]:
    with _lock:
        _ensure(catalog)
        return [copy.deepcopy(r) for r in _rels]


def create_relationship(
    catalog: str, req: ExternalLineageRelationship
) -> ExternalLineageRelationship:
    global _rel_seq
    with _lock:
        _ensure(catalog)
        _rel_seq += 1
        stored = copy.deepcopy(req)
        stored.id = stored.id or f"mock-rel-{_rel_seq}"
        _rels.append(stored)
        return copy.deepcopy(stored)


def delete_relationship(catalog: str, rel_id: str) -> bool:
    with _lock:
        _ensure(catalog)
        before = len(_rels)
        _rels[:] = [r for r in _rels if r.id != rel_id]
        return len(_rels) < before
