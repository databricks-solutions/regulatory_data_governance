# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Databricks-based accelerator for compliance with **BACEN Resolucao Conjunta N.18** — a Brazilian Central Bank regulation governing credit risk data reporting (SCR). Reference deployment: a major Brazilian financial institution.

## Two audiences, two bundles

The repo is organized around two distinct scenarios, with **physical separation** between them. The two bundles are now disjoint — neither pulls resources from the other:

| Scenario | Who | Bundle | What gets deployed |
|----------|-----|--------|---------------------|
| **Implementation (own-environment adoption)** | Anyone using this as the base for their own RC18 platform | `rc18-starter-kit` (root `databricks.yml`) | App (`USE_MOCK_BACKEND=false`) + catalog (`rc18_catalog`) + serverless 2X-Small warehouse + bronze/silver/gold pipelines + 2 dashboards + setup job (seeds `reference` + uploads `sample/Doc3040*.xml` and `sample/Doc3050*.xml` into the landing volume) + `landing`/`reference` schemas + Auto Loader volumes. Self-contained: deploys end-to-end with `databricks bundle deploy` alone. Customers with an existing catalog/warehouse override `--var catalog=<name> --var warehouse_id=<id>` and comment out `resources/catalog.yml` / `resources/warehouse.yml`. |
| **Demo mode** | Anyone wanting a quick hands-on with the app in mock mode and synthetic XML generation | `rc18-demo` (`demo/databricks.yml`) | App (`USE_MOCK_BACKEND=true`) + 3 jobs only: `r18-synthetic-data-loader`, `rc18-scr3040-generator`, `rc18-scr3050-generator` + dedicated catalog (`rc18_demo_catalog`) + `bronze`/`reference` schemas. **No DLT pipelines, no dashboards, no Genie.** |

Critical invariants:
1. **Nothing in the core bundle (root) references `demo/`** — customer can `rm -rf demo/` at any time without breaking anything.
2. **The demo bundle does NOT include `../resources/*.yml`** — it ships its own `app.yml`, `uc_assets.yml`, generator jobs, and catalog. Core's pipelines/dashboards/setup-job are intentionally NOT deployed by `rc18-demo`.
3. App source code (`app/backend`) is shared by both bundles. The runtime difference is the `apps.config.env` block in each bundle's `app.yml` (`USE_MOCK_BACKEND=false` in core, `=true` in demo).

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
├── sample/                        # Canonical Doc 3040 / Doc 3050 XMLs uploaded by the
│                                  # implementation bundle into ${var.catalog}.landing.scr_xml
│
├── resources/                     # DAB resources of the accelerator (no demo jobs here)
│   ├── app.yml                    # App resource — USE_MOCK_BACKEND=false via apps.config.env
│   ├── catalog.yml                # ${var.catalog} (default rc18_catalog)
│   ├── warehouse.yml              # Serverless 2X-Small warehouse, default for ${var.warehouse_id}
│   ├── setup_job.yml              # 2 tasks: setup_reference + load_sample_xmls
│   ├── uc_assets.yml              # landing/reference schemas + scr_xml/_checkpoints volumes
│   ├── pipelines/{bronze,silver,gold}.yml
│   └── analytics/dashboard_*.yml
│
├── scripts/                       # Dev utilities (not deployed)
├── docs/                          # Specs, BACEN references, regulatory docs
│
└── demo/                          # ⚠️  INTERNAL DATABRICKS USE — independent demo bundle
    ├── README.md                  # Demo runbook (deploy steps + parameters)
    ├── databricks.yml             # Bundle rc18-demo (self-contained — does NOT include ../resources)
    ├── assets/
    │   └── validators/                # BCB official binaries (ZIPs renamed .bin to skip Workspace Files auto-extract — synced by bundle)
    │       ├── SCR3040_Validador.bin  # Validador3040 (SCR Doc 3040)
    │       ├── SCR3050_Validador.bin  # ValidadorMDR (SCR Doc 3050 / TXB V11)
    │       └── Schema_TXB_V11.xsd     # XSD passed to the ValidadorMDR CLI
    ├── notebooks/
    │   ├── scr3040_generator/     # 5-step synthetic Doc 3040 + BACEN validator run
    │   ├── scr3050_generator/     # 5-step synthetic Doc 3050 (validates with BACEN tool)
    │   └── synthetic_data_loader.py
    ├── prompts/                   # Meta-prompts that guided generator authoring
    └── resources/                 # Demo-only DAB resources
        ├── app.yml                # Demo app — USE_MOCK_BACKEND=true (source: ../../app/backend)
        ├── catalog.yml            # rc18_demo_catalog (so demo runs on a fresh workspace)
        ├── uc_assets.yml          # bronze + reference schemas (homes for the 3 demo jobs)
        ├── synthetic_data.yml     # r18-synthetic-data-loader job
        ├── scr3040_generator.yml  # rc18-scr3040-generator job
        └── scr3050_generator.yml  # rc18-scr3050-generator job
```

### Path conventions

**Core bundle** (root `databricks.yml`): relative paths in `resources/**/*.yml` are resolved from each YAML's location:
- `resources/app.yml` → `../app/backend`
- `resources/pipelines/*.yml` → `../../pipelines/...`
- `resources/analytics/dashboard_*.yml` → `../../dashboards/*.lvdash.json`

**Demo bundle** (`demo/databricks.yml`): self-contained — only `include`s `resources/*.yml` from `demo/resources/`. Paths in demo's resource YAMLs:
- `demo/resources/app.yml` → `../../app/backend` (shared app source)
- `demo/resources/scr*_generator.yml` → `../notebooks/...` (one level up to `demo/notebooks/`)
- `demo/resources/synthetic_data.yml` → `../notebooks/synthetic_data_loader.py`

### Invariants to preserve

1. Nothing in root `databricks.yml` or `resources/` references `demo/`. Customer must be able to `rm -rf demo/` safely.
2. Core bundle (`rc18-starter-kit`) never deploys synthetic data or generators.
3. Demo bundle (`rc18-demo`) is self-contained and does NOT include core's pipelines, dashboards, or `setup_reference_tables`. Only the shared `app/backend` source is reused.

## Development Commands

```bash
# Local devloop (backend :8000 + frontend :5173, mock data)
./run_local.sh

# Frontend build → copy into app/backend/frontend_dist (served by FastAPI)
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist

# === Implementation deploy (accelerator — self-contained sandbox) ===
# Default: provisions catalog + serverless warehouse + pipelines + dashboards + setup job + app.
# The app uses `lifecycle.started: true`, so re-running `bundle deploy` on an
# existing app pushes the new code automatically. EXCEPTION: the very first
# deploy after a `bundle destroy` only starts the compute and skips the code
# push — see the "Bundle gotchas" section. Re-run `bundle deploy` (or
# `bundle run r18_compliance_app`) once to recover.
# IMPORTANT: requires the direct deployment engine because the bundle declares a `catalogs:` resource.
export DATABRICKS_BUNDLE_ENGINE=direct
databricks bundle deploy -t dev --profile <p>                                  # creates resources + starts compute
# If app shows UNAVAILABLE after a destroy+deploy, recover with one of:
#   databricks bundle deploy -t dev --profile <p>                              # second run pushes code
#   databricks bundle run r18_compliance_app -t dev --profile <p>              # manual code push
databricks bundle run setup_reference_tables -t dev --profile <p>              # seeds reference + loads sample XMLs into landing
databricks bundle run bronze -t dev --profile <p>                              # ingests sample XMLs
databricks bundle run silver -t dev --profile <p>                              # validate + DLT expectations
databricks bundle run gold -t dev --profile <p>                                # curated tables + governance scorecard

# Bring-your-own catalog / warehouse: override the vars AND comment out the corresponding
# resources/catalog.yml / resources/warehouse.yml so the bundle doesn't manage them.
databricks bundle deploy -t dev --var catalog=my_cat --var warehouse_id=01abc...

# === Internal Databricks demo (mock app + synthetic XML generators) ===
# `lifecycle.started: true` on the app makes re-deploys auto-push the code.
# After a destroy+deploy, the FIRST deploy only starts compute (known issue);
# re-run deploy once OR `bundle run r18_compliance_app` to push code.
cd demo
databricks bundle deploy -t dev-azure                     # rc18-demo: app + 3 jobs + catalog + bronze/reference

# Run synthetic generators / loader:
databricks bundle run scr3040_generator -t dev-azure      # generate Doc 3040 XML (validates with BACEN tool)
databricks bundle run scr3050_generator -t dev-azure      # generate Doc 3050 XML from 3040 via equivalencia
databricks bundle run synthetic_data_loader -t dev-azure  # populate ${var.catalog}.bronze with synthetic SCR rows
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
| `landing` | 0 + volumes | Raw XML inbox (volumes: scr_xml, _checkpoints) — populated externally |
| `bronze` | 2 | Parsed XML docs (raw_3040_doc, raw_3050_doc) |
| `silver` | 8 | Validated (operacoes_validadas, scr3040_clientes/garantias/vencimentos/cont_4966, scr3050_diario/mensal, quarantine) |
| `gold` | 4 | Curated (posicao_mensal_3040, posicao_3050, governance_status_qualidade_mensal, governance_violacoes_log) |
| `reference` | 6 | Domains, criticas rules, BCB calendar, equivalencia 3040↔3050, R.18 dimensions, leiaute versions |
| `quality` | 4 | quality_scorecard, criticas_results, qualidade_dimensoes_mensal, violacoes_log |

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
- **Equivalencia**: Mapping between Doc 3040 and Doc 3050 modalities — exposed as `mod_3050_equiv` in silver for downstream consumers.
- **Criticas**: Validation rules (syntactic + semantic + inter-document) that must pass before submission.
- **Dominios**: Data dictionaries defining valid values for each field.

## Architecture

```
SCR XML files → Bronze (parsed structs) → Silver (validated, R.18 expectations) → Gold (curated)
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

## Bundle gotchas (learned the hard way)

- `catalogs:` resources require **direct deployment engine** — set `DATABRICKS_BUNDLE_ENGINE=direct` before `bundle deploy/run`. Without it, you get "Catalog resources are only supported with direct deployment mode".
- **App env vars cannot be empty** — `apps.config.env` entries with `value: ""` get serialized without a `value` field, which the Apps API rejects with "Must specify environment variable source using either `value` or `valueFrom`." Either provide a non-empty default or omit the env entry entirely (the app code's `os.getenv(..., "")` covers absence).
- **App auto-start during `bundle deploy`** — set `lifecycle.started: true` on the `apps` resource to make `bundle deploy` push the code AND start the app in one shot. Without it, the app stays in "Unavailable" until you run `bundle run <app_key>` separately. Only works in direct deployment mode. The IDE's bundle schema may flag `started` as unknown — that's a stale schema in the IDE; the CLI accepts it (verified via `bundle validate`).
- **`lifecycle.started: true` is unreliable on the FIRST deploy after `bundle destroy`** — the compute starts, but the source-code deployment step is silently skipped (likely a race between compute-creation and the apps-deploy hook in the DABs CLI). Symptoms: `compute_status=ACTIVE`, `app_status=UNAVAILABLE`, `active_deployment=None`. Reproducer: `bundle destroy` → `bundle deploy` → check via `databricks apps get <app-name>`. Workaround on subsequent deploys works fine — the flag triggers code-push every time once an app already exists. Two ways to recover after a destroy+deploy:
  - run `databricks bundle deploy` a SECOND time (the second run pushes code), or
  - run `databricks bundle run r18_compliance_app -t <target>` once to push code manually.
- DLT `@dlt.table(schema=...)` is **column DDL**, not the target schema — every DLT pipeline writes to a SINGLE schema (its `schema:` config). To write to multiple schemas, split into multiple pipelines.
- `dlt.read("name")` only works for tables defined in the **same** pipeline, with an unqualified name. For cross-pipeline reads (e.g., gold reading silver tables), use `spark.table(f"{catalog}.{schema}.{table}")`.
- **Bronze parser choice (3040 vs 3050)** —
  - `raw_3040_doc` uses Auto Loader's **native XML reader** (`cloudFiles.format=xml`, explicit schema, JVM-only). Reshaped to the legacy `header + clientes/operacoes/garantias/vencimentos/cont4966` arrays with Spark `transform`/`flatten`/`filter` so silver doesn't see a contract change. Faster than Python-UDF parsing for production-scale files (10k+ ops).
  - `raw_3050_doc` stays on `binaryFile + lxml` UDF because the TXB V11 taxonomy uses element *names* (`<crdLivre><pesJuridica><pre><capGirPrzAte365 …/>`) as the dimension axis — defining a static native-XML schema would require enumerating every BCB taxonomy node and is brittle for what are tiny files (~1KB).
  - `lxml` is therefore still declared in `resources/pipelines/bronze.yml` under `environment.dependencies` for the 3050 path.
  - When migrating from `binaryFile` to native XML, use a NEW `cloudFiles.schemaLocation` path (e.g. `_checkpoints/bronze_3040_xml_native/`) — Auto Loader's checkpoint state is format-specific and reusing the old path crashes.
- **Setup job table with `DEFAULT` columns** needs `TBLPROPERTIES('delta.feature.allowColumnDefaults' = 'supported')` on Delta. Already wired in `notebooks/setup/setup_reference_tables.py` for `modalidades_equivalencia`.
- Stale `terraform.tfstate` from a previous workspace will fail with `workspace_id mismatch`. Wipe `.databricks/bundle/<target>/` before redeploying to a different workspace.

## Key Decisions & Constraints

- Frontend is **Svelte** (not APX/React) — user preference
- Databricks does NOT own full XML generation — app validates/displays XML, does not produce certified XML
- R.18 covers ALL BCB reporting (50+ documents), not just SCR — scope limited to SCR for MVP
- Mock mode enables local development without Databricks connectivity
- Synthetic data has intentional quality issues (3% nulls, 2% out-of-domain, 5% cross-doc divergences)
- Quality trend improves over 3 months (Jan 82% → Feb 91% → Mar 96%) for compelling demo
