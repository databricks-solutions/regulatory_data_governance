# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Databricks-based accelerator for compliance with **BACEN Resolucao Conjunta N.18** — a Brazilian Central Bank regulation governing credit risk data reporting (SCR).

## Two audiences, two bundles

The repo is organized around two distinct scenarios, with **physical separation** between them. The two bundles are now disjoint — neither pulls resources from the other:

| Scenario | Who | Bundle | What gets deployed |
|----------|-----|--------|---------------------|
| **Implementation (own-environment adoption)** | Anyone using this as the base for their own RC18 platform | `rc18-starter-kit` (root `databricks.yml`) | App (`USE_MOCK_BACKEND=false`) + catalog (`rc18_catalog`) + serverless 2X-Small warehouse + bronze/silver/gold pipelines + 2 dashboards + setup job (seeds `reference` + uploads the `sample/` CADOC files — `Doc3040*.xml`, `Doc3050*.xml`, `Doc4010*.xml`, `Doc4016*.xml`, `Doc2011*.xml`, `Doc4060*.xml` — into the landing volume) + `landing`/`reference` schemas + Auto Loader volumes. DQX Studio is a mandatory external prerequisite and is not provisioned by this bundle. Apart from DQX, the bundle provisions its own dependencies. Customers with an existing catalog/warehouse set `catalog` / `warehouse_id` in `target.yml` and comment out `resources/catalog.yml` / `resources/warehouse.yml`. |
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
| Data | Unity Catalog, catalog `rc18_catalog` | Workspace: defined by the CLI profile in `target.yml` |

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
│   │                              #   raw_3040 · raw_3050 · raw_4010 · raw_4016 · raw_2011 · raw_4060
│   ├── silver/transformations/    #   Pure ELT — no quality logic (lives in DQX Studio)
│   │                              #   scr3040 · scr3050 · scr4010 · scr4016 · scr2011
│   ├── gold/transformations/      #   ONE notebook per gold artifact:
│   │                              #   posicao_{3040,3050,4010,4016,2011,4060}
│   │                              #   · criticas_ddr_2011 · criticas_cosif_4060
│   │                              #   · reconciliacao_cosif · processing_state
│   └── classical/                 # CLASSICAL mode (default): plain PySpark notebooks,
│       ├── bronze/                #   no `import dlt`. Same tables/contract as the DLT path.
│       ├── silver/                #   Bronze = Auto Loader batch; silver/gold = saveAsTable.
│       └── gold/                  #   Same 8 files as gold/transformations/ (1 task each).
│
├── notebooks/                     # Accelerator utility notebooks
│   └── setup/
│       ├── setup_reference_tables.py   # Loads BACEN domains/criticas/calendar (NOT synthetic)
│       ├── setup_reference_4060.py     # 2 críticas de EXEMPLO do 4060 como DADOS
│       │                               #   + Anexo I da Res. BCB 352 (vazio)
│       ├── setup_reference_2011.py     # GERADO — domínios dos 7 anexos do DDR 2011
│       │                               #   (551 valores) + views v_dom_2011_*.
│       │                               #   Regenerar: scripts/gen_ddr2011_reference_seed.py
│       └── grant_dqx_lakebase_access.sql  # ⚠️ SQL **Postgres**, não notebook. GRANT de
│                                       #   leitura em dq_quality_rules. MANUAL e a
│                                       #   refazer a cada destroy. Os grants de UC
│                                       #   seguem em grant_dqx_studio_access.sql.
│
├── dashboards/                    # Lakeview JSON definitions (3)
│
├── sample/                        # Canonical CADOC samples uploaded by the implementation
│                                  # bundle into ${var.catalog}.landing.scr_xml:
│                                  #   Doc3040_*.xml · Doc3050_*.xml (2026-03/04)
│                                  #   Doc4010_*.xml (mensal 2026-03/04) + Doc4016_*.xml
│                                  #   (semestral 2025-06/12) — leiaute XML oficial;
│                                  #   Doc4010_*_2024-12.txt = posicional legado
│                                  #   Doc4060_*.xml (Conglomerado Prudencial, mensal:
│                                  #   2026-05/06) — sintético, 56 contas, gerado por
│                                  #   scripts/gen_cadoc4060_sample.py com invariantes
│                                  #   E3/E4/E5/G100 garantidos por construção;
│                                  #   Doc2011_*.xml (DDR, DIÁRIO: 2026-03-27/30/31 +
│                                  #   2026-04-01/02) — gerado por
│                                  #   scripts/gen_ddr2011_sample.py, validado no XSD
│
├── resources/                     # DAB resources of the accelerator (no demo jobs here)
│   ├── app.yml                    # App resource — USE_MOCK_BACKEND=false via apps.config.env
│   ├── catalog.yml                # ${var.catalog} (default rc18_catalog)
│   ├── warehouse.yml              # Serverless 2X-Small warehouse, default for ${var.warehouse_id}
│   ├── setup_job.yml              # 5 tasks: setup_reference + setup_reference_2011
│   │                              #   + setup_reference_4060
│   │                              #   + load_sample_xmls + setup_byol_lineage
│   ├── uc_assets.yml              # landing/reference schemas + scr_xml/_checkpoints volumes
│   ├── lakebase_role.yml          # Role Postgres do SP do app no Lakebase da Studio
│   │                              #   (para LER dq_quality_rules). GRANT é MANUAL.
│   ├── postgres_catalogs.yml      # Registra o Lakebase da Studio como catálogo UC
│   │                              #   read-only — só para os dashboards Lakeview.
│   ├── classical/                 # CLASSICAL mode (default, included): jobs bronze/silver/gold
│   │                              #   + orchestration_job.yml (rc18_end_to_end). No SDP resources.
│   ├── pipelines/                 # SDP/DLT mode (opt-in, commented in include):
│   │                              #   {bronze,silver,gold}.yml + orchestration_job.yml
│   └── analytics/dashboard_*.yml
│
├── scripts/                       # Dev utilities (not deployed)
├── docs/                          # Specs, BACEN references, regulatory docs
│   ├── cosif/                     # Leiaute oficial 4010/4016 (PDF do BCB) + README com
│   │                              #   tabelas de campos, DV da conta e base normativa
│   ├── cadoc4060/                  # Leiaute oficial 4060/4066 (PDF do BCB) + Tabela de
│   │                              #   Críticas COSIF + README com o catálogo de
│   │                              #   catálogo de críticas e as pendências
│   └── ddr2011/                    # Leiaute oficial 2011/DDR (XLS v5 + XSD + exemplo XML +
│                                  #   críticas + instruções PDF) + README com as 92 contas
│                                  #   do Anexo 4 e as 11 críticas vigentes
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
# MANUAL, and must be REDONE after every destroy+deploy (the app SP's client id
# changes): grant the app's Postgres role SELECT on the Studio's rules table in
# Lakebase. Without it Críticas SCR renders empty. See "Bundle gotchas".
databricks psql --project dqx-studio-db --branch dqx \
  -- -d databricks_postgres -f notebooks/setup/grant_dqx_lakebase_access.sql
databricks bundle run setup_reference_tables                                         # seeds reference + loads sample XMLs into landing
databricks bundle run bronze                                                         # ingests sample XMLs
databricks bundle run silver                                                         # bronze→silver ELT
databricks bundle run gold                                                           # curated position tables
databricks bundle run rc18_end_to_end                                                # (alt) whole stack chained in one job
# NOTE: these run commands are IDENTICAL in classical (default) and SDP mode —
# both modes reuse the same resource keys (bronze/silver/gold/rc18_end_to_end).

# === CADOC 4060: regenerar o sample sintético do acelerador ===
# Duas data-bases consecutivas por causa das críticas que comparam a data-base
# corrente com a anterior. Sem dado de cliente; versionado. Grava em sample/
# direto — o glob de load_sample_xmls não é recursivo.
python scripts/gen_cadoc4060_sample.py                                               # → sample/Doc4060_C0000001_2026-{05,06}.xml

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
| `landing` | 0 + volumes | Raw inbox (volumes: scr_xml, _checkpoints) — one subfolder per CADOC: `scr_xml/{3040,3050,4010,4016,2011}/` |
| `bronze` | 6 | Parsed XML docs, one row per file (`raw_3040_doc`, `raw_3050_doc`, `raw_2011_doc`) + COSIF balances, one row per account, **one table per document** (`raw_4010_saldos`, `raw_4016_saldos`) + `raw_4060_saldos` (uma linha por bloco×entidade×conta — o 4060 tem 7 blocos) |
| `silver` | 13 | Normalized tables (pure ELT, no quality columns) — naming pattern `scr<CADOC>_<entidade>`: `scr3040_operacoes`, `scr3040_clientes`, `scr3040_garantias`, `scr3040_vencimentos`, `scr3040_cont_4966` + unified `scr3050` + `scr4010_saldos` (Balancete, mensal) e `scr4016_saldos` (Balanço, semestral) + `scr2011_contas`/`scr2011_detalhamentos`/`scr2011_parametros` (DDR, **diário** — uma tabela por grão do leiaute) + `scr4060_saldos_entidade`/`scr4060_saldos_consolidado` (Conglomerado Prudencial, mensal — também uma tabela por grão). Written by the silver DLT pipeline (DLT writes to a single schema). |
| `gold` | 10 | Curated (`posicao_3040`, `posicao_3050`, `posicao_4010`, `posicao_4016`, `posicao_2011`, `posicao_4060`) + `reconciliacao_cosif` (batimento 3040×4010) + `criticas_ddr_2011` (críticas intra-DDR 4693/4751) + `criticas_cosif_4060` (as ~260 críticas do 4060, avaliadas por um motor genérico sobre `reference.criticas_cosif`) + `processing_state` (1-row: `current_data_base`/`data_base_month`/`updated_at`; alimenta o seletor de Data-Base do app via `GET /dashboard/data-bases`. Cada CADOC contribui com o **mês** da sua data-base — 3040/3050/**4010**/**4060**/**2011** — e `current_data_base` é o MAX dt_base DENTRO do mês vigente. `posicao_4016` fica FORA de propósito — é semestral e empurraria o seletor mensal) |
| `reference` | 9 | Domains (inclui os 551 valores dos 7 anexos do DDR 2011 + views `v_dom_2011_*`, e os anexos 1–3 do 4060 + views `v_dom_4060_*`), criticas rules, BCB calendar, equivalencia 3040↔3050, R.18 dimensions, leiaute versions, `cosif_contas` (mapa de batimento COSIF), `criticas_cosif` (as críticas do 4060 como DADOS de domínio: operador + contas de cada lado + comparador), `cosif_anexo_i_res352` (percentuais de perda esperada) |

## Key Links

### BCB Reference Pages
- SCR Doc 3040: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040
- SCR Doc 3050: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3050
- COSIF Doc 4010: https://www.bcb.gov.br/fis/info/doc4010.asp · Doc 4016: https://www.bcb.gov.br/fis/info/doc4016.asp
- Leiaute COSIF 4010/4016 (um só p/ os dois): https://www.bcb.gov.br/estabilidadefinanceira/leiautecosif4010 — cópia + tabelas de campos em [docs/cosif/](docs/cosif/README.md)
- COSIF Doc 4060: https://www.bcb.gov.br/fis/info/doc4060.asp · Leiaute 4060/4066 (um só p/ os dois): https://www.bcb.gov.br/estabilidadefinanceira/leiautecosif4060 — cópia + o catálogo de críticas em [docs/cadoc4060/](docs/cadoc4060/README.md)
- Tabela de Críticas COSIF: https://www.bcb.gov.br/content/estabilidadefinanceira/cosif/criticas-cosif/criticascosif.pdf
- Leiaute DDR 2011: https://www.bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011 — cópia (XLS v5 + XSD + exemplo + críticas + instruções) em [docs/ddr2011/](docs/ddr2011/README.md)
- External Lineage (BYOL): https://docs.databricks.com/aws/en/data-governance/unity-catalog/external-lineage

### Google Docs
See [docs/gdocs_notes.md](docs/gdocs_notes.md) for meeting notes and project context links.

## Domain Context

- **R.18**: Joint resolution mandating a formal Data Quality Policy covering ALL information reported to BCB. 12 mandatory quality dimensions, board-level governance, semi-annual reports, 5-year retention. Deadline: 31/12/2026.
- **SCR 3040**: Detailed credit operation data — individual operations with 130+ fields, IPOC identification, cessao/FIDC complexity. Submitted as XML, validated before sending to BCB.
- **SCR 3050**: Aggregated credit data in TXB/XML format. Versioned layouts (current: V11). Weekly/monthly periodicity with BCB business day calendar.
- **COSIF 4010 / 4016**: the two accounting documents (doc 1 do COSIF) that carry the balance per COSIF account. **4010 = Balancete Patrimonial Analítico, monthly**, STA code `ACOS010`, due day 18 of the following month. **4016 = Balanço Patrimonial Analítico, semiannual (June and December only)**, STA code `ACOS016`, due the last business day of the following month; because it is the position *after* the year's result has been appropriated, accounts from groups 7 (Receitas) and 8 (Despesas) are NOT expected. Both share ONE layout — XML since data-base jan/2025 (IN BCB 469/2024), positional before that. Spec + field tables in [docs/cosif/README.md](docs/cosif/README.md); PDF in `docs/cosif/`. The 4010 is the accounting leg of the inter-CADOC reconciliation (crítica N01).
- **COSIF 4060 / 4066**: o par contábil do **conglomerado prudencial** — **4060 = Balancete, MENSAL**; 4066 = Balanço, semestral. Remetido pela instituição **líder** do conglomerado (cadastro no módulo *Conglomerados* do Unicad), em **ordem sequencial obrigatória** (como o DDR 2011). ⚠️ **NÃO** compartilha leiaute com o 4010/4016: tem 1 cabeçalho + **7 blocos**, com a posição contábil no país, no exterior, país e exterior, o balancete individual de cada **entidade assemelhada**, o consolidado prudencial e as dependências e participações no exterior. A regra de formação do documento (`País e Exterior + Assemelhadas − Eliminações = Conglomerado Prudencial`) e `saldoConsolidado = saldoAglutinado − valorEliminacoes` são críticas aritméticas de graça. Spec, catálogo de críticas e pendências em [docs/cadoc4060/README.md](docs/cadoc4060/README.md).
- **DDR 2011**: *Demonstrativo Diário de Acompanhamento das Parcelas de Requerimento de Capital e dos Limites Operacionais* — documento **prudencial** (não contábil) do projeto BCB "Limites Operacionais", periodicidade **diária**. Carrega exposição em ouro/moeda estrangeira/variação cambial e as parcelas de requerimento de capital para risco de mercado (RWACAM, RWAJUR1-4, RWACOM, RWAACS, RWAMPAD, RWAMINT, VPRM). Enviado pelo Sisbacen (transação `SLIM800`), **em ordem sequencial obrigatória**: sem a data-base anterior recepcionada, o BCB não aceita a subsequente. Leiaute v5 (a partir de 01/07/2023) com 7 anexos de domínio — 92 contas, 186 moedas, 248 países. Spec + as 92 contas + as 11 críticas vigentes em [docs/ddr2011/README.md](docs/ddr2011/README.md).
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
- **Lineage**: UC system tables + External Lineage API (BYOL) for external systems. The **Linhagem** page is a read/write management surface over the UC External Metadata + External Lineage APIs (`app/backend/routers/external_metadata.py`, mirroring the native Catalog Explorer "New external metadata" dialog), plus the read-only graph (`routers/lineage.py`). **The graph's UC nodes are the tables bound to a CADOC in `governance.cadoc_tabelas` (the "Vínculo de Regras" screen) that EXIST, plus exactly 1 hop up/down from each via the REST table-lineage API.** `cadoc_tabelas` is seeded with all 12 vínculos, so the existence intersection against `information_schema.tables` is what keeps a partial deployment (e.g. only the DDR pipeline ran) from drawing nodes for tables that were never created; if that filter would empty a non-empty declared list, the declared list wins (a blank graph is the worse failure). Two consequences of the 1-hop limit: a gold table derived from another gold table (`processing_state` ← `posicao_2011`) never shows, and bronze/gold nodes appear only once the pipeline has actually run. Node layer/system/`ingestion_mode` are DERIVED from each external object's own `properties` (`camada`/`sistema`/`ingestion_mode`) — no hardcoded topology. Mixed integration is modeled per source: `file_autoloader` (COBOL/mainframe file drop), `federation` (Lakehouse Federation), `lakeflow_connect`. `notebooks/setup/setup_byol_lineage.py` is a small idempotent **demo seed** (5 objects/5 edges) mirroring `app/backend/external_lineage_store.py` (the mock-mode in-memory store shared by CRUD + graph so edits show up live); the customer manages the real topology from the app. Writes run as the **app SP**, which needs `CREATE EXTERNAL METADATA` on the metastore + `MODIFY` on boundary schemas — see the "GRANT BYOL" section of `notebooks/setup/grant_dqx_studio_access.sql` (missing grant → create/edit forms 403; read-only graph still works). `system_type` enum has no COBOL/DB2 z/OS → those use `OTHER` + real name in the `sistema` property; the inline SVG `SystemTypeIcon` carries system identity (color no longer overloaded with name-substring rules). **`bundle destroy` does NOT remove external metadata/lineage** — those are *metastore*-scoped objects created via API (by the seed OR the app), outside the DAB lifecycle, so they survive a destroy as ORPHANS (`owner=unknown` once the app SP is gone; only a metastore admin can delete them afterward). Before `bundle destroy`, delete the `rc18_*` objects manually — list with `databricks api get /api/2.0/lineage-tracking/external-metadata` and `databricks api delete /api/2.0/lineage-tracking/external-metadata/<name>` for each, or re-run the seed notebook (it deletes all `rc18_*` before recreating). This is a documented manual step (there is no reliable DAB pre-destroy hook to automate it).

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
- DLT `@dlt.table(schema=...)` is **column DDL**, not the target schema — every DLT pipeline writes to a SINGLE schema (its `schema:` config). To write to multiple schemas, split into multiple pipelines. (Classical mode has no such limit — a single job task writes wherever `saveAsTable` points, which is why a classical silver notebook can cover several tables of the same CADOC: `scr3040.py` writes 5, `scr2011.py` writes 3.)
- `dlt.read("name")` only works for tables defined in the **same** pipeline, with an unqualified name. For cross-pipeline reads (e.g., gold reading silver tables), use `spark.table(f"{catalog}.{schema}.{table}")`. The classical notebooks use `spark.table` everywhere (no `dlt.read`); the gold `processing_state` same-pipeline dependency becomes a separate task that `spark.table`-reads the positions written by its predecessor tasks.
- **Gold is ONE notebook per artifact, and the classical task keys are per document.** `pipelines/{classical/,}gold/` each hold 10 files (`posicao_{3040,3050,4010,4016,2011,4060}` · `criticas_ddr_2011` · `criticas_cosif_4060` · `reconciliacao_cosif` · `processing_state`), replacing a single `posicao_mensal.py`, so a CADOC goes bronze→silver→gold without waiting on the others. Three consequences:
  - In `rc18_end_to_end` the task key `gold` is GONE — it became `gold_3040`/`gold_3050`/`gold_4010`/`gold_4016`/`gold_2011`/`gold_4060`/`gold_criticas_2011`/`gold_criticas_4060`/`gold_reconciliacao_cosif`/`gold_processing_state`. Update any `--only gold`. The resource keys are preserved, so `bundle run gold` / `bundle run rc18_end_to_end` are unchanged.
  - Only the two cross-CADOC artifacts fan in: `reconciliacao_cosif` on silver 3040 + 4010, `processing_state` on the 4 MONTHLY positions (4016 excluded — semiannual).
  - Classical `processing_state`/`reconciliacao_cosif` tolerate a missing source table (`spark.catalog.tableExists`): with a subset of CADOCs active, an absent table means "out of scope", not failure. `reconciliacao_cosif` exits instead of computing half a batimento — read that skip as "N01 was NOT evaluated". SDP can't express this (a `@dlt.table` must return a DataFrame; an empty one would wipe the table), so it stays all-or-nothing — the one deliberate behavioural difference between the modes.
- **Bronze parser choice (3040 vs 3050)** —
  - `raw_3040_doc` uses Auto Loader's **native XML reader** (`cloudFiles.format=xml`, explicit schema, JVM-only). Reshaped to the legacy `header + clientes/operacoes/garantias/vencimentos/cont4966` arrays with Spark `transform`/`flatten`/`filter` so silver doesn't see a contract change. Faster than Python-UDF parsing for production-scale files (10k+ ops).
  - `raw_3050_doc` stays on `binaryFile + lxml` UDF because the TXB V11 taxonomy uses element *names* (`<crdLivre><pesJuridica><pre><capGirPrzAte365 …/>`) as the dimension axis — defining a static native-XML schema would require enumerating every BCB taxonomy node and is brittle for what are tiny files (~1KB).
  - `lxml` is therefore declared under `environment.dependencies` for the 3050 path in BOTH modes — `resources/pipelines/bronze.yml` (SDP) and `resources/classical/bronze.yml` + `resources/classical/orchestration_job.yml` (classical `serverless_env`).
  - When migrating from `binaryFile` to native XML, use a NEW `cloudFiles.schemaLocation` path (e.g. `_checkpoints/bronze_3040_xml_native/`) — Auto Loader's checkpoint state is format-specific and reusing the old path crashes.
- **COSIF 4010/4016 são UM leiaute, e o formato oficial é XML desde a data-base jan/2025.** A `IN BCB 469/2024` substituiu o arquivo posicional (71 posições) pelo XML — `<documento codigoDocumento cnpj dataBase tipoRemessa><contas><conta codigoConta saldo/></contas></documento>`, enviado no STA com `ACOS010` (4010) / `ACOS016` (4016). Apesar do leiaute ser um só, cada documento tem seu PRÓPRIO notebook e sua PRÓPRIA tabela (`raw_4010.py`→`bronze.raw_4010_saldos`, `raw_4016.py`→`bronze.raw_4016_saldos`, e o mesmo na silver) — os clientes operam 4010 e 4016 de forma independente, então cada um precisa de task, checkpoint e reprocessamento próprios, como já ocorre com 3040/3050. O preço é parse duplicado: **se mudar o parse de um, mude o do gêmeo** (as 4 combinações doc×modo devem ficar idênticas fora da prosa). A coluna `formato_origem` (`xml` | `posicional`) registra de qual leiaute a linha veio, e `documento` é gravada SEM filtro na silver de propósito: um arquivo do 4016 na pasta do 4010 tem de chegar na silver para o check DQX `documento_e_4010` acusar, em vez de desaparecer em silêncio. O leiaute XML **não tem campo de sinal** (o posicional tem, na posição 33), então `sinal` fica NULL nas linhas vindas de XML — `gold.reconciliacao_cosif` já usa `abs(saldo)`, então não é afetado. Tabelas de campos e base normativa em [docs/cosif/README.md](docs/cosif/README.md).
- **O CADOC 4060 NÃO compartilha o leiaute do 4010/4016.** São todos COSIF, mas o 4010/4016 é uma lista plana de contas e o 4060 tem **1 cabeçalho + 7 blocos**, com a posição de cada entidade do conglomerado. Consequências no modelo: bronze é UMA tabela larga com a coluna `bloco` como discriminador e colunas de valor nuláveis (os blocos têm formas diferentes — `saldoAglutinado`/`valorEliminacoes`/`saldoConsolidado` nos consolidados, `saldoContabil`/`saldoAte3Meses`/`saldoApos3Meses` nas assemelhadas, `saldo` nas dependências/participações); a silver separa em **2 tabelas por grão** (`scr4060_saldos_entidade` para os blocos 4/6/7, `scr4060_saldos_consolidado` para 1/2/3/5), mesmo critério do DDR 2011. Misturar entidade e consolidado numa tabela só obrigaria toda consulta a filtrar por bloco para não somar os dois. `gold.posicao_4060` é o bloco 5 (`consolidadoPrudencial`) — o número que representa o conglomerado — com `saldo` apelidado de `saldo_consolidado` para ficar comparável a `posicao_4010`.
- **As críticas do 4060 são DADOS DE DOMÍNIO; o acelerador versiona só 2 de EXEMPLO.** `reference.criticas_cosif` guarda uma linha por crítica — `operador`, contas de cada lado com peso, `comparador`, tolerância — sem expressão SQL embutida. `gold.criticas_cosif_4060` é um avaliador genérico que não sabe quantas regras existem, então carregar o catálogo de uma instituição é `INSERT`, nunca código. O seed traz `COS00584` (lado único, soma fecha em zero) e `COS00802` (lado duplo com comparador). As 2 citam contas COSIF reais, ausentes do sample sintético, então nele dão `INDETERMINADO` (conta citada que não veio ⇒ nunca zero) — o `OK` do primeiro deploy vem da estrutural `SOMA_PRUDENCIAL`.
  Os cinco operadores são batizados com o NOME que o BCB dá à crítica arquetípica de cada família (Tabela de Críticas COSIF), para o vocabulário ser reconhecível por quem lê as tabelas do regulador: `TOTAL_DIFERE_DAS_PARCELAS` (crítica **E3**) · `CONTRAPARTIDA_AUSENTE` (*"Contrapartida Ativo Passivo"*) · `SALDO_INFERIOR_AO_ESPERADO` (*"não pode ser inferior a"*) · `SALDO_INDEVIDO` (*"não podem registrar saldos"*) · `DIVERGENCIA_ACIMA_DA_TOLERANCIA`. ⚠️ O BCB **não** publica taxonomia de operador — os códigos (`A7`, `E3`, `COS00802`) identificam críticas individuais. O recorte em famílias é do acelerador; os rótulos são do BCB.
  `tipo_critica` guarda o `E`/`I` do BCB (Erro reprova o documento · Indício é sinalizado no CRD), como já se faz em `gold.criticas_ddr_2011`; `criticality` (o que o DQX consome) é derivada dele — `E → error`, `I → warn` — e gravada como coluna no seed. Mude a coluna se a instituição quiser tratar indício como bloqueante.
  `modulo_esquerda`/`modulo_direita` existem porque `|a| + |b| ≠ |a + b|` e o avaliador distingue os dois casos; `simetrico` cobre a forma em que a crítica só aprova quando os DOIS lados têm saldo.
- **O `filter` de um check DQX não tolera literal string, por isso existe `critica_seq`.** O round-trip de `parse_json` da Studio corrompe aspas, então o recorte por crítica usa a chave NUMÉRICA `critica_seq` (única e rastreável), nunca `critica_id`. É a mesma razão pela qual os checks do DDR 2011 usam `cast(critica_id as int) = 4693`. A crítica estrutural calculada pelo próprio gold (`SOMA_PRUDENCIAL`) usa `seq` reservado (`900001`) para nunca colidir. Um check por crítica, nunca um guarda-chuva (o repo já removeu o guarda-chuva do DDR justamente por perder a rastreabilidade por crítica).
- **`INDETERMINADO` é status de primeira classe em `gold.criticas_cosif_4060`.** Perna ausente que NÃO tolera ausência ⇒ `INDETERMINADO` e veredito nulo, em vez de assumir zero e devolver um "ok" que o BCB não daria. A view `v_crit_4060_status_bloqueante` inclui `INDETERMINADO`, então crítica inavaliável não passa em silêncio.
- **18 críticas do 4060 comparam com a data-base ANTERIOR, e isso muda o que a landing precisa ter.** O sample sintético traz DUAS data-bases (`2026-05` e `2026-06`) por esse motivo; com um mês só essas regras ficam permanentemente indeterminadas. Os checks dessas 18 são gerados como `warn`, não `error`: na primeira data-base a falha é estrutural (falta histórico), não de dado.
- **`gold.posicao_4060` ENTRA em `processing_state`** — o 4060 é mensal. O contraste é com `posicao_4016`, que fica fora por ser semestral. Mesma lógica do 4010.
- **Conta COSIF: o grupo é o 1º dígito SIGNIFICATIVO, nunca `substring(codigo_conta, 1, 1)`.** O campo tem 10 dígitos, mas as contas representativas deste repo (e as de qualquer extração legada) vêm na forma antiga — 8 dígitos + DV preenchidos à esquerda com zeros (`0031000000` = grupo 3) — enquanto a forma oficial de jan/2025 começa já no grupo (`1000000009` = grupo 1). Usar o 1º caractere retorna `0` para toda conta legada e faz o check "4016 não pode ter grupos 7/8" NUNCA acusar violação (falso-negativo silencioso). A derivação correta, usada em `scr4010.py`/`scr4016.py`, é `substring(cast(codigo_conta as bigint) as string, 1, 1)`.
- **O DV da conta COSIF é verificável e vale a pena checar**: pesos 3-7-1 repetidos da direita para a esquerda sobre os 9 dígitos de hierarquia, `DV = 10 - (soma mod 10)` (0 se o resto for 0). Confirmado contra os quatro códigos do exemplo oficial do BCB (§4 do leiaute). Implementado no check DQX `conta_cosif_digito_verificador` e em `dv_cosif()` no gerador do demo.
- **`gold.posicao_4016` NÃO entra em `processing_state`.** O 4016 é semestral (só junho/dezembro), então um Balanço de 30/06 entraria no `MAX(dt_base)` e empurraria o seletor de Data-Base do app para um mês em que 3040/3050/4010 ainda não têm posição. O seletor acompanha o ciclo MENSAL — `processing_state` cobre apenas `posicao_3040`/`3050`/`4010`.
- **O DDR (Doc 2011) é DIÁRIO, mas o seletor de Data-Base é MENSAL e compartilhado por todos os CADOCs.** `gold.processing_state` não guarda data-base por documento: cada CADOC contribui com o **mês** da sua data-base, o mês vigente é o maior deles e `current_data_base` é o `MAX(dt_base)` dentro dele. É essa redução que acomoda o DDR sem modo especial — suas várias datas no mês colapsam. Como o DDR é remetido todo dia útil, normalmente é ele que define o mês vigente, então o mês corrente aparece antes de 3040/3050/4010 fecharem (correto para mês em andamento). Os checks DQX do 2011 filtram por `data_base_month`, **não** por `dt_base`: com várias datas-base no mês, o último `dt_base` avaliaria só o último dia remetido. `posicao_2011` preserva o grão diário e marca `is_ultima_do_mes`.
- **Só 2 das 11 críticas oficiais do DDR são implementáveis.** As outras 9 confrontam os documentos **2060 (DRM)** e **2061 (DLO)**, que o acelerador não ingere. Sobram a **4693** (E: conta 161000 ≥ 181000) e a **4751** (I: chaves duplicadas posição×moeda). Ambas são de grão AGREGADO e a `sql_expression` do DQX roda linha a linha — então são materializadas em `gold.criticas_ddr_2011` com coluna `status` e o check só verifica o status (mesmo padrão da N01 em `reconciliacao_cosif`). Não tente expressá-las como check de silver.
- **Os domínios do DDR 2011 vêm de um notebook GERADO — nunca edite à mão.** Os 7 anexos somam 551 valores (92 contas + 186 moedas + 248 países + 25 dos demais); transcrever erra. `scripts/gen_ddr2011_reference_seed.py` lê a aba `Anexos` do XLS oficial e emite `notebooks/setup/setup_reference_2011.py` com os domínios embutidos (autocontido em runtime). Leiaute novo do BCB → baixe o XLS, rode o script, revise o diff. Idem para `sample/Doc2011_*.xml` via `scripts/gen_ddr2011_sample.py --validate`. ⚠️ `docs/` é git-ignored: o XLS de origem não é versionado, só o notebook gerado — o comando de download está no docstring do script.
- **A soma dos `valorDetalhe` NÃO precisa bater com o `valorConta` no DDR.** Parece óbvio que deveria, mas o próprio arquivo de exemplo do BCB viola o invariante (conta 141000), então não é regra do leiaute e não há check para isso. Avaliá-lo exigiria cruzar `scr2011_contas` × `scr2011_detalhamentos` — candidato a materializar no gold, como as críticas 4693/4751.
- **Setup job table with `DEFAULT` columns** needs `TBLPROPERTIES('delta.feature.allowColumnDefaults' = 'supported')` on Delta. Already wired in `notebooks/setup/setup_reference_tables.py` for `modalidades_equivalencia`.
- Stale `terraform.tfstate` from a previous workspace will fail with `workspace_id mismatch`. Destroy the target against its original workspace first; only then wipe `.databricks/bundle/<target>/` before redeploying that target elsewhere.
- **Direct-engine state is target-scoped, not profile-scoped** — this repository has one default target fixed as `dev`. Before changing `workspace.profile` in `target.yml`, destroy the existing deployment against the original workspace; otherwise resources can be orphaned.
- **Dois bugs dos dashboards que sobreviveram porque ninguém cruzava o SQL com o dado.** `status IN ('active','approved')` tinha ramo morto (a Studio removeu `active`), e o `ds_regras_por_dimensao` do `monitor_criticas` juntava o tag `dimensao_r18` (**arábico**, `"6"`) direto em `reference.dimensoes_r18.dimensao_id` (**romano**, `VI`) sem conversão — esse painel mostrava 0 regras em toda dimensão desde antes da migração. O `conformidade_r18` já tinha o `CASE`. Ambos corrigidos nos 4 JSONs; se criar dataset novo que use o tag, o `CASE` arábico→romano é obrigatório.
- **O GRANT do Lakebase é o único acesso que o bundle NÃO reaplica, e ele quebra a cada `destroy` + `deploy`.** `resources/lakebase_role.yml` cria o role do SP do app, mas role dá LOGIN, não privilégio de objeto: o `GRANT USAGE`/`SELECT` só pode vir de quem é dono das tabelas (SP da Studio, ou `DATABRICKS_SUPERUSER` no branch). O task `grant_warehouse_perms` não cobre — roda COMO o SP do RC18, que não concede a si mesmo. Então `notebooks/setup/grant_dqx_lakebase_access.sql` é manual e refeito sempre que o client id mudar. Sintoma: Críticas SCR e dimensões vazias, com `permission denied for table dq_quality_rules` no log (não 500 — degrada de propósito). Dar `DATABRICKS_SUPERUSER` ao role do RC18 automatizaria, mas concede escrita irrestrita no estado da Studio.
- **Workspace-local target configuration** — root `databricks.yml` includes the git-ignored `target.yml`. Copy `target.yml.example`, then fill the CLI profile and required DQX Studio URL. Azure/AWS/GCP selection belongs to the profile, never to the target name. The direct engine is set via `bundle.engine: direct` in `databricks.yml` (no wrapper); `.env` is exclusively for local app development.

## Key Decisions & Constraints

- Frontend is **Svelte** (not APX/React) — user preference
- Databricks does NOT own full XML generation — app validates/displays XML, does not produce certified XML
- R.18 covers ALL BCB reporting (50+ documents), not just SCR — scope limited to SCR for MVP
- Mock mode enables local development without Databricks connectivity
- Synthetic data has intentional quality issues (3% nulls, 2% out-of-domain, 5% cross-doc divergences)
- Quality trend improves over 3 months (Jan 82% → Feb 91% → Mar 96%) for compelling demo
- **DQX Studio is a mandatory prerequisite for quality rule authoring and execution.** It is an external Databricks App from Databricks Labs DQX (https://databrickslabs.github.io/dqx/docs/guide/dqx_studio/) and is not provisioned by this bundle. The target must provide `dqx_studio_url`; the RC18 app embeds it at `/rules`. Pipelines silver/gold remain pure ELT — no embedded DQX dependency, no `_errors`/`_warnings` columns, no `quality.dqx_checks` table. **A Studio agora exige Lakebase habilitado no workspace** (o backend Delta dela foi removido), o que torna Lakebase pré-requisito transitivo do RC18 — ver o bullet de `dq_quality_rules`.
- **DQX monthly-run scope via a subquery in the check `filter`.** The DQX checks in `quality/dqx_checks/*.yml` run monthly and must evaluate only the latest data-base. Each check carries `filter: "dt_base = (SELECT max(dt_base) FROM <its own table>)"` — the `MAX(dt_base)` is recomputed from the data each run, no column or state to maintain. Checks are `sql_expression`, single-table (import one `.yml` per table). **This subquery filter (and the domain/referential checks' `IN (SELECT … FROM reference.*)`) only works if DQX Studio's SP can read `rc18_catalog`** — see the grant gotcha below; without it every subquery silently yields 100% violations. **Run/schedule with "All rows" (`sample_size=0`)** — DQX samples BEFORE the filter, so a small sample on a `dt_base`-partitioned table can miss the current data-base entirely (run reports SUCCESS / 0 violations). (History: a precomputed boolean column and cross-table `sql_query` were both tried and reverted — the subquery filter works once the SP grant is in place and is the simplest, keeping silver ELT-pure and the `.yml` self-contained.)
- **`dq_quality_rules` NÃO está em Unity Catalog — está em Lakebase Postgres, e o RC18 fala Postgres direto (`app/backend/dqx_lakebase.py`).** Desde a DQX 0.15/0.16 a Studio guarda seu estado OLTP (regras, settings, RBAC, comments, schedules) em Lakebase e **removeu o backend Delta** — não há modo de compatibilidade nem migração (o app dela hard-falha no startup sem Lakebase). Só as tabelas append-only de observabilidade (`dq_validation_runs`, `dq_metrics`, `dq_profiling_results`, `dq_quarantine_records`) seguem em Delta, lidas via warehouse por `db.py`. Consequências no repo:
  - O backend passou a falar DOIS dialetos: `:nome` para Databricks SQL e `%(nome)s` para psycopg. `scope_clause()` e `_in_clause()` recebem `paramstyle` por isso. Marcador errado NÃO é erro de sintaxe — no psycopg o `:nome` vira literal, o predicado nunca casa e a tela zera em silêncio.
  - `check` é palavra reservada e a Studio declara a coluna assim (`"check" JSONB`): toda referência precisa de aspas duplas (`dqx_lakebase.CHECK_COLUMN`). O JSONB volta do psycopg já como `dict` — `parse_check_defs()` aceita dict/str/list.
  - **`status IN ('active','approved')` está morto**: o enum atual é `draft|pending_approval|approved|rejected`, com CHECK constraint. Só `approved` conta (`dqx_lakebase.ACTIVE_STATUS`).
  - Nenhuma composição regra×execução pode ser um JOIN SQL único — são engines distintas. Os 5 read sites já eram statements separados, o que é o que tornou a migração viável.
  - **Acesso = role Postgres + GRANT manual.** `resources/lakebase_role.yml` cria o role do SP do app (declarativo, exige CLI ≥ 1.4.0 + entitlement *Lakebase: Manager*); o `GRANT USAGE/SELECT` roda DENTRO do Postgres (`notebooks/setup/grant_dqx_lakebase_access.sql`) e é MANUAL — ver o gotcha em "Bundle gotchas".
  - **Dashboards leem o Lakebase por um catálogo UC registrado** (`resources/postgres_catalogs.yml`, var `dqx_rules_catalog`) — Lakeview não fala Postgres. Verificado por experimento: `check` (JSONB) chega como **STRING** e o acessor `check:name::string` continua valendo, então os datasets mudaram só o FQN (parâmetro `dqx_rules_schema`; `dqx_schema` segue servindo runs/metrics em Delta). Join numa query só entre o catálogo registrado e tabelas Delta funciona. Exige warehouse **Serverless** (Pro/Classic → `PERMISSION_DENIED`) e `embed_credentials: true` nos 4 dashboards, senão cada viewer precisaria de grant no catálogo. O catálogo NÃO é sufixado por target: com vários deployments na mesma Studio, um gerencia o recurso e os outros só apontam a var.
- **O preço da degradação graciosa é um diagnóstico explícito: `app/backend/diagnostics.py` + `GET /api/v1/diagnostics/prereqs`.** Como as leituras devolvem `[]` sem acesso, "falta permissão" e "não há regra" dão a MESMA tela vazia. O módulo classifica a causa e devolve o comando **já preenchido com o client id do app** (`dqx_lakebase.identity()`). `PrereqAlert.svelte` só consulta quando a tela vem vazia e traz "Re-verificar" — funciona sem restart porque o pool é lazy. Regra de ouro: **prescrição só quando a causa é conhecida** (Postgres por SQLSTATE `42501`, UC por `_UC_ACCESS_ERRORS`); outro erro vira `failed` SEM comando, porque prescrever GRANT para warehouse parado é pior que não diagnosticar. O check `rules_materialized` codifica a pegadinha do fluxo novo: YAML importado vira regra no Registry, e só chega em `dq_quality_rules` quando o vínculo da tabela é PUBLICADO em Tabelas.
- **As leituras de `dq_quality_rules` são escopadas por catálogo E indexadas por `(table_fqn, check_name)` — via `app/backend/dqx_rules.py`.** A tabela de regras da DQX Studio é compartilhada por todos os deployments que apontam para a mesma Studio (antes metastore-wide em UC, agora um schema Postgres único): ela contém as regras de todos. Duas defesas, ambas no módulo: `scope_clause()` restringe às tabelas deste deployment (`<catalog>.%` ∪ `cadoc_tabelas`) e `RuleIndex` indexa pelo PAR, porque **`check_name` não é único** em `dq_quality_rules` (o grão real é tabela+regra). Sem isso, uma regra homônima de outro projeto sobrescrevia o `user_metadata` e trocava a dimensão R.18 exibida, sem erro. O `RuleIndex.get()` tenta o par e cai para o nome só se o par não casar (`source_table_fqn` dos runs e `table_fqn` das regras vêm de caminhos diferentes da Studio e podem divergir; sem o fallback, divergência de formatação zeraria a tela). Efeito colateral por desenho: regras com `table_fqn` que não é tabela (`__sql_check__/<name>`, para checks de SQL puro) ficam fora — registre a tabela em `cadoc_tabelas` se precisar delas. Histórico: as leituras nasceram quando a DQX era LOCAL ao catálogo RC18 (o fallback `DQX_CATALOG = os.getenv("DQX_CATALOG", CATALOG)` ainda testemunha isso, hoje só para as tabelas Delta); a Studio externa chegou depois, e a migração para Lakebase depois disso.
- **Vários deployments no MESMO workspace: o isolador é o CATÁLOGO, e o nome do target dá o resto de graça.** Quase todo recurso já é sufixado por `${bundle.target}` (app `${var.app_name}-<target>`, jobs `r18-*-<target>`, warehouse `rc18-warehouse-<target>`, e o `root_path` default `~/.bundle/<bundle>/<target>`), então um novo target resolve as colisões de nome sozinho. O `catalog` NÃO é sufixado — tem de ser setado explicitamente no novo target, e é ele que separa os deployments na DQX Studio compartilhada (`scope_clause()` filtra por `<catalog>.%`). Dois deployments no mesmo catálogo continuam se misturando. Dois pontos que exigem trabalho manual: (a) os `.yml` em `quality/dqx_checks/` têm o catálogo **hardcoded** (~84 ocorrências) — faça `sed` antes de importar na Studio; (b) os `display_name` dos dashboards Lakeview não são sufixados, então aparecem com nomes idênticos na listagem (não quebra — ficam em pastas distintas por target — mas confunde). `grant_warehouse_perms.py` recebe o catálogo via widget **obrigatório** (`catalog`, sem default): um default silencioso ali fazia o segundo deployment grantar no catálogo do primeiro — app novo sem permissão no próprio catálogo E o SP da Studio sem leitura, o que devolve 100% de violação silenciosa nos checks com subquery. O SP da Studio acaba com leitura em vários catálogos, o que é esperado: o isolamento das REGRAS é no app (`dqx_rules.py`), não por permissão.
- **DQX Studio's SP needs read access to `rc18_catalog` (bidirectional grant, non-obvious).** DQX validation jobs run as DQX Studio's OWN service principal (the job `run_as`/creator — can differ from the app's `service_principal_client_id`). Any check that reads another table via subquery — domain checks (`IN (SELECT valor_codigo FROM reference.v_dom_3040_*)`), referential integrity (`EXISTS ... silver.scr3040_clientes`), COSIF status (`NOT IN reference.v_recon_status_bloqueante`) — needs that SP to have `USE CATALOG` + `SELECT` on `rc18_catalog.{silver,gold,reference}`. **If missing, those checks flag 100% of rows as violations** (subquery can't resolve → expression NULL → all fail) and the run still reports SUCCESS — a silent false-positive. `foreign_key` fails loudly with `INSUFFICIENT_PERMISSIONS: USE CATALOG on rc18_catalog`. Find the SP via `databricks api get /api/2.1/jobs/runs/get?run_id=<a validation run>` → `creator_user_name`. Grants added to `notebooks/setup/grant_dqx_studio_access.sql` ("GRANT REVERSO" section) — the existing RC18→DQX read grant is only half of what's needed.
