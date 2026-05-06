# RC18 StarterKit — Acelerador BACEN Resolução Conjunta nº 18

Starter kit Databricks para conformidade com a **Resolução Conjunta BACEN nº 18** (governança de dados sobre risco de crédito — SCR Doc 3040 e Doc 3050).

Entrega uma aplicação Databricks (FastAPI + Svelte) de monitoramento de qualidade e validação, esqueletos de pipelines DLT para tratamento dos CADOCs (como exemplo os 3040/3050), dashboards no AI/BI e uma sala Genie.

---

## Como usar este repositório

Dois caminhos:

### 1. Implementar o acelerador no seu ambiente

Você usa o repositório como **atalho** para construir sua própria solução de conformidade com a RC18 no seu ambiente Databricks. Estende a app, pluga seus dados reais nos pipelines 3040/3050 (e outros CADOCs), customiza dashboards.

```bash
git clone <repo>
cd regulatory-data-governance
export DATABRICKS_BUNDLE_ENGINE=direct                       # obrigatório (bundle declara `catalogs:`)
databricks bundle deploy -t dev --profile <seu-profile>      # cria catálogo, warehouse, schemas, app, pipelines, dashboards
databricks bundle run rc18_end_to_end -t dev --profile <seu-profile>   # orquestra setup → bronze → silver → gold
databricks bundle run r18_compliance_app -t dev --profile <seu-profile> # Disponibilizando o app após o deployment
```

> Prefere rodar passo a passo? Veja [Passo a passo](#passo-a-passo) abaixo, que dispara cada job/pipeline individualmente.

Como padrão, são implementados pipelines utilizando dois arquivos de exemplo (CADOCs 3040 e 3050) disponibilizados no diretório [sample](/sample/). Estes arquivos foram gerados sinteticamente e já validados com o Validador Oficial do BACEN.

### 2. Ver o acelerador em ação (modo demo)

Quer experimentar o acelerador fim-a-fim simulando a geração de dados fictícios — Doc 3040 sendo gerado, agregado em 3050 e exibido nos dashboards.

```bash
cd demo
databricks bundle deploy -t dev    # sobe acelerador + geradores sintéticos + loader
```

- Bundle `rc18-demo` inclui **todo o acelerador** MAIS os geradores de Doc 3040/3050 e o loader de dados fictícios.
- Ver [demo/README.md](demo/README.md) para parâmetros dos jobs.

---

## Configuração de ambiente

| Cenário | Como configura |
|---------|----------------|
| **Deploy do bundle** (Databricks Apps + pipelines) | O bundle provisiona catálogo, warehouse, schemas e dashboards e injeta os IDs no app via `apps.config.env` em [resources/app.yml](resources/app.yml#L18-L36) — usando referências `${resources.*}` que resolvem em deploy time. **Preencha o arquivo `.env`** para o deploy funcionar corretamente no seu próprio ambiente.|
| **Dev local** (`./run_local.sh`) | `app/backend/main.py` carrega `.env` via `python-dotenv` no startup. Copie `.env.example` → `.env` e ajuste se for testar em um workspace real. Para dados mockados (default), `USE_MOCK_BACKEND=true`, neste caso não é utilizado dados reais do ambiente. |
| **Frontend** | Não lê `.env` direto — recebe URLs/IDs via API do backend. |

Variáveis relevantes (ver [.env.example](.env.example) para a lista completa):

| Variável | Descrição |
|----------|-----------|
| `DATABRICKS_HOST` | Host do workspace (`adb-<id>.<n>.azuredatabricks.net`) — apenas para dev local contra workspace real |
| `DATABRICKS_WAREHOUSE_ID` | Apenas para dev local; em deploy de produção o bundle aponta o app para o warehouse provisionado |
| `DATABRICKS_CATALOG` | Apenas para dev local; em deploy o bundle define via `${var.catalog}` |
| `DASHBOARD_ID_CONFORMIDADE` / `_CRITICAS` | Apenas para dev local; em deploy o bundle resolve via `${resources.dashboards.*.id}` |
| `GENIE_SPACE_ID` | Set quando houver um Genie Room provisionado externamente |
| `USE_MOCK_BACKEND` | `true` no dev para servir fixtures sem Databricks |

---

## Estrutura do repositório

```
regulatory-data-governance/
│
├── databricks.yml                 # Bundle do ACELERADOR (rc18-starter-kit)
├── README.md                      # Este arquivo
├── CLAUDE.md                      # Guia de contexto para Claude Code
├── .env.example                   # Template de configuração (copie para .env)
├── run_local.sh                   # Dev local (sobe app + frontend localmente)
│
├── app/                           # Aplicação (FastAPI + SvelteKit)
│   ├── backend/                   # API FastAPI servida pelo Databricks Apps
│   │   ├── main.py
│   │   ├── routers/               # Endpoints REST por domínio
│   │   ├── models.py              # Pydantic v2
│   │   ├── db.py                  # Conexão Databricks SQL (mock/real)
│   │   ├── app.yaml               # Runtime config do Databricks App
│   │   ├── requirements.txt
│   │   └── frontend_dist/         # Build estático do Svelte (servido pelo FastAPI)
│   └── frontend/                  # Código-fonte SvelteKit 5
│       ├── src/routes/
│       ├── src/lib/
│       ├── package.json
│       ├── svelte.config.js
│       └── vite.config.js
│
├── pipelines/                     # Esqueletos de pipelines DLT (medallion)
│   ├── bronze/transformations/    # Ingestão raw (3040, 3050, COSIF)
│   ├── silver/transformations/    # Validação + expectations R.18 + métricas
│   └── gold/transformations/      # Reconciliação, scorecard, posições
│
├── notebooks/                     # Notebooks utilitários do acelerador
│   └── setup/
│       └── setup_reference_tables.py   # Carrega domínios/críticas/calendário BACEN
│
├── dashboards/                    # Definições Lakeview (AI/BI)
│   ├── conformidade_r18.lvdash.json
│   └── monitor_criticas.lvdash.json
│
├── resources/                     # DAB resources do acelerador
│   ├── app.yml                    # Databricks App
│   ├── uc_assets.yml              # UC schemas (landing, reference) + volumes
│   ├── setup_job.yml              # Seeds reference tables on deploy
│   ├── orchestration_job.yml      # Job rc18_end_to_end (setup → bronze → silver → gold)
│   ├── pipelines/                 # DLT pipelines
│   │   ├── bronze.yml
│   │   ├── silver.yml
│   │   └── gold.yml
│   └── analytics/                 # Dashboards + Genie
│       ├── dashboard_conformidade.yml
│       ├── dashboard_criticas.yml
│       └── genie_scr.yml
│
├── scripts/                       # Utilitários de dev (não deploy)
│   └── gen_doc3040_pdf.py
│
└── demo/                          # Modo demo — dados sintéticos para experimentar o acelerador
    ├── README.md                  # Como rodar as demos
    ├── databricks.yml             # Bundle rc18-demo (acelerador + geradores)
    ├── notebooks/                 # Geradores 3040/3050 + synthetic_data_loader
    ├── prompts/                   # Meta-prompts usados para criar os geradores
    └── resources/                 # Jobs exclusivos do demo
```

---

## Stack

| Camada | Tecnologia | Pasta |
|-------|-----------|-------|
| Frontend | SvelteKit 5, Svelte Flow, LayerCake, d3 | `app/frontend/` |
| Backend | FastAPI, Pydantic v2, databricks-sdk | `app/backend/` |
| Pipelines | DLT/SDP com Expectations | `pipelines/` |
| Dashboards | Lakeview (AI/BI) JSON | `dashboards/` |
| NL Queries | Genie Room | `resources/analytics/genie_scr.yml` |
| Deployment | Databricks Asset Bundles | `databricks.yml` + `resources/**` |
| Dados | Unity Catalog (catálogo parametrizável via `${var.catalog}`) | — |

---

## Pré-requisitos

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) autenticada
- Python 3.11+ (backend)
- Node.js 18+ e npm (frontend)

---

## Dev local (app)

```bash
# Atalho (sobe backend :8000 + frontend :5173 com mock data)
./run_local.sh
```

Ou manualmente:

```bash
# Backend
cd app/backend
pip install -r requirements.txt
USE_MOCK_BACKEND=true uvicorn main:app --reload --port 8000

# Frontend (em outro terminal)
cd app/frontend
npm install
npm run dev -- --port 5173
```

Abrir http://localhost:5173.

---

## Deploy do acelerador

### Pré-requisitos

- `databricks` CLI autenticada com um profile apontando para o workspace destino
- `DATABRICKS_BUNDLE_ENGINE=direct` exportado no shell (o bundle declara `catalogs:` e exige o direct deployment engine — sem isso o `bundle deploy` aborta na primeira linha)

### Passo a passo

```bash
# 0. (Opcional) Rebuild do frontend se o código Svelte mudou
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist
cd -

# 1. Sobe catálogo, warehouse, schemas, volumes, app, 3 pipelines DLT, 2 dashboards,
#    setup_job e o job de orquestração rc18_end_to_end.
#    O app já é configurado via `apps.config.env` (USE_MOCK_BACKEND=false, dashboards, warehouse) —
#    nenhum overlay de `app.yaml` é necessário.
export DATABRICKS_BUNDLE_ENGINE=direct
databricks bundle deploy -t dev --profile <seu-profile>

# 2a. Atalho: orquestração fim-a-fim (setup_reference → load_sample_xmls → bronze → silver → gold).
#     Roda tudo em um único job com dependências encadeadas.
databricks bundle run rc18_end_to_end -t dev --profile <seu-profile>

# 2b. Alternativa: disparar cada etapa manualmente (útil para reprocessar uma camada).
databricks bundle run setup_reference_tables -t dev --profile <seu-profile>   # seeds reference + carrega XMLs de exemplo
databricks bundle run bronze -t dev --profile <seu-profile>
databricks bundle run silver -t dev --profile <seu-profile>
databricks bundle run gold   -t dev --profile <seu-profile>
```

### Disponibilizando o app após o deployment

Publica o código no compute e deixa o app acessível:

```bash
databricks bundle run r18_compliance_app -t dev --profile <seu-profile>
```

### Bring-your-own (BYOC) catálogo / warehouse

Para apontar o bundle ao seu próprio catálogo e warehouse em vez dos provisionados:

```bash
databricks bundle deploy -t dev --profile <seu-profile> \
  --var catalog=<nome_catalogo_existente> \
  --var warehouse_id=<id_warehouse_existente>
```

Adicionalmente, comente os blocos em [resources/catalog.yml](resources/catalog.yml) e [resources/warehouse.yml](resources/warehouse.yml) para o bundle não tentar gerenciar o ciclo de vida desses recursos externos.

---
