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
databricks bundle run setup_reference_tables -t dev --profile <seu-profile>   # seeds reference + carrega XMLs de exemplo
databricks bundle run bronze -t dev --profile <seu-profile>  # ingere XMLs do landing volume
databricks bundle run silver -t dev --profile <seu-profile>
databricks bundle run gold   -t dev --profile <seu-profile>
```

- **Nenhum dado sintético é envolvido.** O bundle na raiz (`databricks.yml`, nome `rc18-starter-kit`) entrega só o framework — nenhum gerador, nenhum loader fictício. Os XMLs de `sample/` são apenas duas amostras canônicas (uma 3040, uma 3050) que o `setup_reference_tables` copia para `landing.scr_xml` para o `bundle deploy` ser auto-suficiente fim-a-fim.
- **Pode deletar `demo/`** sem medo: nada do bundle do acelerador depende daquela pasta.
- O bundle provisiona um catálogo (`rc18_catalog`) e um SQL warehouse serverless (`rc18-warehouse-<target>`) por padrão. Para reutilizar assets existentes, sobreponha `--var catalog=<nome>` e `--var warehouse_id=<id>` E comente `resources/catalog.yml` / `resources/warehouse.yml` para o bundle não tentar gerenciar o ciclo de vida deles.
- ⚠️ **Após `bundle destroy`**, o primeiro `bundle deploy` apenas inicia o compute do app sem publicar o código (bug conhecido do `lifecycle.started: true` no DABs). Sintoma: app fica em `UNAVAILABLE` apesar do compute `ACTIVE`. Recupere com `bundle deploy` uma segunda vez ou `databricks bundle run r18_compliance_app -t <target>`.
- Próximos passos: conectar as pipelines às suas fontes reais (Oracle/DB2/VSAM/etc.) substituindo os XMLs de `sample/`, e adaptar o app à identidade visual/domínio da sua IF.

### 2. Ver o acelerador em ação (modo demo)

Quer experimentar o acelerador fim-a-fim com dados fictícios — Doc 3040 sendo gerado, agregado em 3050 e exibido nos dashboards.

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
| **Deploy do bundle** (Databricks Apps + pipelines) | O bundle provisiona catálogo, warehouse, schemas e dashboards e injeta os IDs no app via `apps.config.env` em [resources/app.yml](resources/app.yml#L18-L36) — usando referências `${resources.*}` que resolvem em deploy time. **Não é preciso preencher `.env`** para o deploy funcionar. Para reutilizar assets existentes, ver `--var catalog=...` / `--var warehouse_id=...` na seção de deploy. |
| **Devloop local** (`./run_local.sh`) | `app/backend/main.py` carrega `.env` via `python-dotenv` no startup. Copie `.env.example` → `.env` e ajuste se for testar contra um workspace real. Para mock data (default), `USE_MOCK_BACKEND=true` já basta. |
| **Frontend** | Não lê `.env` direto — recebe URLs/IDs via API do backend. |

Variáveis relevantes (ver [.env.example](.env.example) para a lista completa):

| Variável | Descrição |
|----------|-----------|
| `DATABRICKS_HOST` | Host do workspace (`adb-<id>.<n>.azuredatabricks.net`) — apenas para devloop local contra workspace real |
| `DATABRICKS_WAREHOUSE_ID` | Apenas para devloop local; em deploy de produção o bundle aponta o app para o warehouse provisionado |
| `DATABRICKS_CATALOG` | Apenas para devloop local; em deploy o bundle define via `${var.catalog}` |
| `DASHBOARD_ID_CONFORMIDADE` / `_CRITICAS` | Apenas para devloop local; em deploy o bundle resolve via `${resources.dashboards.*.id}` |
| `GENIE_SPACE_ID` | Set quando houver um Genie Room provisionado externamente |
| `USE_MOCK_BACKEND` | `true` no devloop para servir fixtures sem Databricks |

---

## Estrutura do repositório

Cada pasta de topo representa um artefato independente. A separação entre o **acelerador** (raiz) e o **demo** (`demo/`) é física e total — o cliente pode `rm -rf demo/` a qualquer momento.

```
regulatory-data-governance/
│
├── databricks.yml                 # Bundle do ACELERADOR (rc18-starter-kit)
├── README.md                      # Este arquivo
├── CLAUDE.md                      # Guia de contexto para Claude Code
├── .env.example                   # Template de configuração (copie para .env)
├── run_local.sh                   # Devloop local (sobe app + frontend)
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
├── docs/                          # Especificações, requisitos e referência BACEN
│   ├── spec/                      # 6 specs canônicos (fonte da verdade)
│   ├── scr3040/                   # Layout + críticas + validador Doc 3040
│   ├── scr3050/                   # Layout + críticas + validador Doc 3050
│   ├── roundtable/                # Saídas da debate de 9 agentes
│   ├── generated/                 # Documentos gerados (PDFs)
│   ├── bacen_r18_requirements_architecture.md
│   ├── resolucao_conjunta_n18.pdf
│   └── index.md
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

## Devloop local (app)

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

### Sequência canônica

```bash
# 0. (Opcional) Rebuild do frontend se o código Svelte mudou
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist
cd -

# 1. Sobe catálogo, warehouse, schemas, volumes, app, 3 pipelines DLT, 2 dashboards e setup_job.
#    O app já é configurado via `apps.config.env` (USE_MOCK_BACKEND=false, dashboards, warehouse) —
#    nenhum overlay de `app.yaml` é necessário.
export DATABRICKS_BUNDLE_ENGINE=direct
databricks bundle deploy -t dev --profile <seu-profile>

# 2. Seeds: carrega domínios/críticas/calendário BACEN no schema `reference`
#    e copia os XMLs de `sample/` para `landing.scr_xml/{3040,3050}/` para que
#    as pipelines tenham dados para ingerir fim-a-fim de saída.
databricks bundle run setup_reference_tables -t dev --profile <seu-profile>

# 3. Roda as DLT na ordem do medallion
databricks bundle run bronze -t dev --profile <seu-profile>
databricks bundle run silver -t dev --profile <seu-profile>
databricks bundle run gold   -t dev --profile <seu-profile>
```

### Bring-your-own (BYOC) catálogo / warehouse

Para apontar o bundle ao seu próprio catálogo e warehouse em vez dos provisionados:

```bash
databricks bundle deploy -t dev --profile <seu-profile> \
  --var catalog=<nome_catalogo_existente> \
  --var warehouse_id=<id_warehouse_existente>
```

Adicionalmente, comente os blocos em [resources/catalog.yml](resources/catalog.yml) e [resources/warehouse.yml](resources/warehouse.yml) para o bundle não tentar gerenciar o ciclo de vida desses recursos externos.

### Caveats

- **App em "Unavailable" após `bundle destroy` + `bundle deploy`**. O `lifecycle.started: true` do app inicia o compute mas não publica o código no primeiro deploy depois de uma destruição. Recupere com mais um `bundle deploy` (segundo run publica o código) ou rodando `databricks bundle run r18_compliance_app -t dev --profile <seu-profile>` para forçar a publicação.
- **Re-deploy do app é automático**: alterar código em `app/backend/` e rodar `bundle deploy` novamente já republica o container — não é preciso comando separado.
- **Genie Room** não é provisionado pelo bundle. Para habilitar a aba Genie, crie a sala manualmente, pegue o ID e re-adicione `GENIE_SPACE_ID` em `resources/app.yml` ou rode `databricks apps update <app-name> --env GENIE_SPACE_ID=<id>` post-deploy.

---

## Domínio

- **R.18**: resolução conjunta BACEN que exige política formal de qualidade para todo dado reportado ao BCB. 12 dimensões obrigatórias, governança no nível de board. Prazo: 31/12/2026.
- **SCR Doc 3040**: dados detalhados de operações de crédito (130+ campos, IPOC, cessão/FIDC). Submissão em XML.
- **SCR Doc 3050**: dados agregados (TXB/XML, layouts versionados — V11 atual). Periodicidade semanal/mensal seguindo calendário BCB.
- **Equivalência**: mapeamento entre modalidades 3040 ↔ 3050 — exposto no silver como `mod_3050_equiv` para consumo dos dashboards.
- **Críticas**: regras de validação (sintáticas, semânticas e inter-documentais).

Detalhes completos em [docs/spec/](docs/spec/) e [docs/bacen_r18_requirements_architecture.md](docs/bacen_r18_requirements_architecture.md).
