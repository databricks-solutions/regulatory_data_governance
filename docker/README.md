# App RC18 em Docker

Roda o app RC18 (o FastAPI e a SPA) num único container, no lugar do Databricks
Apps — num Docker local (Colima, Docker Desktop) ou numa plataforma de
containers.

> O container não é standalone: usa um workspace Databricks (SQL warehouse, Unity
> Catalog, DQX Studio) e se autentica como um service principal (SP). Catálogo,
> pipelines e dashboards continuam no bundle; só o App sai dele.

## Pré-requisitos

- Docker com Compose v2.24+ e `python3`. Com Colima: `colima start`.
- DQX Studio deployada no workspace.
- Um perfil do Databricks CLI da sua identidade (`<seu-perfil>` abaixo), que
  possa fazer `bundle deploy`, seja owner do warehouse e conceda nos catálogos do
  RC18 e da DQX Studio.

## Setup

Rode tudo da raiz do repositório, com o seu perfil.

1. **Crie o service principal do container:**

   ```bash
   databricks service-principals create --display-name rc18-container -p <seu-perfil> -o json
   ```

2. **Crie um OAuth secret para ele.** `<id>` é o `id` numérico do passo 1, e o
   secret só é mostrado uma vez.

   ```bash
   databricks service-principal-secrets-proxy create <id> -p <seu-perfil> -o json
   ```

3. **Preencha o `docker/.env` e o `target.yml`.** No `docker/.env`, copiado do
   template, defina `DATABRICKS_CLIENT_ID` (o `applicationId` do SP) e
   `DATABRICKS_CLIENT_SECRET`; ele é git-ignored e nunca entra na imagem. No
   `target.yml`, crie um target com `app_hosting: container` e `dqx_studio_url`
   (recomendado também `dqx_studio_sp`), e comente `- resources/app/*.yml` no
   `include:` do `databricks.yml`. Os comentários dos arquivos explicam cada
   valor.

   ```bash
   cp docker/.env.example docker/.env
   ```

   ⚠️ A linha do `include:` vale para todos os targets do repositório: num
   deployment que já tem o Databricks App, o próximo `bundle deploy` o **apaga**.

4. **Crie os recursos e conceda as permissões:**

   ```bash
   ./docker/setup.sh -t <target> --no-up
   ```

5. **Suba** e abra <http://localhost:8010>. O diagnóstico do app mostra o que
   ainda faltar. A primeira vez também builda a imagem.

   ```bash
   docker compose -f docker/compose.yaml up
   ```

O script pode ser reexecutado e lista o que não conseguiu fazer. Ele faz o mesmo
`bundle deploy` do fluxo com o Databricks App (catálogo, warehouse, jobs,
dashboards), menos o App, e gera o `docker/.env.bundle` com a configuração do app
resolvida do `target.yml` (não edite). Sem `--no-up`, ele mesmo sobe o container.
Depois concede ao SP:

| Recurso | SP do container |
|---|---|
| Workspace | entitlements `workspace-access`, `databricks-sql-access` |
| SQL warehouse | `CAN_USE` |
| Execuções da DQX Studio (`dqx_catalog`.`dqx_schema`) | `USE CATALOG`, `USE SCHEMA`; `SELECT` em `dq_validation_runs`, `dq_metrics`, `dq_quarantine_records` |
| Catálogo do RC18 | `USE CATALOG`; `USE SCHEMA` + `SELECT` em `bronze`, `silver`, `gold`, `reference` |
| `governance` | `USE SCHEMA`; `SELECT` + `MODIFY` nas tabelas que o app grava (incidentes e vínculos) |
| Metastore (só com `--byol`) | `CREATE EXTERNAL METADATA`; `MODIFY` em `bronze` e `gold` |

O setup não roda o pipeline, e as tabelas de `governance` só existem depois dele
— até lá ficam como `PENDENTE`. Rode o job e conceda o que faltou:

```bash
databricks bundle run rc18_end_to_end -t <target>
./docker/grant_sp.sh -p <seu-perfil>
```

No modo container, o task `grant_warehouse_perms` do job aplica só o grant
reverso (SP da DQX Studio); os grants do SP do container vêm do
[`grant_sp.sh`](grant_sp.sh).

### DQX Studio também em Docker

A Studio em Docker usa dois SPs (os IDs estão no `.env` dela), e os dois
precisam de acesso ao catálogo do RC18. Sem OBO no container, é o SP do app que
cria a view temporária de cada execução, então ele também precisa ler os dados:

| SP da Studio | Para quê | O que conceder |
|---|---|---|
| App (`DATABRICKS_CLIENT_ID`) | listar tabelas, profiling e criar a view temporária da execução | `USE CATALOG` no catálogo; `USE SCHEMA` + `SELECT` em `silver`, `gold`, `reference` (SQL abaixo) |
| Task runner (`DQX_TASK_RUNNER_CLIENT_ID`) | executar as validações | entitlement `workspace-access` (comando abaixo); e `dqx_studio_sp: <application-id-dele>` no `target.yml` — o `rc18_end_to_end` concede o resto |

```sql
GRANT USE CATALOG ON CATALOG <catalogo> TO `<sp-app-da-studio>`;
GRANT USE SCHEMA, SELECT ON SCHEMA <catalogo>.silver    TO `<sp-app-da-studio>`;
GRANT USE SCHEMA, SELECT ON SCHEMA <catalogo>.gold      TO `<sp-app-da-studio>`;
GRANT USE SCHEMA, SELECT ON SCHEMA <catalogo>.reference TO `<sp-app-da-studio>`;
```

```bash
# <id> é o id numérico do SP do runner, não o application id.
databricks service-principals list -p <seu-perfil> \
  --filter 'applicationId eq "<application-id-do-runner>"' -o json | jq -r '.[0].id'
databricks service-principals patch <id> -p <seu-perfil> --json \
  '{"schemas":["urn:ietf:params:scim:api:messages:2.0:PatchOp"],"Operations":[{"op":"add","path":"entitlements","value":[{"value":"workspace-access"}]}]}'
```

Sintoma de cada falta:

- SP do app sem os GRANTs: *User does not have USE CATALOG on Catalog
  '<catalogo>'* ao criar a `tmp_view_*`.
- Runner sem `workspace-access`: *The user <application-id> does not have access
  to Databricks Workspace*.
- Sem o `dqx_studio_sp`: os checks com subquery marcam 100% de violação.

## Autenticação

O container atende **toda requisição como o SP**: não há o login por usuário que
o Databricks Apps faz. O app grava como autor de incidentes e vínculos os headers
`X-Forwarded-Email`/`-User`/`-Preferred-Username`, que lá vêm do SSO da
plataforma e aqui qualquer cliente escolhe. Por isso o compose publica só em
`127.0.0.1`.

Antes de expor além de uma rede confiável, ponha um proxy com autenticação na
frente (ex.: oauth2-proxy, com o Databricks como provedor OIDC), que defina esses
headers e descarte os que o cliente mandar. Guarde o `DATABRICKS_CLIENT_SECRET`
no secret manager da plataforma.

## Uso diário

- App: <http://localhost:8010> · API: <http://localhost:8010/api/docs> ·
  diagnóstico: <http://localhost:8010/api/v1/diagnostics/prereqs>
- Logs: `docker compose -f docker/compose.yaml logs -f` · parar:
  `docker compose -f docker/compose.yaml down`
- Mudança de configuração: edite o `target.yml` e rode o setup de novo. Mudança de
  código: `docker compose -f docker/compose.yaml up -d --build`.

Sem Compose, da raiz do repositório:

```bash
docker build -f docker/Dockerfile -t rc18-app app
docker run --rm -p 127.0.0.1:8010:8000 --env-file docker/.env --env-file docker/.env.bundle rc18-app
```

## Remover

O inverso do setup — o equivalente ao `databricks bundle destroy`:

```bash
./docker/destroy.sh -t <target>                     # compose down + bundle destroy + apaga .env.bundle
./docker/destroy.sh -t <target> --revoke-grants     # + revoga os grants na DQX Studio
```

- Só aceita target com `app_hosting: container`; para os demais, `databricks bundle destroy`.
- O `bundle destroy` apaga o catálogo do target **com os dados**, além de warehouse, jobs e dashboards.
- `--revoke-grants` só se o SP não servir a outro deployment: os grants na DQX Studio são por SP, não por target.
- Ficam de fora o `docker/.env`, a imagem `rc18-app:local` e a linhagem externa (`rc18_*`, do metastore — CLAUDE.md, seção Lineage).

## Deploy no Azure Kubernetes Service

Exige Azure CLI (`az login`) e `kubectl`. Rode o [Setup](#setup) até o passo 4.

```bash
./docker/deploy_aks.sh -g <rg> -r <nome-do-acr> -l <região> --dry-run   # prévia
./docker/deploy_aks.sh -g <rg> -r <nome-do-acr> -l <região>
```

O script cria o que faltar (resource group, registry, cluster AKS), builda a
imagem no ACR, guarda `docker/.env` + `docker/.env.bundle` num Secret do
Kubernetes e roda uma réplica. Rode de novo para publicar código ou configuração.

- **Região:** use a do workspace.
- **Acesso:** o Service é `ClusterIP`, nada fica exposto. Abra o app com:

  ```bash
  az aks get-credentials -g <rg> -n rc18
  kubectl -n rc18 port-forward svc/rc18-app 8010:8000
  ```

- **Cluster:** `-c dqx-studio` usa o cluster da DQX Studio.
- **API server:** só `--api-server-ip-ranges` o alcança (default: seu IP público); mudou de IP, rode de novo.
- **Build:** sobe só o que o git não ignora em `app/` — nenhum `.env`. Sem ACR Tasks, use `--local-build` ou `--image`.

## Notas

- **Embeds de dashboard e Genie:** o host do container precisa estar em Approved
  domains ([Aprovar o domínio do app](../README.md#aprovar-o-domínio-do-app)), e o
  navegador precisa de sessão ativa no workspace. O embed da DQX Studio em
  `/rules` não é tratado por este modo.
- **Branding** (logo/tema) fica no filesystem do container e some ao recriá-lo,
  como no Databricks Apps.
- **Porta:** o default no host é 8010, para não colidir com a DQX Studio local (8000). Ocupada? `RC18_PORT=<outra>` no `docker/.env`.
- **Rede sem PyPI/npm públicos:** `PIP_INDEX_URL` e `NPM_CONFIG_REGISTRY` no
  `docker/.env`; o compose os repassa ao build (sem Compose:
  `--build-arg`).
- **Colima via Homebrew** (`unknown shorthand flag: 'f'`): registre o plugin
  Compose com `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]`
  no `~/.docker/config.json`.
- **Apple Silicon** builda `arm64` nativo; para servidor x86,
  `--platform linux/amd64`.
