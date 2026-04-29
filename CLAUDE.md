# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Databricks-based accelerator for compliance with **BACEN Resolucao Conjunta N.18** — a Brazilian Central Bank regulation governing credit risk data reporting (SCR). Reference deployment: a major Brazilian financial institution.

## Two audiences, two bundles

The repo is organized around two distinct scenarios, with **physical separation** between them:

| Scenario | Who | Bundle | What gets deployed |
|----------|-----|--------|---------------------|
| **Own-environment adoption** | Anyone using this as the base for their own RC18 platform | `rc18-starter-kit` (root `databricks.yml`) | App + pipelines + dashboards + genie. **No synthetic data, no generators.** |
| **Demo mode** | Anyone wanting to see the accelerator in action with synthetic data | `rc18-demo` (`demo/databricks.yml`) | Everything from core + synthetic generators (3040/3050) + fake data loader |

Critical invariant: **nothing in the core bundle (root) references `demo/`**. The customer can `rm -rf demo/` at any time without breaking anything. When editing, preserve this invariant.

## Tech Stack

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | SvelteKit 5, Svelte Flow, LayerCake, d3 | `app/frontend/` |
| Backend | FastAPI, Pydantic v2, databricks-sdk | `app/backend/` |
| Pipelines | DLT/SDP with Expectations | `pipelines/` |
| Dashboards | Lakeview (AI/BI) JSON definitions | `dashboards/` |
| Deployment | Databricks Asset Bundles (DABs) | `databricks.yml`, `resources/` |
| Data | Unity Catalog, catalog `rc18_catalog` | Workspace `latam-ssa` |

## Project Structure

Top-level folders are each an independent deliverable. The root is the **accelerator** (customer base); `demo/` is an isolated overlay for internal Databricks demos.

```
regulatory-data-governance/
├── databricks.yml                 # Bundle rc18-starter-kit (accelerator — customer uses)
├── README.md
├── CLAUDE.md                      # This file
├── run_local.sh                   # Local devloop (backend + frontend)
│
├── app/                           # Databricks App
│   ├── backend/                   # FastAPI (main.py, routers/, models.py, frontend_dist/, ...)
│   └── frontend/                  # SvelteKit 5 source
│
├── pipelines/                     # DLT skeletons (bronze/silver/gold) for CADOC 3040/3050
│   ├── bronze/transformations/
│   ├── silver/transformations/
│   └── gold/transformations/
│
├── notebooks/                     # Accelerator utility notebooks
│   └── setup/
│       └── setup_reference_tables.py   # Loads BACEN domains/criticas/calendar (NOT synthetic)
│
├── dashboards/                    # Lakeview JSON definitions (3)
│
├── resources/                     # DAB resources of the accelerator (no demo jobs here)
│   ├── app.yml
│   ├── pipelines/{bronze,silver,gold}.yml
│   └── analytics/{dashboard_*,genie_scr}.yml
│
├── scripts/                       # Dev utilities (not deployed)
├── docs/                          # Specs, BACEN references, regulatory docs
│
└── demo/                          # ⚠️  INTERNAL DATABRICKS USE — synthetic data overlay
    ├── README.md                  # Demo runbook
    ├── databricks.yml             # Bundle rc18-demo (includes core + demo resources)
    ├── assets/
    │   └── validators/
    │       └── SCR3040_Validador.bin  # BCB official validator (a ZIP renamed to .bin to skip Workspace Files auto-extract — synced by bundle)
    ├── notebooks/
    │   ├── scr3040_generator/     # 5-step synthetic Doc 3040 + BACEN validator run
    │   ├── scr3050_generator/     # 5-step synthetic Doc 3050 (validates with BACEN tool)
    │   └── synthetic_data_loader.py
    ├── prompts/                   # Meta-prompts that guided generator authoring
    └── resources/                 # Jobs exclusive to the demo (NOT in core)
        ├── scr3040_generator.yml
        ├── scr3050_generator.yml
        ├── synthetic_data.yml
        └── scheduled_refresh.yml
```

### Path conventions

**Core bundle** (root `databricks.yml`): relative paths in `resources/**/*.yml` are resolved from each YAML's location:
- `resources/app.yml` → `../app/backend`
- `resources/pipelines/*.yml` → `../../pipelines/...`
- `resources/analytics/dashboard_*.yml` → `../../dashboards/*.lvdash.json`

**Demo bundle** (`demo/databricks.yml`): uses `sync.paths: [..]` + `include` from both `../resources/` (core) and `resources/` (demo-local). Paths in demo's own resource YAMLs are relative to `demo/resources/`:
- `demo/resources/*.yml` → `../notebooks/...` (one level up to `demo/notebooks/`)

### Invariants to preserve

1. Nothing in root `databricks.yml` or `resources/` references `demo/`. Customer must be able to `rm -rf demo/` safely.
2. Core bundle (`rc18-starter-kit`) never deploys synthetic data or generators.
3. Demo bundle (`rc18-demo`) always bundles the core + its overlay (both get deployed together).

## Development Commands

```bash
# Local devloop (backend :8000 + frontend :5173, mock data)
./run_local.sh

# Frontend build → copy into app/backend/frontend_dist (served by FastAPI)
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist

# === Accelerator deploy (what the customer runs) ===
databricks bundle deploy -t dev                # rc18-starter-kit: app + pipelines + dashboards + genie

# === Internal Databricks demo (with synthetic data) ===
cd demo
databricks bundle deploy -t dev                # rc18-demo: accelerator + synthetic generators + loader
databricks bundle run scr3040_generator -t dev # generate Doc 3040 XML
databricks bundle run scr3050_generator -t dev # generate Doc 3050 XML from 3040 via equivalence
databricks bundle run synthetic_data_loader -t dev
```

## Databricks Assets

Asset IDs (workspace, warehouse, dashboards, Genie space) are not committed.
Configure them via `.env` for local dev or `app.yaml` env vars for the deployed
Databricks App. See [.env.example](.env.example) for the full list of variables.

| Asset | Env var |
|-------|---------|
| Catalog | `DATABRICKS_CATALOG` (default `rc18_catalog`) |
| SQL warehouse | `DATABRICKS_WAREHOUSE_ID` |
| Dashboard: Conformidade R.18 | `DASHBOARD_ID_CONFORMIDADE` |
| Dashboard: Monitor Críticas | `DASHBOARD_ID_CRITICAS` |
| Dashboard: Reconciliação | `DASHBOARD_ID_RECONCILIACAO` |
| Genie Room: SCR R.18 | `GENIE_SPACE_ID` |

### Data Schemas (catalog: rc18_catalog)

| Schema | Tables | Purpose |
|--------|--------|---------|
| `bronze` | 7 | Raw ingestion (operacoes_raw, clientes_raw, raw_3050_*, raw_cosif_saldos) |
| `silver` | 8 | Validated (operacoes_validadas, scr3050_diario/mensal, quarantine) |
| `gold` | 6 | Reconciled (posicao_mensal_3040, reconciliacao_*, governance_*) |
| `reference` | 7 | Domains, criticas rules, BCB calendar, equivalencia, R.18 dimensions |
| `quality` | 5 | Scorecard, criticas_results, reconciliation_results, submissao_historico |

## Key Links

### BCB Reference Pages
- SCR Doc 3040: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040
- SCR Doc 3050: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3050
- External Lineage (BYOL): https://docs.databricks.com/aws/en/data-governance/unity-catalog/external-lineage

### Google Docs
See [docs/gdocs_notes.md](docs/gdocs_notes.md) for meeting notes and project context links.

## Domain Context

- **R.18**: Joint resolution mandating a formal Data Quality Policy covering ALL information reported to BCB. 12 mandatory quality dimensions, board-level governance, semi-annual reports, 5-year retention. Deadline: 31/12/2026.
- **SCR 3040**: Detailed credit operation data — individual operations with 130+ fields, IPOC identification, cessao/FIDC complexity. Submitted as XML, validated before sending to BCB.
- **SCR 3050**: Aggregated credit data in TXB/XML format. Versioned layouts (current: V11). Weekly/monthly periodicity with BCB business day calendar.
- **Equivalencia**: Mapping between Doc 3040 and Doc 3050 modalities — critical for reconciliation.
- **Criticas**: Validation rules (syntactic + semantic + inter-document) that must pass before submission.
- **Dominios**: Data dictionaries defining valid values for each field.

## Architecture

```
Sources (Oracle/DB2/VSAM) → Bronze (raw) → Silver (validated, R.18 expectations) → Gold (reconciled)
                                                                                      ↓
                                                                              Lakeview Dashboards
                                                                              Genie Room (NL→SQL)
                                                                              Svelte App (FastAPI)
```

- **Frontend**: SvelteKit 5 SPA with custom theme, Svelte Flow lineage DAG, LayerCake charts
- **Backend**: FastAPI with mock mode (USE_MOCK_BACKEND=true) and real Databricks SQL mode
- **Pipelines**: DLT with Expectations mapped to 12 R.18 quality dimensions
- **Lineage**: UC system tables + External Lineage API (BYOL) for external systems

## Conventions

- **UI text**: Portuguese-BR (BCB/SCR standard terminology)
- **Code**: English (variables, functions, comments)
- **API fields**: English names, Portuguese-BR display values
- **Specs before code**: Always check docs/spec/ before implementing new features
- **Data model source of truth**: docs/spec/03_data_model.md (v1.1 canonical names in Appendix C)

## Key Decisions & Constraints

- Frontend is **Svelte** (not APX/React) — user preference
- Databricks does NOT own full XML generation — app validates/displays XML, does not produce certified XML
- R.18 covers ALL BCB reporting (50+ documents), not just SCR — scope limited to SCR for MVP
- Mock mode enables local development without Databricks connectivity
- Synthetic data has intentional quality issues (3% nulls, 2% out-of-domain, 5% cross-doc divergences)
- Quality trend improves over 3 months (Jan 82% → Feb 91% → Mar 96%) for compelling demo
