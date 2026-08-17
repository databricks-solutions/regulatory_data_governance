# Databricks notebook source
# MAGIC %md
# MAGIC # RC18 — Bring Your Own Lineage (BYOL) — DEMO SEED
# MAGIC
# MAGIC **This notebook only SEEDS a small, realistic starting topology.** In the
# MAGIC RC18 app, the customer manages the real external lineage through the
# MAGIC **Linhagem** page (a write-through UI over the same External Metadata /
# MAGIC External Lineage APIs). This seed exists so a fresh deploy shows an
# MAGIC end-to-end graph before the customer registers their own systems.
# MAGIC
# MAGIC ## What it registers (mixed integration — "real por fonte")
# MAGIC The seed mirrors `app/backend/external_lineage_store.py` so the deployed
# MAGIC (real) graph matches what the local mock shows:
# MAGIC
# MAGIC ```
# MAGIC COBOL batch (z/OS)  ──[arquivo + Auto Loader]──┐
# MAGIC Oracle Core Banking ──[Lakehouse Federation]──┤─→ bronze.raw_3040_doc
# MAGIC SQL Server cadastro ──[Lakeflow Connect]──────┘        │ (DLT silver/gold — UC automatic)
# MAGIC                                                        ▼
# MAGIC                                              gold.posicao_3040
# MAGIC                                                        │ [export]
# MAGIC                                                        ▼
# MAGIC                                          Validador BCB 3040 ──[SFTP]──→ STA/CADIP
# MAGIC ```
# MAGIC
# MAGIC The three source→bronze edges each carry a distinct `ingestion_mode`
# MAGIC property (`file_autoloader` / `federation` / `lakeflow_connect`) — the app
# MAGIC renders them and the side panel surfaces the mode.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC - User (or app SP) with `CREATE EXTERNAL METADATA` on the metastore.
# MAGIC - Run after `bundle deploy` and `setup_reference_tables`.
# MAGIC
# MAGIC ## Idempotency
# MAGIC Deletes all `rc18_*` external metadata objects before recreating — safe to
# MAGIC re-run. NOTE: customer objects created via the app UI should NOT use the
# MAGIC `rc18_` prefix if they must survive a re-seed (the teardown targets `rc18_`).

# COMMAND ----------

dbutils.widgets.text("catalog",        "rc18_catalog", "Catalog")
dbutils.widgets.text("bronze_schema",  "bronze",        "Bronze Schema")
dbutils.widgets.text("silver_schema",  "silver",        "Silver Schema")
dbutils.widgets.text("gold_schema",    "gold",          "Gold Schema")

catalog       = dbutils.widgets.get("catalog")
bronze_schema = dbutils.widgets.get("bronze_schema")
gold_schema   = dbutils.widgets.get("gold_schema")

print(f"catalog={catalog}  bronze={bronze_schema}  gold={gold_schema}")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    ExternalMetadata,
    SystemType,
    CreateRequestExternalLineage,
    ExternalLineageObject,
    ExternalLineageExternalMetadata,
    ExternalLineageTable,
    ColumnRelationship,
    LineageDirection,
)

w = WorkspaceClient()
print(f"Connected to: {w.config.host}")


def fq(schema: str, table: str) -> str:
    return f"{catalog}.{schema}.{table}"


def ext_obj(name: str) -> ExternalLineageObject:
    return ExternalLineageObject(external_metadata=ExternalLineageExternalMetadata(name=name))


def uc_obj(schema: str, table: str) -> ExternalLineageObject:
    return ExternalLineageObject(table=ExternalLineageTable(name=fq(schema, table)))


def col(src: str, tgt: str) -> ColumnRelationship:
    return ColumnRelationship(source=src, target=tgt)

# COMMAND ----------

# MAGIC %md ## 1 — Teardown: remove existing rc18_* objects (idempotency)

# COMMAND ----------

existing = list(w.external_metadata.list_external_metadata())
to_delete = [m for m in existing if m.name and m.name.startswith("rc18_")]
for m in to_delete:
    try:
        w.external_metadata.delete_external_metadata(m.name)
        print(f"  Deleted: {m.name}")
    except Exception as e:
        print(f"  Warning — could not delete {m.name}: {e}")
print(f"Removed {len(to_delete)} existing rc18_* objects")

# COMMAND ----------

# MAGIC %md ## 2 — Create External Metadata Objects (mixed integration)

# COMMAND ----------

OBJECTS = [
    # ── Legacy mainframe (COBOL) — crosses the boundary as a file drop + Auto Loader
    ExternalMetadata(
        name="rc18_cobol_scr_batch",
        system_type=SystemType.OTHER,   # COBOL/mainframe is not in the enum → OTHER; real name in `sistema`
        entity_type="JOB",
        description=(
            "Rotina COBOL batch (z/OS) que extrai as operacoes de credito do core "
            "legado e grava o arquivo posicional do CADOC 3040. Origem fora do Spark "
            "— entra no Databricks como arquivo no volume landing."
        ),
        url="mainframe://prod/SCRBATCH/PGM3040",
        columns=["CD_IPOC", "CD_CNPJ_IF", "CD_MODALIDADE", "VLR_CONTABIL", "DT_CONTRATACAO"],
        properties={
            "camada":         "origin",
            "sistema":        "IBM z/OS COBOL",
            "ingestion_mode": "file_autoloader",
            "update_mode":    "Batch diario 22h00 — arquivo posicional EBCDIC",
            "data_owner":     "TI — Sistemas Legados",
        },
    ),
    # ── Oracle Core Banking — Lakehouse Federation (foreign catalog)
    ExternalMetadata(
        name="rc18_oracle_tb_operacoes_credito",
        system_type=SystemType.ORACLE,
        entity_type="TABLE",
        description=(
            "Tabela de operacoes de credito no Core Banking Oracle. Exposta ao "
            "Databricks via Lakehouse Federation (foreign catalog) — leitura "
            "federada sem copia fisica para o bronze."
        ),
        url="jdbc:oracle:thin:@core-banking-prod:1521/CREDITO",
        columns=["CD_IPOC", "CD_CNPJ_IF", "CD_MODALIDADE", "VLR_CONTABIL_BRL", "DT_CONTRATACAO", "CD_TIPO_RISCO"],
        properties={
            "camada":         "source",
            "sistema":        "Oracle Core Banking 19c",
            "ingestion_mode": "federation",
            "update_mode":    "Federado — leitura on-demand via foreign catalog",
            "data_owner":     "Diretoria de Credito",
        },
    ),
    # ── SQL Server cadastro — Lakeflow Connect managed ingestion
    ExternalMetadata(
        name="rc18_sqlserver_cadastro_clientes",
        system_type=SystemType.MICROSOFT_SQL_SERVER,
        entity_type="TABLE",
        description=(
            "Cadastro mestre de clientes em Microsoft SQL Server. Ingerido no "
            "Databricks via Lakeflow Connect (conector gerenciado) — CDC "
            "incremental para o bronze."
        ),
        url="jdbc:sqlserver://cadastro-prod.bancorp.internal:1433;database=MDM",
        columns=["CD_CLIENTE", "CD_CNPJ_CPF", "NM_CLIENTE", "CD_SEG_PORTE", "CD_MUNICIPIO"],
        properties={
            "camada":         "source",
            "sistema":        "Microsoft SQL Server 2022",
            "ingestion_mode": "lakeflow_connect",
            "update_mode":    "CDC via Lakeflow Connect — incremental 15 min",
            "data_owner":     "Diretoria de Relacionamento",
        },
    ),
    # ── Output side — BACEN validator + STA/CADIP
    ExternalMetadata(
        name="rc18_bacen_validador_scr3040",
        system_type=SystemType.OTHER,
        entity_type="PROCESS",
        description=(
            "Validador oficial BACEN (Validador3040). Aplica criticas sintaticas/"
            "semanticas antes do envio ao STA/CADIP."
        ),
        url="https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040",
        columns=["arquivo_xml", "resultado", "cnt_criticas", "dt_validacao"],
        properties={
            "camada":         "validator",
            "sistema":        "BACEN Validador3040",
            "r18_compliance": "Validacao obrigatoria antes do STA/CADIP",
        },
    ),
    ExternalMetadata(
        name="rc18_sta_cadip_doc3040",
        system_type=SystemType.OTHER,
        entity_type="DATASET",
        description=(
            "Canal STA/CADIP do BACEN — destino final do CADOC 3040 validado. "
            "Fecha a cadeia de rastreabilidade exigida pela R.18."
        ),
        url="https://www.bcb.gov.br/acessoinformacao/legenda_sistemas_informacoes#STA",
        columns=["cd_protocolo_bcb", "dt_envio", "dt_competencia", "status_processamento_bcb"],
        properties={
            "camada":    "output",
            "sistema":   "BACEN STA/CADIP",
            "retention": "5 anos — R.18 Art. 6",
        },
    ),
]

created = []
for obj in OBJECTS:
    try:
        result = w.external_metadata.create_external_metadata(obj)
        created.append(result.name)
        print(f"  OK  {result.name}  ({obj.system_type.value}, {obj.entity_type})")
    except Exception as e:
        print(f"  ERR {obj.name}: {e}")

print(f"\nCreated {len(created)}/{len(OBJECTS)} external metadata objects")

# COMMAND ----------

# MAGIC %md ## 3 — Create External Lineage Relationships
# MAGIC
# MAGIC Three source→bronze edges (one per ingestion mode), a gold→validator
# MAGIC export, and a validator→STA delivery. Bronze→silver→gold is UC-automatic
# MAGIC (DLT) and is NOT registered here.

# COMMAND ----------

RELATIONSHIPS = [
    # COBOL → bronze (file drop + Auto Loader)
    dict(
        source=ext_obj("rc18_cobol_scr_batch"),
        target=uc_obj(bronze_schema, "raw_3040_doc"),
        columns=[col("CD_IPOC", "header.CD_IPOC"), col("VLR_CONTABIL", "operacoes[0].VLR_CONTABIL")],
        properties={"mechanism": "Arquivo posicional -> Auto Loader (cloudFiles)", "ingestion_mode": "file_autoloader"},
    ),
    # Oracle (federation) → bronze
    dict(
        source=ext_obj("rc18_oracle_tb_operacoes_credito"),
        target=uc_obj(bronze_schema, "raw_3040_doc"),
        columns=[col("CD_IPOC", "header.CD_IPOC"), col("VLR_CONTABIL_BRL", "operacoes[0].VLR_CONTABIL")],
        properties={"mechanism": "Lakehouse Federation — leitura federada", "ingestion_mode": "federation"},
    ),
    # SQL Server (Lakeflow Connect) → bronze
    dict(
        source=ext_obj("rc18_sqlserver_cadastro_clientes"),
        target=uc_obj(bronze_schema, "raw_3040_doc"),
        columns=[col("CD_CNPJ_CPF", "header.CD_CNPJ_CPF"), col("NM_CLIENTE", "clientes[0].NM_CLIENTE")],
        properties={"mechanism": "Lakeflow Connect — ingestao gerenciada CDC", "ingestion_mode": "lakeflow_connect"},
    ),
    # gold → validador (export)
    dict(
        source=uc_obj(gold_schema, "posicao_3040"),
        target=ext_obj("rc18_bacen_validador_scr3040"),
        columns=[col("cnpj_if", "CD_CNPJ_IF"), col("ipoc", "CD_IPOC"), col("vlr_contabil", "VLR_CONTABIL")],
        properties={"mechanism": "Exportacao XML a partir do Gold -> Validador3040"},
    ),
    # validador → STA/CADIP (final delivery)
    dict(
        source=ext_obj("rc18_bacen_validador_scr3040"),
        target=ext_obj("rc18_sta_cadip_doc3040"),
        properties={"mechanism": "SFTP/HTTPS -> portal STA BCB", "precondition": "Zero criticas de ERRO"},
    ),
]

created_rels = []
for i, rel in enumerate(RELATIONSHIPS):
    req = CreateRequestExternalLineage(
        source=rel["source"],
        target=rel["target"],
        columns=rel.get("columns"),
        properties=rel.get("properties"),
    )
    try:
        result = w.external_lineage.create_external_lineage_relationship(req)
        created_rels.append(result.id)
        src = (rel["source"].external_metadata.name if rel["source"].external_metadata
               else rel["source"].table.name)
        tgt = (rel["target"].external_metadata.name if rel["target"].external_metadata
               else rel["target"].table.name)
        print(f"  OK  {src}  ->  {tgt}")
    except Exception as e:
        print(f"  ERR relationship {i+1}: {e}")

print(f"\nCreated {len(created_rels)}/{len(RELATIONSHIPS)} lineage relationships")

# COMMAND ----------

# MAGIC %md ## 4 — Verify

# COMMAND ----------

print("External metadata objects (rc18_*):")
all_meta = list(w.external_metadata.list_external_metadata())
rc18 = sorted([m for m in all_meta if m.name and m.name.startswith("rc18_")], key=lambda x: x.name)
for m in rc18:
    print(f"  {m.name:40s}  {m.system_type.value if m.system_type else 'n/a':24s}  {m.entity_type}")
print(f"\nTotal: {len(rc18)} objects")

for schema, table in [(bronze_schema, "raw_3040_doc"), (gold_schema, "posicao_3040")]:
    obj = ExternalLineageObject(table=ExternalLineageTable(name=fq(schema, table)))
    try:
        up   = list(w.external_lineage.list_external_lineage_relationships(obj, LineageDirection.UPSTREAM))
        down = list(w.external_lineage.list_external_lineage_relationships(obj, LineageDirection.DOWNSTREAM))
        print(f"  {fq(schema, table)}: {len(up)} upstream / {len(down)} downstream BYOL edges")
    except Exception as e:
        print(f"  {fq(schema, table)}: {e}")

print("\nBYOL demo seed complete. Open the RC18 app > Linhagem — and edit the topology there.")
