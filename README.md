# RC18 StarterKit — Acelerador BACEN Resolução Conjunta nº 18

Starter kit Databricks para conformidade com a **Resolução Conjunta BACEN nº 18** (governança de dados sobre risco de crédito — SCR Doc 3040 e Doc 3050).

Entrega uma aplicação Databricks (FastAPI + Svelte) de monitoramento de qualidade e validação, esqueletos de pipelines DLT para tratamento dos CADOCs (como exemplo os 3040/3050), dashboards no AI/BI e uma sala Genie.

---

## Como usar este repositório

Dois caminhos:

> **Sobre o motor de qualidade (DQX) — leia antes de usar em produção**
>
> A camada de qualidade do RC18 é construída sobre **[Databricks Labs DQX](https://github.com/databrickslabs/dqx)**,
> uma biblioteca **oficial Databricks Labs em estágio pré-1.0** (versão fixada
> aqui: `databricks-labs-dqx==0.14.0`). Bibliotecas Labs são suportadas pela
> comunidade Databricks, **não** entram nos SLAs de produto comerciais e podem
> introduzir mudanças incompatíveis em versões menores.
>
> Por isso este acelerador **fixa explicitamente a versão da DQX** no notebook
> que a invoca ([`notebooks/dqx_tutorial/dqx_basics.py`](notebooks/dqx_tutorial/dqx_basics.py),
> este aviso). Antes de promover para um ambiente produtivo:
>
> 1. Faça fork deste repositório.
> 2. Mantenha a versão fixa congelada — atualize só dentro do seu ciclo de
>    recertificação (ler [CHANGELOG da DQX](https://github.com/databrickslabs/dqx/releases)
>    primeiro).
> 3. As regras DQX vivem em **`dqx.dqx_studio.dq_quality_rules`** e são criadas
>    inteiramente via DQX Studio (Motor de Regras) — o RC18 apenas as LÊ, não faz
>    mais seed automático. **Pré-requisito:** workspace admin precisa rodar
>    [`notebooks/setup/grant_dqx_studio_access.sql`](notebooks/setup/grant_dqx_studio_access.sql)
>    UMA vez para conceder os GRANTs de leitura cross-catalog ao SP do bundle.
>    Customers que deployaram a DQX Studio em outro catálogo/schema ajustam
>    `dqx_catalog`/`dqx_schema` no `target.yml`.
>
> **A DQX Studio é um pré-requisito obrigatório deste acelerador.** Se a sua
> organização optar por outra engine, isso constitui uma customização/fork fora
> do fluxo de deploy documentado aqui.

### 1. Implementar o acelerador no seu ambiente

Você usa o repositório como **atalho** para construir sua própria solução de conformidade com a RC18 no seu ambiente Databricks. Estende a app, pluga seus dados reais nos pipelines 3040/3050 (e outros CADOCs), customiza dashboards.

```bash
git clone <repo>
cd regulatory-data-governance
cp target.yml.example target.yml                             # preencha profile e URL obrigatória da DQX
./bundle.sh deploy                                           # cria todos os recursos do acelerador
./bundle.sh run rc18_end_to_end                              # orquestra setup → bronze → silver → gold
./bundle.sh run r18_compliance_app                           # disponibiliza o app após o deployment
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
| **Deploy do bundle** (Databricks Apps + pipelines) | Usa exclusivamente o `target.yml` local. `bundle.sh` habilita o direct engine e chama o Databricks CLI. O bundle provisiona catálogo, warehouse, schemas e dashboards e injeta os IDs no app via `apps.config.env`. |
| **Dev local** (`./run_local.sh`) | Usa `.env`, carregado via `python-dotenv`. Portanto, `.env.example` continua necessário apenas como template para desenvolvimento local; ele não participa do deploy. |
| **Frontend** | Não lê `.env` direto — recebe URLs/IDs via API do backend. |

Variáveis relevantes (ver [.env.example](.env.example) para a lista completa):

| Variável | Descrição |
|----------|-----------|
| `DATABRICKS_HOST` | Host do workspace (`adb-<id>.<n>.azuredatabricks.net`) — apenas para dev local contra workspace real |
| `DATABRICKS_WAREHOUSE_ID` | Warehouse existente; vazio usa o warehouse provisionado pelo bundle |
| `DATABRICKS_CATALOG` | Catálogo usado pelo app e pelo target gerado |
| `DQX_STUDIO_URL` | URL pública obrigatória da DQX Studio para usar o app local completo |
| `DQX_CHECKS_TABLE` | FQN da tabela de regras da DQX Studio |
| `DASHBOARD_ID_CONFORMIDADE` / `_CRITICAS` | Apenas para dev local; em deploy o bundle resolve via `${resources.dashboards.*.id}` |
| `GENIE_SPACE_ID` | Apenas para dev local; em deploy o bundle provisiona o Genie Space e resolve via `${resources.genie_spaces.rc18_genie.id}` |
| `USE_MOCK_BACKEND` | `true` no dev para servir fixtures sem Databricks |

---

## Estrutura do repositório

```
regulatory-data-governance/
│
├── databricks.yml                 # Bundle do ACELERADOR (rc18-starter-kit)
├── target.yml.example             # Template do único target (obrigatórios/opcionais)
├── target.yml                     # Configuração local de deploy, ignorada pelo Git
├── bundle.sh                      # Habilita direct engine e executa `databricks bundle ...`
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
│   ├── analytics/                 # Dashboards
│   │   ├── dashboard_conformidade.yml
│   │   └── dashboard_criticas.yml
│   └── rc18_genie.genie_space.yml # Genie Space (serialized_space inline, ${var.catalog})
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
| NL Queries | Genie Space | `resources/rc18_genie.genie_space.yml` |
| Deployment | Databricks Asset Bundles | `databricks.yml` + `resources/**` |
| Dados | Unity Catalog (catálogo parametrizável via `${var.catalog}`) | — |

---

## Pré-requisitos

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) autenticada
- Python 3.11+ (backend)
- Node.js 18+ e npm (frontend)
- **[DQX Studio](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation) deployada no workspace destino** — provê a camada de qualidade (autoria/execução de regras) e cria a tabela `dqx.dqx_studio.dq_quality_rules` que o acelerador consome. Ver [Camada de qualidade (DQX Studio)](#camada-de-qualidade-dqx-studio) abaixo.

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
- `target.yml` criado a partir de `target.yml.example`; `bundle.sh` configura automaticamente o direct deployment engine exigido pelo recurso `catalogs:`
- **DQX Studio é requisito obrigatório e deve estar deployada no mesmo workspace** (ver [Camada de qualidade (DQX Studio)](#camada-de-qualidade-dqx-studio)). A URL pública é obrigatória no `target.yml`. Sem a Studio, o acelerador está incompleto: o app não consegue ler a tabela de regras e a página Críticas SCR fica vazia.

### Target único

O bundle possui somente um target, definido no `target.yml` ignorado pelo Git:

```bash
cp target.yml.example target.yml
# O target já é fixo como `dev`; preencha os dois campos obrigatórios:
#   <your-databricks-cli-profile>
#   https://<your-dqx-studio-app-host>
./bundle.sh validate
```

O target `dev` é marcado como default. Cloud e workspace são definidos
exclusivamente pelo `workspace.profile`; nenhum comando precisa de `-t`,
`--profile`, `--var` ou exports.

Campos opcionais:

- `warehouse_id`: omitido, o bundle cria e usa automaticamente um warehouse
  Serverless 2X-Small; preenchido, aponta para um warehouse existente.
- `catalog`: omitido, o bundle cria e gerencia `rc18_catalog`; preenchido,
  aponta para um catálogo existente.
- `dqx_checks_table`: omitido, usa
  `dqx.dqx_studio.dq_quality_rules`.
- schemas (`schema_bronze`/`silver`/`gold`) e vínculo DQX (`dqx_catalog`/`dqx_schema`): possuem defaults.
- Genie Space: provisionado pelo bundle (`resources/rc18_genie.genie_space.yml`); o app recebe o ID via resource, sem parametrização manual.

Ao usar catálogo ou warehouse existentes, comente também o recurso correspondente
em `resources/catalog.yml` ou `resources/warehouse.yml`; caso contrário o bundle
ainda criará um recurso gerenciado duplicado, mesmo que o app use o ID informado.

> **Troca de workspace.** Como existe apenas um target, primeiro execute
> `./bundle.sh destroy` usando o `target.yml` atual. Somente depois altere o
> `workspace.profile`. Reutilizar o estado de `dev` em outro workspace pode deixar
> recursos órfãos.

### Passo a passo

```bash
# 0. (Opcional) Rebuild do frontend se o código Svelte mudou
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist
cd -

# 1. Sobe catálogo, warehouse, schemas, volumes, app, 3 pipelines DLT, 2 dashboards,
#    setup_job e o job de orquestração rc18_end_to_end.
#    O app já é configurado via `apps.config.env` (USE_MOCK_BACKEND=false, dashboards, warehouse) —
#    nenhum overlay de `app.yaml` é necessário.
./bundle.sh deploy

# 2a. Atalho: orquestração fim-a-fim (setup_reference → load_sample_xmls → bronze → silver → gold).
#     Roda tudo em um único job com dependências encadeadas.
./bundle.sh run rc18_end_to_end

# 2b. Alternativa: disparar cada etapa manualmente (útil para reprocessar uma camada).
./bundle.sh run setup_reference_tables   # seeds reference + carrega XMLs de exemplo
./bundle.sh run bronze
./bundle.sh run silver
./bundle.sh run gold
```

### Disponibilizando o app após o deployment

Publica o código no compute e deixa o app acessível:

```bash
./bundle.sh run r18_compliance_app
```

### Aprovar o domínio do app (obrigatório para dashboards e Genie)

O app RC18 embarca via `iframe` os **dashboards Lakeview** (`/dashboards`) e a
**sala Genie** (`/genie`). Por padrão, o Databricks bloqueia esses iframes quando
carregados a partir de um domínio de Databricks Apps — as páginas aparecem em
branco (ou com erro de _refused to connect_ / `X-Frame-Options`) até que o
domínio do app seja adicionado à allowlist do workspace.

Após o deploy, um **admin do workspace** precisa registrar a URL do app deployado
em **Settings → Security → Approved domains** (allowlist de domínios para
embedding de iframe). O passo é feito **uma vez por workspace** (e refeito se a
URL do app mudar):

1. Copie a URL do app:
   ```bash
   databricks apps get r18_compliance_app --profile <seu-profile> \
     | grep -i "url"
   # ex.: https://rc18-starter-kit-dev-<workspace-id>.<region>.databricksapps.com
   ```
2. No workspace, vá em **Settings → Security → Approved domains** e adicione o
   host do app (ex.: `rc18-starter-kit-dev-<workspace-id>.<region>.databricksapps.com`).
3. Salve. Recarregue as páginas `/dashboards` e `/genie` do app — os iframes
   passam a carregar.

> Sem este passo, o restante do app (Visão Geral, Críticas SCR, `/rules` com a DQX
> Studio) funciona normalmente; apenas os embeds de dashboard Lakeview e Genie
> ficam bloqueados. A DQX Studio embarcada em `/rules` também é um app Databricks —
> se ela também aparecer em branco, adicione o domínio dela à mesma allowlist.

### Bring-your-own (BYOC) catálogo / warehouse

Para apontar o bundle ao seu próprio catálogo e warehouse em vez dos provisionados,
descomente os valores no `target.yml`:

```yaml
variables:
  catalog: <nome_catalogo_existente>
  warehouse_id: <id_warehouse_existente>
```

Adicionalmente, comente os blocos em [resources/catalog.yml](resources/catalog.yml) e [resources/warehouse.yml](resources/warehouse.yml) para o bundle não tentar gerenciar o ciclo de vida desses recursos externos.

---

## Camada de qualidade (DQX Studio)

A camada de qualidade do acelerador (autoria e execução de regras) é obrigatoriamente delegada à
**[DQX Studio](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation)**,
um app externo do [Databricks Labs DQX](https://github.com/databrickslabs/dqx).
O acelerador **não** provisiona a DQX Studio — ela precisa estar deployada **no
mesmo workspace destino**, porque cria e é dona da tabela de regras
`dqx.dqx_studio.dq_quality_rules` que o acelerador consome (página `/rules` do
app + catálogo de Críticas SCR). As regras são autoradas na própria Studio; o
RC18 apenas as LÊ.

> **Por que é um pré-requisito.** O `bundle deploy` e os pipelines
> bronze→silver→gold (ELT puro) **não** dependem da DQX. Mas o app (Críticas SCR,
> KPIs de qualidade, validações) e o task `grant_warehouse_perms` do job
> `rc18_end_to_end` leem `dqx.dqx_studio.dq_quality_rules` e suas tabelas de
> execução. Sem a DQX Studio deployada, essas leituras retornam vazio e o task de
> grant falha com `CATALOG_DOES_NOT_EXIST` / `TABLE_OR_VIEW_NOT_FOUND` (os demais
> tasks concluem normalmente).

### Instalação (resumo)

Siga o [guia oficial de instalação da DQX Studio](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation). Em linhas gerais:

```bash
git clone https://github.com/databrickslabs/dqx.git
cd dqx
# Edite app/databricks.yml com catalog_name, dqx_service_principal_application_id
# e sql_warehouse_id (ver o guia), então:
make app-deploy PROFILE=<seu-profile> TARGET=<seu-target>
```

Pré-requisitos da própria DQX Studio: Databricks CLI v0.268+, `jq`, `make`, `uv`,
Node.js 18+, `yarn`, Databricks Apps + serverless habilitados, um Unity Catalog
existente e um SQL warehouse. Consulte o guia para a lista completa e atualizada.

### Depois de instalar

1. **Conceda os grants de leitura cross-catalog (uma vez, como admin do `dqx`):**
   rode [`notebooks/setup/grant_dqx_studio_access.sql`](notebooks/setup/grant_dqx_studio_access.sql),
   preenchendo o service principal do bundle RC18. Isso libera o app RC18 a LER a
   tabela de regras (e as tabelas de execução) da DQX Studio.
2. **Obrigatório — configure a URL pública no `target.yml`:**
   ```yaml
   variables:
     dqx_studio_url: https://<your-dqx-studio-app-host>
   ```
3. **Opcional — somente se a Studio usa outro catálogo/schema:** parametrize o
   catálogo (e, se necessário, o schema) de vínculo no mesmo arquivo. O FQN da
   tabela de regras é montado como `${dqx_catalog}.${dqx_schema}.dq_quality_rules`:
   ```yaml
   variables:
     dqx_catalog: <your-dqx-catalog>   # default: dqx
     dqx_schema: <your-dqx-schema>     # default: dqx_studio
   ```
   Se o nome da tabela divergir do padrão `dq_quality_rules`, sobrescreva o FQN
   completo com `dqx_checks_table: <catalog>.<schema>.<table>`.

### Destroy e recursos órfãos

O target é sempre `dev` e o profile vem do `target.yml`; não são necessários argumentos adicionais:

```bash
./bundle.sh destroy
```

Se um workspace já tiver recursos órfãos de uma configuração anterior, remova o
app diretamente pelo nome exibido em `databricks apps list`:

```bash
databricks apps list --profile <profile-original>
databricks apps delete <nome-do-app-órfão> --profile <profile-original>
```

---
