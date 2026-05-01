# RC18 BYOL Lineage Demo Guide

## Overview

This document explains how the **Bring Your Own Lineage (BYOL)** feature is used in the RC18 accelerator to showcase end-to-end data lineage for Brazilian BACEN credit risk reporting (SCR Doc 3040 / Doc 3050).

The demo shows the full pipeline from legacy on-premise systems to official BCB submission — with Databricks Unity Catalog as the single source of truth for both **automatic lineage** (DLT pipelines) and **external lineage** (pre/post-Databricks systems registered via BYOL).

---

## Architecture

```
Oracle Core Banking (4 tables)   ─┐
                                   ├─► Informatica ETL: SCR3040 ─► [BYOL boundary →]
IBM DB2 Mainframe (3 tables)     ─┘                                bronze.raw_3040_doc
                                                                         │
                                   ┌─► Informatica ETL: SCR3050 ─►      │
IBM DB2 Mainframe (historico_scr) ─┘                             bronze.raw_3050_doc
                                                                         │
                                              UC Automatic Lineage (DLT) │
                                                                         ▼
                                                          silver.operacoes_validadas
                                                          silver.scr3040_clientes
                                                          silver.quality_scorecard
                                                                         │
                                                                         ▼
                                                          gold.posicao_mensal_3040
                                                          gold.posicao_3050
                                                                         │
                             [← BYOL boundary] ◄─────────────────────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
         Validador BCB: Doc 3040        Validador BCB: Doc 3050
                     │                             │
                     ▼                             ▼
             STA/CADIP: Doc 3040         STA/CADIP: Doc 3050
               (BCB official)              (BCB official)
```

### Two lineage mechanisms

| Mechanism | Scope | How registered | Query method |
|-----------|-------|---------------|-------------|
| **BYOL (External Lineage API)** | Oracle/DB2 → ETL → Bronze entry; Gold → Validators → STA/CADIP exit | `notebooks/setup/setup_byol_lineage.py` | REST API (`/api/2.0/lineage-tracking/external-lineage`) |
| **UC Automatic Lineage** | Bronze → Silver → Gold (DLT pipelines) | Automatic via DLT + Unity Catalog | `system.access.table_lineage` / `system.access.column_lineage` |

---

## Setup Instructions

### Prerequisites

- Databricks workspace with Unity Catalog enabled
- `CREATE EXTERNAL METADATA` privilege on the metastore
- Bundle deployed (`databricks bundle deploy -t dev ...`)
- Silver and gold pipeline runs completed (data must exist in the UC tables)

### 1. Deploy the bundle

```bash
export DATABRICKS_BUNDLE_ENGINE=direct
databricks bundle deploy -t dev --profile Demo --var catalog=<your_catalog>
```

### 2. Run the setup job (seeds reference + registers BYOL)

```bash
databricks bundle run setup_reference_tables -t dev --profile Demo
```

This runs 3 tasks in order:
1. `setup_reference` — seeds reference schema (BCB domains, criticas, calendar, equivalencia)
2. `load_sample_xmls` — uploads sample Doc 3040/3050 XML files into the landing volume
3. `setup_byol_lineage` — registers 13 external metadata objects + 13 lineage relationships

### 3. Run data pipelines

```bash
databricks bundle run bronze -t dev --profile Demo
databricks bundle run silver -t dev --profile Demo
databricks bundle run gold   -t dev --profile Demo
```

### 4. Open the Lineage view in the app

Navigate to **Linhagem** in the RC18 app. The graph shows the full end-to-end topology with:
- Oracle and DB2 source tables (orange/blue nodes)
- Informatica ETL processes (purple nodes)
- Databricks Bronze/Silver/Gold tables (layer-specific colors)
- BACEN validators and STA/CADIP output (green/red nodes)

---

## What Gets Registered (BYOL)

### External Metadata Objects (13 total)

| Name | System | Type | Description |
|------|--------|------|-------------|
| `rc18_oracle_tb_operacoes_credito` | Oracle | TABLE | Main credit operations — CNPJ, IPOC, vlr_contabil |
| `rc18_oracle_tb_garantias` | Oracle | TABLE | Collateral / guarantees per operation |
| `rc18_oracle_tb_contratantes` | Oracle | TABLE | Counterparty/client master data |
| `rc18_oracle_tb_cessoes_fidc` | Oracle | TABLE | FIDC transfer operations |
| `rc18_db2_clientes_credito` | DB2 | TABLE | Credit client master (mainframe) |
| `rc18_db2_historico_scr` | DB2 | TABLE | Historical SCR submissions |
| `rc18_db2_plano_contas_cosif` | DB2 | TABLE | COSIF chart of accounts |
| `rc18_etl_scr3040_extractor` | Informatica | PROCESS | Extracts/transforms to Doc 3040 XML |
| `rc18_etl_scr3050_aggregator` | Informatica | PROCESS | Aggregates to Doc 3050 TXB/XML |
| `rc18_bacen_validador_scr3040` | BACEN | DATASET | Official BCB Validador3040 tool |
| `rc18_bacen_validador_scr3050` | BACEN | DATASET | Official BCB ValidadorMDR tool |
| `rc18_sta_cadip_doc3040` | BACEN STA | DATASET | Official BCB submission channel (Doc 3040) |
| `rc18_sta_cadip_doc3050` | BACEN STA | DATASET | Official BCB submission channel (Doc 3050) |

### Lineage Relationships (13 total)

| Source | Target | Label | Column mappings |
|--------|--------|-------|----------------|
| Oracle TB_OPERACOES | ETL SCR3040 | CDC extract | CD_CNPJ_IF→cnpj_if, CD_IPOC→ipoc, VLR_CONTABIL→vlr_contabil |
| Oracle TB_GARANTIAS | ETL SCR3040 | JOIN via IPOC | — |
| Oracle TB_CONTRATANTES | ETL SCR3040 | lookup contratante | — |
| Oracle TB_CESSOES_FIDC | ETL SCR3040 | LEFT JOIN cessoes | — |
| DB2 CLIENTES_CREDITO | ETL SCR3040 | DRDA lookup | — |
| DB2 HISTORICO_SCR | ETL SCR3050 | agregacao mensal | — |
| DB2 PLANO_CONTAS_COSIF | ETL SCR3050 | lookup COSIF | — |
| ETL SCR3040 | bronze.raw_3040_doc | XML → Auto Loader | ipoc→header.CD_IPOC, vlr_contabil→operacoes[0].VLR_CONTABIL |
| ETL SCR3050 | bronze.raw_3050_doc | TXB/XML → Auto Loader | — |
| gold.posicao_mensal_3040 | Validador BCB 3040 | export XML | — |
| gold.posicao_3050 | Validador BCB 3050 | export TXB/XML | — |
| Validador BCB 3040 | STA/CADIP Doc 3040 | SFTP transmissao | — |
| Validador BCB 3050 | STA/CADIP Doc 3050 | SFTP transmissao | — |

---

## Customer Demo Script

### Opening narrative

> *"A Resolução Conjunta N.18 exige rastreabilidade de ponta a ponta de todos os dados reportados ao BCB. Isso inclui não apenas as transformações dentro do Databricks, mas também os sistemas legados que alimentam os dados e os canais oficiais de transmissão para o BCB."*
>
> *"Com a funcionalidade Bring Your Own Lineage do Databricks Unity Catalog, conseguimos registrar a linhagem de qualquer sistema externo — Oracle, DB2, Informatica — e visualizá-la junto com a linhagem automática dos pipelines DLT, em um único grafo."*

### Walk-through talking points

**1. Show the graph (Linhagem view)**

- Point out the **7 layers** left to right: Fontes Externas → ETL → Bronze → Silver → Gold → Validadores → BCB STA
- Explain **dashed edges** = BYOL (registered manually via API), **solid animated edges** = UC automatic (DLT captures this natively)
- Highlight that this covers **both sides of the Databricks boundary** — the pre-ingestion legacy world AND the post-processing submission world

**2. Click an Oracle source node**

- Show the connection string (`jdbc:oracle:thin:@core-banking-prod:1521/CREDITO`)
- Explain this is the CDC source — changes captured every 15 minutes via ROWSCN
- *"Este dado vem diretamente do sistema de core banking legado — pré-Databricks"*

**3. Click an ETL edge (Oracle TB_OPERACOES → Informatica SCR3040)**

- Show the column mapping panel: `CD_CNPJ_IF → cnpj_if`, `CD_IPOC → ipoc`, `VLR_CONTABIL_BRL → vlr_contabil`
- *"A linhagem de colunas está registrada — sabemos exatamente de qual campo do Oracle veio cada coluna crítica do SCR"*

**4. Click a Silver table node, then click `ipoc`**

- Show column lineage cascading back through bronze, ETL, all the way to Oracle
- *"Do campo IPOC no Silver, conseguimos rastrear até o CD_IPOC do Oracle Core Banking, passando pelo Informatica — tudo em um único clique"*

**5. Click the gold → Validador edge**

- *"Após o processamento no Databricks, o dado exportado em XML passa pelo Validador oficial do BCB antes da transmissão. Esse processo também está registrado na linhagem"*

**6. Show the output nodes (STA/CADIP)**

- *"A linhagem termina na transmissão oficial ao STA/CADIP do BCB — fechando o ciclo completo exigido pela R.18 para rastreabilidade"*

### RC18 compliance angle

The R.18 regulation (Resolução Conjunta N.18) requires financial institutions to maintain a formal **Data Quality Policy** with 12 quality dimensions, including:

- **Rastreabilidade** (Traceability) — *exactly what BYOL provides*
- **Completude** (Completeness) — validated by DLT Expectations in silver
- **Conformidade** (Conformity) — validated against BCB domains/criticas

The lineage graph is the visual proof of the **Rastreabilidade** dimension for all auditors and BCB regulators.

---

## Implementation Details

### BYOL Notebook (`notebooks/setup/setup_byol_lineage.py`)

- **Idempotent**: deletes all `rc18_*` external metadata objects before recreating
- **Auth**: uses `WorkspaceClient()` (cluster IAM, no token needed)
- **SDK classes**: `ExternalMetadata`, `SystemType`, `CreateRequestExternalLineage`, `ExternalLineageObject`, `ExternalLineageTable`, `ExternalLineageExternalMetadata`, `ColumnRelationship`, `LineageDirection`
- **Widget parameters**: `catalog`, `bronze_schema`, `silver_schema`, `gold_schema`

### Backend (`app/backend/routers/lineage.py`)

In real mode (`USE_MOCK_BACKEND=false`), the `/api/lineage/graph` endpoint:
1. Lists all `rc18_*` external metadata via `w.external_metadata.list_external_metadata()`
2. Queries BYOL relationships for bronze/gold boundary tables (UPSTREAM + DOWNSTREAM)
3. Queries ext-to-ext BYOL edges (sources→ETL, validators→STA/CADIP)
4. Queries `system.access.table_lineage` for UC automatic lineage (Bronze→Silver→Gold)
5. Merges all into a single `LineageGraphResponse`

### Frontend (`app/frontend/src/routes/lineage/+page.svelte`)

- **Layer-based X positioning**: 7 columns at 250px intervals
- **System-type colors**: Oracle=orange, DB2=indigo, Informatica=purple, UC bronze/silver/gold=layer colors, BACEN validator=green, STA/CADIP=red
- **Edge styling**: BYOL=dashed gray, UC automatic=solid Databricks blue (animated)
- **Side panel**: shows connection, frequency, row count, expectations pass rate; edge panel shows column mapping table; column lineage shows full upstream chain including BYOL external sources

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `setup_byol_lineage` fails with `PERMISSION_DENIED` | Missing `CREATE EXTERNAL METADATA` privilege | Grant: `GRANT CREATE EXTERNAL METADATA ON METASTORE TO <user>` |
| Lineage graph shows mock data in deployed app | `USE_MOCK_BACKEND` is `true` | Check `resources/app.yml` env var; redeploy with correct value |
| BYOL relationships not showing in graph | Notebook ran before tables existed | Run bronze+silver+gold pipelines, then re-run `setup_byol_lineage` |
| `rc18_*` objects already exist error | Previous run left stale objects | Notebook is idempotent — it deletes and recreates. If manual cleanup needed: `w.external_metadata.delete_external_metadata(name)` |
