# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Databricks-based accelerator for compliance with **BACEN Resolucao Conjunta N.18** — a Brazilian Central Bank regulation governing credit risk data reporting (SCR). Reference deployment: a major Brazilian financial institution.

## Two audiences, two bundles

The repo is organized around two distinct scenarios, with **physical separation** between them. The two bundles are now disjoint — neither pulls resources from the other:

| Scenario | Who | Bundle | What gets deployed |
|----------|-----|--------|---------------------|
| **Implementation (own-environment adoption)** | Anyone using this as the base for their own RC18 platform | `rc18-starter-kit` (root `databricks.yml`) | App (`USE_MOCK_BACKEND=false`) + catalog (`rc18_catalog`) + serverless 2X-Small warehouse + bronze/silver/gold pipelines + 2 dashboards + setup job (seeds `reference` + uploads `sample/Doc3040*.xml` and `sample/Doc3050*.xml` into the landing volume) + `landing`/`reference` schemas + Auto Loader volumes. DQX Studio is a mandatory external prerequisite and is not provisioned by this bundle. Apart from DQX, the bundle provisions its own dependencies. Customers with an existing catalog/warehouse set `catalog` / `warehouse_id` in `target.yml` and comment out `resources/catalog.yml` / `resources/warehouse.yml`. |
| **Demo mode** | Anyone wanting a quick hands-on with the app in mock mode and synthetic XML generation | `rc18-demo` (`demo/databricks.yml`) | App (`USE_MOCK_BACKEND=true`) + 3 jobs only: `r18-synthetic-data-loader`, `rc18-scr3040-generator`, `rc18-scr3050-generator` + dedicated catalog (`rc18_demo_catalog`) + `bronze`/`reference` schemas. **No DLT pipelines, no dashboards, no Genie.** |

Critical invariants:
1. **Nothing in the core bundle (root) references `demo/`** — customer can `rm -rf demo/` at any time without breaking anything.
2. **The demo bundle does NOT include `../resources/*.yml`** — it ships its own `app.yml`, `uc_assets.yml`, generator jobs, and catalog. Core's pipelines/dashboards/setup-job are intentionally NOT deployed by `rc18-demo`.
3. App source code (`app/backend`) is shared by both bundles. The runtime difference is the `apps.config.env` block in each bundle's `app.yml` (`USE_MOCK_BACKEND=false` in core, `=true` in demo).

## Two pipeline modes (core bundle only)

The core bundle orchestrates the bronze→silver→gold medallion in one of two **mutually exclusive** modes. Both produce the identical tables/schemas and the same downstream contract; they differ only in HOW the transforms run:

| Mode | `pipeline_mode` | What runs | Resources deployed | Who |
|------|-----------------|-----------|--------------------|-----|
| **Classical** (DEFAULT) | `classical` | Databricks **jobs** running PySpark notebooks under `pipelines/classical/**` (Auto Loader batch `trigger(availableNow=True)` for bronze; `spark.table` + `saveAsTable(overwrite)` for silver/gold) | `resources/classical/*.yml` → jobs `bronze`/`silver`/`gold` + `rc18_end_to_end`. **Zero SDP/DLT resources.** | Customers who cannot / do not want to use SDP/DLT |
| **SDP/DLT** | `sdp` | Declarative DLT/SDP pipelines (original path) with `@dlt.table` notebooks under `pipelines/{bronze,silver,gold}/` | `resources/pipelines/*.yml` → pipelines `bronze`/`silver`/`gold` + `rc18_end_to_end` | Customers who want the declarative Lakeflow path |

How the switch works (and why it's structural, not purely a variable):
- **DABs cannot conditionally drop a resource based on a variable value** (variables only do string interpolation). So the *effective* switch is the `include:` block in `databricks.yml`: exactly one of `resources/classical/*.yml` / `resources/pipelines/*.yml` is active (uncommented). This is the same idiom already used for BYOC (comment out `resources/catalog.yml` / `warehouse.yml`).
- `var.pipeline_mode` (default `classical`) documents/telemetrizes the choice. Set `pipeline_mode: sdp` in `target.yml` AND flip the two include lines to switch. Never leave both include lines active — the shared resource keys (`bronze`/`silver`/`gold`/`rc18_end_to_end`) collide and `bundle validate` errors, which by design forces exactly one mode.
- **Both modes reuse the same resource keys**, so every documented command (`databricks bundle run rc18_end_to_end`, `... run bronze|silver|gold`) works unchanged regardless of mode.
- The DLT orchestration job lives at `resources/pipelines/orchestration_job.yml` (moved out of the always-included `resources/*.yml` because it references `${resources.pipelines.*.id}`, which only exist in SDP mode). The classical equivalent is `resources/classical/orchestration_job.yml`.

Invariant: a classical-only deploy must provision **no `pipelines:` resource at all** — verify with `databricks bundle validate -o json | jq '.resources.pipelines'` → should be null/absent in classical mode.

## Tech Stack

| Layer | Technology | Location |
|-------|-----------|----------|
| Frontend | SvelteKit 5, Svelte Flow, LayerCake, d3 | `app/frontend/` |
| Backend | FastAPI, Pydantic v2, databricks-sdk | `app/backend/` |
| Pipelines | Classical jobs (default, `pipelines/classical/`) OR DLT/SDP (`pipelines/`) — pure ELT bronze→silver→gold | `pipelines/` |
| Quality (rule authoring + execution) | DQX Studio (external Databricks App, embedded via iframe) | env var `DQX_STUDIO_URL` → `/rules` page |
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
├── pipelines/                     # Transform code for CADOC 3040/3050 (two modes)
│   ├── bronze/transformations/    # SDP/DLT mode: @dlt.table notebooks
│   ├── silver/transformations/    #   Pure ELT — no quality logic (lives in DQX Studio)
│   ├── gold/transformations/
│   └── classical/                 # CLASSICAL mode (default): plain PySpark notebooks,
│       ├── bronze/                #   no `import dlt`. Same tables/contract as the DLT path.
│       ├── silver/                #   Bronze = Auto Loader batch; silver/gold = saveAsTable.
│       └── gold/
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
│   ├── setup_job.yml              # 3 tasks: setup_reference + load_sample_xmls + setup_byol_lineage
│   ├── uc_assets.yml              # landing/reference schemas + scr_xml/_checkpoints volumes
│   ├── classical/                 # CLASSICAL mode (default, included): jobs bronze/silver/gold
│   │                              #   + orchestration_job.yml (rc18_end_to_end). No SDP resources.
│   ├── pipelines/                 # SDP/DLT mode (opt-in, commented in include):
│   │                              #   {bronze,silver,gold}.yml + orchestration_job.yml
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
- `resources/pipelines/*.yml` → `../../pipelines/...` (SDP mode, incl. `orchestration_job.yml` → `../../notebooks/setup/...`)
- `resources/classical/*.yml` → `../../pipelines/classical/...` and `../../notebooks/setup/...` (classical mode, default)
- `resources/analytics/dashboard_*.yml` → `../../dashboards/*.lvdash.json`

Note: `databricks.yml`'s `include:` no longer uses the broad `resources/**/*.yml` glob. It lists `resources/*.yml` + `resources/analytics/*.yml` (always on) plus exactly one of `resources/classical/*.yml` (default) / `resources/pipelines/*.yml` (opt-in). See "Two pipeline modes".

**Demo bundle** (`demo/databricks.yml`): self-contained — only `include`s `resources/*.yml` from `demo/resources/`. Paths in demo's resource YAMLs:
- `demo/resources/app.yml` → `../../app/backend` (shared app source)
- `demo/resources/scr*_generator.yml` → `../notebooks/...` (one level up to `demo/notebooks/`)
- `demo/resources/synthetic_data.yml` → `../notebooks/synthetic_data_loader.py`

### Invariants to preserve

1. Nothing in root `databricks.yml` or `resources/` references `demo/`. Customer must be able to `rm -rf demo/` safely.
2. Core bundle (`rc18-starter-kit`) never deploys synthetic data or generators.
3. Demo bundle (`rc18-demo`) is self-contained and does NOT include core's pipelines, dashboards, or `setup_reference_tables`. Only the shared `app/backend` source is reused.
4. Exactly ONE pipeline mode is active at a time (classical default vs SDP opt-in), toggled by the `include:` block. Classical mode must deploy ZERO `pipelines:` resources. The classical PySpark notebooks (`pipelines/classical/**`) and DLT notebooks (`pipelines/{bronze,silver,gold}/`) must stay output-equivalent — same tables, columns, and downstream contract. See "Two pipeline modes".

## Development Commands

```bash
# Local devloop (backend :8000 + frontend :5173, mock data)
./run_local.sh

# Frontend build → copy into app/backend/frontend_dist (served by FastAPI)
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist

# === Implementation deploy (accelerator — self-contained sandbox) ===
# Default: provisions catalog + serverless warehouse + CLASSICAL pipeline jobs
# (no SDP/DLT) + dashboards + setup job + app. Switch to SDP mode below.
# The app uses `lifecycle.started: true`, so re-running `bundle deploy` on an
# existing app pushes the new code automatically. EXCEPTION: the very first
# deploy after a `bundle destroy` only starts the compute and skips the code
# push — see the "Bundle gotchas" section. Re-run `bundle deploy` (or
# `bundle run r18_compliance_app`) once to recover.
# Copy target.yml.example to target.yml and set the CLI profile and REQUIRED
# DQX Studio URL. The single target is fixed as `dev`; cloud/workspace selection
# belongs to the profile. The direct deployment engine required by `catalogs:`
# is pinned in databricks.yml (`bundle.engine: direct`), so plain
# `databricks bundle ...` works with no wrapper or env var.
databricks bundle deploy                                                             # creates resources + starts compute
# If app shows UNAVAILABLE after a destroy+deploy, recover with one of:
#   databricks bundle deploy                                                         # second run pushes code
#   databricks bundle run r18_compliance_app                                         # manual code push
databricks bundle run setup_reference_tables                                         # seeds reference + loads sample XMLs into landing
databricks bundle run bronze                                                         # ingests sample XMLs
databricks bundle run silver                                                         # bronze→silver ELT
databricks bundle run gold                                                           # curated position tables
databricks bundle run rc18_end_to_end                                                # (alt) whole stack chained in one job
# NOTE: these run commands are IDENTICAL in classical (default) and SDP mode —
# both modes reuse the same resource keys (bronze/silver/gold/rc18_end_to_end).

# === Switch pipeline mode: classical (default) → SDP/DLT ===
# 1. In target.yml set `pipeline_mode: sdp` (documentation/telemetry).
# 2. In databricks.yml `include:`, comment `resources/classical/*.yml` and
#    uncomment `resources/pipelines/*.yml`. Never leave both active (shared
#    resource keys collide → bundle validate errors by design).
# 3. Verify the swap: classical mode → no pipelines; sdp mode → no classical jobs.
databricks bundle validate -o json | jq '.resources.pipelines // "none (classical)"'
databricks bundle deploy

# Bring-your-own catalog / warehouse: set catalog and warehouse_id under the
# target's variables in target.yml AND comment out the corresponding
# resources/catalog.yml / resources/warehouse.yml so the bundle doesn't manage them.
databricks bundle deploy

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

For LOCAL dev, asset IDs are configured via `.env` (see [.env.example](.env.example)).
On DEPLOY, the bundle provisions the assets and injects their IDs into the app via
`resources/app.yml` `apps.config.env` — dashboards resolve via
`${resources.dashboards.*.id}`. The Genie Space is a separate opt-in bundle
(`genie/`) — its ID reaches the app via `var.genie_space_id` set in the core
`target.yml` (default `__unset__` = Genie disabled). The env vars below are the
local-dev overrides.

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
| `silver` | 6 | Normalized SCR tables (pure ELT, no quality columns) — naming pattern `scr<CADOC>_<entidade>`: `scr3040_operacoes`, `scr3040_clientes`, `scr3040_garantias`, `scr3040_vencimentos`, `scr3040_cont_4966` + unified `scr3050`. Written by the silver DLT pipeline (DLT writes to a single schema). |
| `gold` | 3 | Curated (`posicao_3040`, `posicao_3050`) + `processing_state` (1-row: `current_data_base`/`data_base_month`/`updated_at` = último CADOC processado, MAX dt_base; alimenta o seletor de Data-Base do app via `GET /dashboard/data-bases`) |
| `reference` | 6 | Domains, criticas rules, BCB calendar, equivalencia 3040↔3050, R.18 dimensions, leiaute versions |

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
SCR XML files → Bronze (parsed structs) → Silver (normalized) → Gold (curated)
                                                                       ↓
                                                               Lakeview Dashboards
                                                               Genie Room (NL→SQL)
                                                               Svelte App (FastAPI)
```

- **Frontend**: SvelteKit 5 SPA with custom theme, Svelte Flow lineage DAG, LayerCake charts
- **Backend**: FastAPI with mock mode (USE_MOCK_BACKEND=true) and real Databricks SQL mode
- **Pipelines**: pure ELT bronze→silver→gold in one of two modes — **classical** Databricks jobs + PySpark notebooks (default, `pipelines/classical/`) or **DLT/SDP** declarative pipelines (`pipelines/`). Both are output-equivalent; no quality logic embedded in either. Quality (rule authoring + execution) is delegated to the mandatory **DQX Studio** prerequisite (external Databricks App from Databricks Labs DQX), embedded via iframe on `/rules` using the required `dqx_studio_url` target variable.
- **Lineage**: UC system tables + External Lineage API (BYOL) for external systems

## Conventions

- **UI text**: Portuguese-BR (BCB/SCR standard terminology)
- **Code**: English (variables, functions, comments)
- **API fields**: English names, Portuguese-BR display values
- **Specs before code**: Always check docs/spec/ before implementing new features
- **Data model source of truth**: docs/spec/03_data_model.md (v1.1 canonical names in Appendix C)

## Bundle gotchas (learned the hard way)

- `catalogs:` resources require **direct deployment engine**. This is pinned in `databricks.yml` as `bundle.engine: direct` (also in `genie/databricks.yml`), which takes priority over the `DATABRICKS_BUNDLE_ENGINE` env var and makes plain `databricks bundle ...` work without any wrapper. Without it (engine defaults to `terraform`) the CLI fails with "Catalog resources are only supported with direct deployment mode". The `--plan` flag on `bundle deploy` is direct-engine-only.
- **App env vars cannot be empty** — `apps.config.env` entries with `value: ""` get serialized without a `value` field, which the Apps API rejects with "Must specify environment variable source using either `value` or `valueFrom`." Either provide a non-empty default or omit the env entry entirely (the app code's `os.getenv(..., "")` covers absence).
- **App auto-start during `bundle deploy`** — set `lifecycle.started: true` on the `apps` resource to make `bundle deploy` push the code AND start the app in one shot. Without it, the app stays in "Unavailable" until you run `bundle run <app_key>` separately. Only works in direct deployment mode. The IDE's bundle schema may flag `started` as unknown — that's a stale schema in the IDE; the CLI accepts it (verified via `bundle validate`).
- **`lifecycle.started: true` is unreliable on the FIRST deploy after `bundle destroy`** — the compute starts, but the source-code deployment step is silently skipped (likely a race between compute-creation and the apps-deploy hook in the DABs CLI). Symptoms: `compute_status=ACTIVE`, `app_status=UNAVAILABLE`, `active_deployment=None`. Reproducer: `bundle destroy` → `bundle deploy` → check via `databricks apps get <app-name>`. Workaround on subsequent deploys works fine — the flag triggers code-push every time once an app already exists. Two ways to recover after a destroy+deploy:
  - run `databricks bundle deploy` a SECOND time (the second run pushes code), or
  - run `databricks bundle run r18_compliance_app -t <target>` once to push code manually.
- **Genie lives in a SEPARATE opt-in bundle (`genie/`), not the core.** `POST /api/2.0/genie/spaces` validates at creation time that every attached table exists. On a clean core `bundle deploy` the catalog/schemas exist but the tables (`gold.posicao_*`, `reference.*`, `governance.incidents`) are empty until `rc18_end_to_end` runs — AFTER the deploy. Provisioning Genie inside the core failed with `403 PERMISSION_DENIED "Catalog '...' does not exist"` and, because the app env referenced the space, cascaded into blocking the app + permissions + job. So the Genie Space is its own bundle `genie/` (`bundle: rc18-genie`) deployed only after the core + `rc18_end_to_end`. Verified empirically: a space with `tables: []` creates fine; adding a missing table triggers the 403. `databricks genie create-space` exists in CLI v1.8.0+ but the Python SDK (`w.genie.*`) only exposes conversation methods, not space creation.
- **Cross-bundle wiring of the Genie ID goes through `var.genie_space_id`, and its default is the `__unset__` sentinel (NOT empty string).** Bundles don't share `${resources...}` references, so the `genie/` bundle creates the space and the operator copies its ID into the CORE `target.yml` (`genie_space_id: <id>`) + redeploys the core; `app.yml` injects `GENIE_SPACE_ID: ${var.genie_space_id}`. The default MUST be a non-empty sentinel (`__unset__`) because an empty-string env serializes without a `value` and the Apps API rejects it (see the empty-env gotcha above) — this would break the normal (Genie-less) deploy. The backend's `genie_space_id()` in `db.py` normalizes `__unset__`/`""` → `""` so the frontend shows the "disponível após deploy" placeholder. `databricks apps update` has NO `--env` flag (the app.yaml comment claiming otherwise is stale); the app's env comes entirely from the core bundle's `apps.config.env`.
- **Genie Space `serialized_space` must be INLINE, not `file_path`, for `${var.catalog}` to interpolate** — the `genie_spaces` resource accepts the definition as `file_path: <x>.geniespace.json` OR inline under `serialized_space:`. DABs treats a `file_path` JSON as **opaque** (no variable substitution — same as `.lvdash.json` dashboards), so `${var.catalog}` stays literal and BYOC customers get tables pointing at a nonexistent catalog. Inlining as native YAML under `serialized_space:` DOES interpolate `${var.catalog}`/`${var.warehouse_id}`. `genie/resources/genie_space.yml` uses the inline form on purpose. After `databricks bundle generate genie-space --resource rc18_genie --force`, convert the regenerated `file_path` back to inline `serialized_space` and re-replace `rc18_catalog` → `${var.catalog}` in the table identifiers. Never hardcode the space ID (it changes on every recreation).
- **Approved domains for iframe embedding** — the app embeds Lakeview dashboards (`/dashboards`) and Genie (`/genie`) via `iframe`. Databricks blocks these iframes (blank page / `X-Frame-Options` refusal) until the **deployed app's own domain** is added to the workspace allowlist at **Settings → Security → Approved domains**. This is a manual, admin-only, once-per-workspace step done AFTER deploy (not expressible in the bundle). Get the host via `databricks apps get r18_compliance_app | grep url` (e.g. `rc18-starter-kit-dev-<workspace-id>.<region>.databricksapps.com`). The rest of the app works without it — only dashboard/Genie embeds are affected. The DQX Studio embed at `/rules` is a separate Databricks App; if it also renders blank, add its domain to the same allowlist. Documented in README "Aprovar o domínio do app".
- **Classical vs SDP pipeline mode is a structural `include:` toggle, not a runtime variable.** DABs cannot conditionally drop a resource by variable value, so "deploy zero SDP resources" can ONLY be achieved by NOT including the SDP YAMLs. `databricks.yml` includes exactly one of `resources/classical/*.yml` (default) / `resources/pipelines/*.yml`; `var.pipeline_mode` (`classical`|`sdp`) only documents the choice. Both sets reuse the same resource keys (`bronze`/`silver`/`gold`/`rc18_end_to_end`) on purpose — run commands stay identical AND leaving both includes active is a hard validate error that prevents an ambiguous deploy. Classical notebooks live in `pipelines/classical/**` (no `import dlt`); they must stay output-equivalent to the DLT notebooks — if you change a transform in one, change the other.
- **Classical bronze uses a DISTINCT Auto Loader checkpoint/schema path** (`_checkpoints/classical_bronze_3040_*` / `classical_bronze_3050_*`) from the DLT pipeline's paths. Auto Loader state is format- and pipeline-specific; sharing a path across modes corrupts state. Switching modes on an already-populated landing volume re-ingests from the classical checkpoints (independent of the DLT ones).
- DLT `@dlt.table(schema=...)` is **column DDL**, not the target schema — every DLT pipeline writes to a SINGLE schema (its `schema:` config). To write to multiple schemas, split into multiple pipelines. (Classical mode has no such limit — a single job task writes wherever `saveAsTable` points, which is why classical silver/gold each cover multiple tables in one notebook.)
- `dlt.read("name")` only works for tables defined in the **same** pipeline, with an unqualified name. For cross-pipeline reads (e.g., gold reading silver tables), use `spark.table(f"{catalog}.{schema}.{table}")`. The classical notebooks use `spark.table` everywhere (no `dlt.read`); the gold `processing_state` same-pipeline dependency becomes a sequential `spark.table` read of the just-written positions.
- **Bronze parser choice (3040 vs 3050)** —
  - `raw_3040_doc` uses Auto Loader's **native XML reader** (`cloudFiles.format=xml`, explicit schema, JVM-only). Reshaped to the legacy `header + clientes/operacoes/garantias/vencimentos/cont4966` arrays with Spark `transform`/`flatten`/`filter` so silver doesn't see a contract change. Faster than Python-UDF parsing for production-scale files (10k+ ops).
  - `raw_3050_doc` stays on `binaryFile + lxml` UDF because the TXB V11 taxonomy uses element *names* (`<crdLivre><pesJuridica><pre><capGirPrzAte365 …/>`) as the dimension axis — defining a static native-XML schema would require enumerating every BCB taxonomy node and is brittle for what are tiny files (~1KB).
  - `lxml` is therefore declared under `environment.dependencies` for the 3050 path in BOTH modes — `resources/pipelines/bronze.yml` (SDP) and `resources/classical/bronze.yml` + `resources/classical/orchestration_job.yml` (classical `serverless_env`).
  - When migrating from `binaryFile` to native XML, use a NEW `cloudFiles.schemaLocation` path (e.g. `_checkpoints/bronze_3040_xml_native/`) — Auto Loader's checkpoint state is format-specific and reusing the old path crashes.
- **Setup job table with `DEFAULT` columns** needs `TBLPROPERTIES('delta.feature.allowColumnDefaults' = 'supported')` on Delta. Already wired in `notebooks/setup/setup_reference_tables.py` for `modalidades_equivalencia`.
- Stale `terraform.tfstate` from a previous workspace will fail with `workspace_id mismatch`. Destroy the target against its original workspace first; only then wipe `.databricks/bundle/<target>/` before redeploying that target elsewhere.
- **Direct-engine state is target-scoped, not profile-scoped** — this repository has one default target fixed as `dev`. Before changing `workspace.profile` in `target.yml`, destroy the existing deployment against the original workspace; otherwise resources can be orphaned.
- **Workspace-local target configuration** — root `databricks.yml` includes the git-ignored `target.yml`. Copy `target.yml.example`, then fill the CLI profile and required DQX Studio URL. Azure/AWS/GCP selection belongs to the profile, never to the target name. The direct engine is set via `bundle.engine: direct` in `databricks.yml` (no wrapper); `.env` is exclusively for local app development.

## Key Decisions & Constraints

- Frontend is **Svelte** (not APX/React) — user preference
- Databricks does NOT own full XML generation — app validates/displays XML, does not produce certified XML
- R.18 covers ALL BCB reporting (50+ documents), not just SCR — scope limited to SCR for MVP
- Mock mode enables local development without Databricks connectivity
- Synthetic data has intentional quality issues (3% nulls, 2% out-of-domain, 5% cross-doc divergences)
- Quality trend improves over 3 months (Jan 82% → Feb 91% → Mar 96%) for compelling demo
- **DQX Studio is a mandatory prerequisite for quality rule authoring and execution.** It is an external Databricks App from Databricks Labs DQX (https://databrickslabs.github.io/dqx/docs/guide/dqx_studio/) and is not provisioned by this bundle. The target must provide `dqx_studio_url`; the RC18 app embeds it at `/rules`. Pipelines silver/gold remain pure ELT — no embedded DQX dependency, no `_errors`/`_warnings` columns, no `quality.dqx_checks` table.
