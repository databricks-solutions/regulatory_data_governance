# RC18 StarterKit — Acelerador BACEN Resolução Conjunta nº 18

Starter kit Databricks para conformidade com a **Resolução Conjunta BACEN nº 18** (governança de dados sobre risco de crédito — SCR Doc 3040 e Doc 3050).

Entrega uma aplicação Databricks (FastAPI + Svelte) de monitoramento de qualidade, validação e reconciliação, esqueletos de pipelines DLT para tratamento dos CADOCs (como exemplo os 3040/3050), dashboards no AI/BI e uma sala Genie.

---

## Como usar este repositório

Dois caminhos:

### 1. Implementar o acelerador no seu ambiente

Você usa o repositório como **atalho** para construir sua própria solução de conformidade com a RC18 no seu ambiente Databricks. Estende a app, pluga seus dados reais nos pipelines 3040/3050 (e outros CADOCs), customiza dashboards.

```bash
git clone <repo>
cd regulatory-data-governance
cp .env.example .env             # preencha com IDs do seu workspace
./scripts/deploy.sh              # sobe app + pipelines + dashboards + genie
```

- **Nenhum dado sintético é envolvido.** O bundle na raiz (`databricks.yml`, nome `rc18-starter-kit`) entrega só o framework — nenhum gerador, nenhum loader fictício.
- **Pode deletar `demo/`** sem medo: nada do bundle do acelerador depende daquela pasta.
- Próximos passos: conectar as pipelines às suas fontes (Oracle/DB2/VSAM/etc.), carregar as tabelas de referência BACEN via `notebooks/setup/setup_reference_tables.py`, e adaptar o app à identidade visual/domínio da sua IF.

### 2. Ver o acelerador em ação (modo demo)

Quer experimentar o acelerador fim-a-fim com dados fictícios — Doc 3040 sendo gerado, agregado em 3050, reconciliado e exibido nos dashboards.

```bash
cd demo
databricks bundle deploy -t dev    # sobe acelerador + geradores sintéticos + loader
```

- Bundle `rc18-demo` inclui **todo o acelerador** MAIS os geradores de Doc 3040/3050 e o loader de dados fictícios.
- Ver [demo/README.md](demo/README.md) para parâmetros dos jobs.

---

## Configuração de ambiente

URLs de workspace, IDs de warehouse, dashboards e Genie Space **não são versionados** no repositório — todos vêm de variáveis de ambiente.

1. Copie o template e preencha com os valores do seu workspace:

   ```bash
   cp .env.example .env
   # edite .env com seus IDs reais (host, warehouse, dashboards, Genie)
   ```

2. Onde cada componente lê o `.env`:

   | Componente | Como consome |
   |------------|--------------|
   | Backend (dev local) | `app/backend/main.py` carrega via `python-dotenv` no startup |
   | Backend (Databricks Apps) | [scripts/deploy.sh](scripts/deploy.sh) gera um `app.yaml` runtime a partir do `.env` e faz overlay no path do bundle no workspace — o `app/backend/app.yaml` versionado fica em branco |
   | Bundle DABs | `./scripts/deploy.sh` lê `DATABRICKS_WAREHOUSE_ID` e passa via `--var warehouse_id=...` |
   | Frontend | Não lê `.env` direto — recebe URLs/IDs via API do backend |

3. Variáveis principais (ver [.env.example](.env.example) para a lista completa):

   | Variável | Descrição |
   |----------|-----------|
   | `DATABRICKS_HOST` | Host do workspace (`adb-<id>.<n>.azuredatabricks.net`) — o ID numérico é extraído daqui em runtime |
   | `DATABRICKS_WAREHOUSE_ID` | SQL warehouse usado pela API |
   | `DATABRICKS_CATALOG` | Catálogo Unity (default: `rc18_catalog`) |
   | `DASHBOARD_ID_CONFORMIDADE` / `_CRITICAS` / `_RECONCILIACAO` | IDs Lakeview |
   | `GENIE_SPACE_ID` | ID do Genie Room |
   | `USE_MOCK_BACKEND` | `true` para servir fixtures mock localmente |

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
│   ├── monitor_criticas.lvdash.json
│   └── reconciliacao_executiva.lvdash.json
│
├── resources/                     # DAB resources do acelerador
│   ├── app.yml                    # Databricks App
│   ├── pipelines/                 # DLT pipelines
│   │   ├── bronze.yml
│   │   ├── silver.yml
│   │   └── gold.yml
│   └── analytics/                 # Dashboards + Genie
│       ├── dashboard_conformidade.yml
│       ├── dashboard_criticas.yml
│       ├── dashboard_reconciliacao.yml
│       └── genie_scr.yml
│
├── scripts/                       # Utilitários de dev e deploy
│   ├── deploy.sh                  # Deploy do bundle + app (lê .env, popula app.yaml runtime)
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

## Deploy do acelerador (cliente)

### Pré-requisitos

- `.env` preenchido (ver [Configuração de ambiente](#configuração-de-ambiente))
- `databricks` CLI autenticada com um profile que aponte para o workspace destino
  (default no script: `ssa-latam` — sobreponha com `PROFILE=<seu-profile>`)

### One-liner

```bash
# 1. Build do frontend (apenas se mudou o código Svelte)
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist
cd -

# 2. Deploy fim-a-fim (bundle DABs + app + populate runtime app.yaml a partir do .env)
./scripts/deploy.sh                                    # target=dev, profile=ssa-latam
./scripts/deploy.sh prod                               # outro target
TARGET=dev PROFILE=meu-profile APP_NAME=rc18-staging ./scripts/deploy.sh

# 3. Carregar tabelas de referência BACEN (domínios, críticas, calendário)
databricks bundle run -t dev setup_reference_tables -p ssa-latam   # (após criar o job correspondente)
```

### O que o script faz

1. Carrega `.env` (falha se ausente ou se `DATABRICKS_WAREHOUSE_ID` estiver vazio)
2. `databricks bundle deploy -t <target> -p <profile> --var warehouse_id=$DATABRICKS_WAREHOUSE_ID`
   — sobe app, 3 pipelines DLT (`r18-bronze-ingestion`, `r18-silver-validation`, `r18-gold-reconciliation`), 3 dashboards e Genie Room
3. Gera `app.yaml` runtime com os valores do `.env` (warehouse, dashboards, Genie, schemas) e faz overlay sobre o `app.yaml` em branco que veio no bundle — assim o `app/backend/app.yaml` versionado **nunca** carrega IDs reais
4. `databricks apps deploy rc18-starter-kit` — reinicia o container com a config nova
5. Imprime URL final + estado da app

### Deploy manual (se precisar)

```bash
set -a && . ./.env && set +a
databricks bundle deploy -t dev -p ssa-latam --var "warehouse_id=$DATABRICKS_WAREHOUSE_ID"
```
(Pulando os passos 3–4, a app sobe mas com env vars vazias — dashboards e queries reais não funcionam.)

---

## Domínio

- **R.18**: resolução conjunta BACEN que exige política formal de qualidade para todo dado reportado ao BCB. 12 dimensões obrigatórias, governança no nível de board. Prazo: 31/12/2026.
- **SCR Doc 3040**: dados detalhados de operações de crédito (130+ campos, IPOC, cessão/FIDC). Submissão em XML.
- **SCR Doc 3050**: dados agregados (TXB/XML, layouts versionados — V11 atual). Periodicidade semanal/mensal seguindo calendário BCB.
- **Equivalência**: mapeamento entre modalidades 3040 ↔ 3050 — base da reconciliação.
- **Críticas**: regras de validação (sintáticas, semânticas e inter-documentais).

Detalhes completos em [docs/spec/](docs/spec/) e [docs/bacen_r18_requirements_architecture.md](docs/bacen_r18_requirements_architecture.md).
