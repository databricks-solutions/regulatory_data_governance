# RC18 Starter Kit — Acelerador BACEN Resolução Conjunta nº 18

Starter kit Databricks para conformidade com a **Resolução Conjunta BACEN nº 18** — governança de dados de risco de crédito (com exemplos de arquivos sintéticos dos CADOCs 3040 e 3050).

Você usa este repositório como **atalho** para construir a sua **própria plataforma de conformidade RC18**: faz o deploy no seu workspace, pluga seus dados reais e customiza app e dashboards.

O que o deploy entrega:

- **App** de monitoramento de qualidade e validação (FastAPI + Svelte)
- **Pipelines DLT** medallion (bronze → silver → gold) de exemplo para os CADOCs 3040/3050
- **Dashboards** com AI/BI
- **Catálogo, warehouse e schemas** no Unity Catalog
- **Sala Genie** (NL→SQL) — opcional, via bundle separado

---

## Início rápido

```bash
git clone <repo>
cd regulatory-data-governance

cp target.yml.example target.yml      # preencha: profile do CLI + URL da DQX Studio
databricks bundle deploy              # cria todos os recursos do acelerador
databricks bundle run rc18_end_to_end # setup → bronze → silver → gold
databricks bundle run r18_compliance_app  # disponibiliza o app
```

O deploy já sobe com dois arquivos de exemplo (Doc 3040 e Doc 3050 em [`sample/`](sample/)), gerados sinteticamente e validados com o Validador Oficial do BACEN. Substitua-os pelos seus dados reais quando estiver pronto.

> Precisa reprocessar uma camada isoladamente? Veja [Rodar passo a passo](#rodar-passo-a-passo).

---

## Pré-requisitos

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) autenticada, com um profile apontando para o workspace destino
- Python 3.11+ (backend) e Node.js 18+ (frontend) — apenas para dev local
- **[DQX Studio](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation) deployment da aplicação no mesmo workspace** — provê a camada de qualidade e é utilizado como **Motor de Regras** do acelerador. **IMPORTANTE**: É pré-requisito obrigatório (ver [Camada de qualidade](#camada-de-qualidade-dqx-studio)).

---

## Configuração (`target.yml`)

O bundle tem um único target, fixo como `dev`, configurado no `target.yml` (ignorado pelo Git). Cloud e workspace vêm do `workspace.profile`.

**Obrigatório:**

```yaml
targets:
  dev:
    default: true
    workspace:
      profile: <seu-profile-do-cli>
    variables:
      dqx_studio_url: https://<host-da-sua-dqx-studio>
```

**Opcional** (todos têm default — ver comentários em [`target.yml.example`](target.yml.example)):

| Variável | Default | Para quê |
|----------|---------|----------|
| `catalog` | cria `rc18_catalog` | Apontar para um catálogo existente ([BYOC](#trazer-catálogo--warehouse-próprios-byoc)) |
| `warehouse_id` | cria warehouse Serverless 2X-Small | Apontar para um warehouse existente |
| `schema_bronze` / `_silver` / `_gold` | `bronze` / `silver` / `gold` | Renomear schemas |
| `dqx_catalog` / `dqx_schema` | `dqx` / `dqx_studio` | Se a DQX Studio estiver em outro catálogo/schema |
| `genie_space_id` | `__unset__` (desativado) | Ativar a sala Genie (ver [Genie Space](#sala-genie-opcional)) |

---

## Dev local (app)

```bash
./run_local.sh    # backend :8000 + frontend :5173 com dados mock
```

Abra http://localhost:5173. O dev local usa `.env` (copie de [`.env.example`](.env.example)), separado do deploy. Com `USE_MOCK_BACKEND=true` o app roda sem conexão com o Databricks.

---

## Camada de qualidade (DQX Studio)

A autoria e execução de regras de qualidade são delegadas ao
**[DQX Studio](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation)**,
um app do [Databricks Labs DQX](https://github.com/databrickslabs/dqx). O acelerador **NÃO** provisiona a Studio — ela precisa estar deployada no mesmo workspace, pois é responsável por popular a tabela de regras `dqx.dqx_studio.dq_quality_rules` que o app lê (página `/rules` + Críticas). As regras são criadas no próprio Studio; o RC18 apenas as **lê**.

Depois de instalar a Studio ([guia oficial](https://databrickslabs.github.io/dqx/docs/installation/#dqx-studio-installation)):

1. **Conceda os grants de leitura (uma vez, como admin do catálogo `dqx`):** rode [`notebooks/setup/grant_dqx_studio_access.sql`](notebooks/setup/grant_dqx_studio_access.sql), preenchendo o service principal do bundle RC18.
2. **Informe a URL no `target.yml`:** `dqx_studio_url: https://<host-da-studio>` (obrigatório).
3. **Se a Studio usa outro catálogo/schema:** ajuste `dqx_catalog` / `dqx_schema`.

> Os pipelines bronze→silver→gold são ELT puro e **não** dependem da DQX. Mas sem a Studio, o app não consegue ler as regras: a página Críticas SCR fica vazia e o task de grant do `rc18_end_to_end` falha (os demais concluem normalmente).

> **Versão fixada.** A DQX é uma biblioteca Databricks Labs pré-1.0 (fixada aqui em `databricks-labs-dqx==0.14.0`). Antes de promover para produção, faça fork, mantenha a versão congelada e só atualize dentro do seu ciclo de recertificação, lendo o [CHANGELOG](https://github.com/databrickslabs/dqx/releases) primeiro.

---

## Aprovar o domínio do app

O app embarca via `iframe` os **dashboards Lakeview** (`/dashboards`), a **sala Genie** (`/genie`) e a **DQX Studio** (`/rules`). O Databricks bloqueia esses iframes até que o domínio do app entre na allowlist do workspace — as páginas aparecem em branco (erro `X-Frame-Options`).

Após o deploy, um **admin do workspace** faz isto **uma vez**:

1. Pegue a URL do app: `databricks apps get r18_compliance_app | grep -i url`
   (ex.: `rc18-starter-kit-dev-<id>.<region>.databricksapps.com`)
2. Adicione esse host em **Settings → Security → Approved domains**.
3. Recarregue `/dashboards` e `/genie` — os iframes passam a carregar.

> Sem esse passo o resto do app funciona normalmente; apenas os embeds ficam bloqueados.

---

## Sala Genie (opcional)

A sala Genie (NL→SQL sobre os dados R.18) utiliza um **bundle separado** em [`genie/`](genie/README.md), fora do deploy principal — a API do Genie valida na criação que todas as tabelas já existem, o que só ocorre depois de `rc18_end_to_end` rodar. Por isso o deploy principal sobe sem Genie e o app mostra um placeholder "disponível após deploy".

Para ativar (com o core no ar e as tabelas criadas):

```bash
cp genie/target.yml.example genie/target.yml   # profile + warehouse_id
cd genie && databricks bundle deploy            # cria a sala Genie
databricks genie list-spaces --profile <profile>   # copie o space_id

# volte ao core, defina genie_space_id no target.yml e redeploy
cd .. && databricks bundle deploy
```

Runbook completo em [`genie/README.md`](genie/README.md).

---

## Rodar passo a passo

O atalho `rc18_end_to_end` roda tudo encadeado. Para reprocessar uma camada isolada:

```bash
databricks bundle run setup_reference_tables   # seeds reference + carrega XMLs de exemplo
databricks bundle run bronze                    # ingere os XMLs
databricks bundle run silver                    # bronze → silver
databricks bundle run gold                      # posições curadas
```

Se o código Svelte mudou, rebuilde o frontend antes do deploy:

```bash
cd app/frontend && npm run build && rm -rf ../backend/frontend_dist && cp -r build ../backend/frontend_dist
```

---

## Operações avançadas

### Trazer catálogo / warehouse próprios (BYOC)

Para usar um catálogo e warehouse existentes em vez dos provisionados, defina-os no `target.yml`:

```yaml
variables:
  catalog: <catálogo-existente>
  warehouse_id: <id-do-warehouse-existente>
```

E **comente** os blocos em [`resources/catalog.yml`](resources/catalog.yml) / [`resources/warehouse.yml`](resources/warehouse.yml), senão o bundle cria recursos gerenciados duplicados.

### Destroy e troca de workspace

```bash
databricks bundle destroy
```

Como existe só um target, para mudar de workspace faça `destroy` **antes** de alterar o `workspace.profile` — reutilizar o estado do `dev` em outro workspace pode deixar recursos órfãos. Se sobrar um app órfão, remova-o direto:

```bash
databricks apps list --profile <profile>
databricks apps delete <nome-do-app> --profile <profile>
```

---

## Modo demo (uso interno Databricks)

> Este modo é voltado ao time Databricks para demonstrações. Clientes usando o repositório como base podem **ignorar ou deletar `demo/`** — nada no acelerador depende dele.

O bundle `rc18-demo` sobe o app em **modo mock** mais **geradores sintéticos** de XML (Doc 3040 e 3050, validados com os binários oficiais do BCB) e um loader de dados fictícios. É autocontido: não inclui os pipelines DLT, dashboards nem o setup do acelerador.

```bash
cd demo
databricks bundle deploy -t dev-azure
databricks bundle run scr3040_generator     -t dev-azure   # gera Doc 3040
databricks bundle run scr3050_generator     -t dev-azure   # gera Doc 3050 (a partir do 3040)
databricks bundle run synthetic_data_loader -t dev-azure   # popula bronze com dados fictícios
```

Targets, parâmetros dos jobs e teardown em [`demo/README.md`](demo/README.md).

---

## Estrutura do repositório

```
regulatory-data-governance/
├── databricks.yml            # Bundle do acelerador (rc18-starter-kit)
├── target.yml(.example)      # Config local de deploy (target.yml é ignorado pelo Git)
├── app/                      # Aplicação
│   ├── backend/              # API FastAPI servida pelo Databricks Apps
│   └── frontend/             # Código-fonte SvelteKit 5
├── pipelines/                # Pipelines DLT (bronze → silver → gold)
├── notebooks/setup/          # Setup de reference tables, grants e lineage
├── dashboards/               # Definições Lakeview (AI/BI)
├── resources/                # DAB resources (app, catálogo, warehouse, jobs, pipelines)
├── sample/                   # XMLs de exemplo (Doc 3040/3050) carregados no deploy
├── genie/                    # Bundle opt-in da sala Genie (rc18-genie)
└── demo/                     # Modo demo — uso interno Databricks
```

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Frontend | SvelteKit 5, Svelte Flow, LayerCake, d3 |
| Backend | FastAPI, Pydantic v2, databricks-sdk |
| Pipelines | DLT/SDP (ELT puro) |
| Qualidade | DQX Studio (app externo, embarcado via iframe) |
| Dashboards | Lakeview (AI/BI) |
| NL Queries | Genie Space (bundle opt-in) |
| Deployment | Databricks Asset Bundles |
| Dados | Unity Catalog (catálogo parametrizável via `${var.catalog}`) |
</content>
</invoke>
