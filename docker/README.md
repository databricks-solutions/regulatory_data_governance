# App RC18 em container (Docker)

Roda o app (FastAPI + SPA) numa imagem Docker, no lugar do Databricks Apps. Catálogo, pipelines e dashboards continuam no bundle; a DQX Studio segue como app Databricks à parte.

## Quick start

Pré-requisitos: DQX Studio deployada no workspace, Databricks CLI autenticada num perfil, Docker com Compose v2.24+, `python3` e `psql`.

1. **Worktree só para o container** — a linha do App no `include:` (passo 3) vale para **todos** os targets da cópia, e um deploy de target com Databricks App a partir dela apagaria o App. Separe:
   ```bash
   git worktree add --detach ../rc18-container <branch>   # --detach: a branch já está ativa no repo principal
   cd ../rc18-container
   ```
   O estado do bundle é por target, então este worktree e o repo principal deployam no mesmo workspace sem conflito. Para atualizar o código: `git checkout --detach <branch>` no worktree. Num repo que só roda em container, pule este passo.
2. **`target.yml`** — `cp target.yml.example target.yml` (o `target.yml` é git-ignored, não vem no worktree). Deixe nele **só** os targets de container — com um target de Databricks App aqui, um `bundle deploy` sem `-t` o apagaria:
   ```yaml
   targets:
     container:
       default: true
       workspace:
         profile: <perfil-do-cli>
       variables:
         dqx_studio_url: https://<host-da-dqx-studio>
         app_hosting: container
         # Recomendado: SP da DQX Studio (run_as dos jobs de validação). Sem ele, os
         # checks com subquery dão 100% de violação em silêncio.
         # dqx_studio_sp: <uuid-do-sp-da-dqx-studio>
         # Só se a Studio não usar os defaults (dqx / dqx_studio):
         # dqx_catalog: <catalogo-da-dqx>
         # dqx_schema: <schema-da-dqx>
   ```
   Catálogo, Lakebase, Genie e módulos ocultos seguem as demais opções do `target.yml.example`, iguais às do fluxo com o Databricks App. Com vários deployments no mesmo workspace, dê ao target do container um `catalog` próprio — é o catálogo que os separa.
3. **`databricks.yml`** — comente a linha do App no `include:`:
   ```yaml
     # - resources/app/*.yml
   ```
   ⚠️ Num target que já tem o Databricks App, o próximo deploy o **apaga** (e o SP dele).
4. **SP do container** — Settings → Identity and access → Service principals: crie um e gere um OAuth secret com scope `all-apis`.
5. **`docker/.env`** — `cp docker/.env.example docker/.env` e preencha `DATABRICKS_CLIENT_ID` (o *Application ID*) e `DATABRICKS_CLIENT_SECRET`.
6. **Setup** — da raiz do worktree:
   ```bash
   ./docker/setup.sh -t container
   ```
   O perfil do CLI vem do `workspace.profile` do target; sem `-t`, vale o target default.
   Faz deploy, gera o `docker/.env.bundle`, concede os grants e sobe o container. Abra http://localhost:8000.
7. **Pipeline** — o setup só cria os recursos; rode o job e, ao fim, os grants das tabelas que ele cria:
   ```bash
   databricks bundle run rc18_end_to_end -t container
   ./docker/grant_sp.sh -p <perfil-do-cli>
   ```
   Até lá, o setup marca como `PENDENTE` os grants em `governance.*` (incidentes e vínculos), que só existem depois do job.

## Setup em detalhe

O `./docker/setup.sh` faz o mesmo `bundle deploy` do fluxo com o Databricks App — catálogo, warehouse, jobs, dashboards —, menos o App, e configura o container. A configuração do app tem **uma fonte só, o `target.yml`**: o setup gera `docker/.env.bundle` a partir do bundle, e o `docker/.env` guarda só o que é do container.

| Arquivo | Quem escreve | Conteúdo |
|---|---|---|
| `target.yml` | você | perfil, catálogo, DQX Studio (`dqx_studio_url`, `dqx_catalog`…), Lakebase, Genie |
| `docker/.env` | você | SP do container, porta, mirrors |
| `docker/.env.bundle` | o setup (não edite) | a config do app, resolvida do bloco `env` de `resources/app/app.yml` + `bundle summary` |

`app_hosting: container` e a linha comentada no `include:` andam juntas: o setup recusa rodar com só uma das duas.

O espelho UC do Lakebase (`resources/postgres_catalogs.yml`, usado pelos dashboards) é um por database: se outro deployment já o registrou, o setup deixa o arquivo de fora do deploy deste target e usa o existente. O `docker/.env.bundle` é um só por cópia do repo — um worktree por target de container.

```bash
./docker/setup.sh -t <target>                            # tudo
./docker/setup.sh -t <target> --skip-deploy              # só regenera .env.bundle, grants e sobe
./docker/setup.sh -t <target> --byol                     # + linhagem gravável (admin do metastore)
./docker/setup.sh -t <target> --no-up                    # não sobe o container
```

No fim ele mostra o `/api/v1/diagnostics/prereqs`; cada acesso faltante vem com o comando pronto. Para mudar a configuração do app, edite o `target.yml` e rode o setup de novo.

Quem roda o setup precisa poder fazer o `bundle deploy` e, para os grants ([`grant_sp.sh`](grant_sp.sh)), ser owner do warehouse, conceder nos catálogos do RC18 e da DQX e ter `DATABRICKS_SUPERUSER` no branch Lakebase da Studio. O role Postgres do SP do container não é recriado por `bundle deploy`, então o GRANT do Lakebase não cai a cada deploy — ao contrário do SP do App.

## Remover

O inverso do setup — o equivalente ao `databricks bundle destroy`:

```bash
./docker/destroy.sh -t <target>                   # compose down + bundle destroy + apaga .env.bundle
./docker/destroy.sh -t <target> --revoke-grants   # + revoga os grants do SP fora do bundle
./docker/destroy.sh -t <target> --yes             # sem a confirmação do destroy
```

- Exige `-t` e só aceita target com `app_hosting: container`: para targets com Databricks App, use `databricks bundle destroy`.
- O `bundle destroy` apaga o catálogo do target **com os dados**, além de warehouse, jobs e dashboards. O espelho do Lakebase só é apagado se for deste target — se o setup o pulou, ele é de outro deployment e fica.
- `--revoke-grants` revoga o que o `grant_sp.sh` deu fora do bundle (grants na DQX Studio, GRANT e role no Lakebase). Use só se o SP do container não servir a outro deployment: esses grants são por SP, não por target. Os do catálogo e do warehouse do target somem com o destroy.
- Ficam de fora: o `docker/.env` (SP do container) e a imagem `rc18-app:local`. A linhagem externa (`rc18_*`) também — é do metastore e compartilhada entre deployments; remova à mão se for o caso (CLAUDE.md, seção Lineage).

## Deploy no AKS

Alternativa ao compose. Exige Azure CLI (`az login`) e `kubectl`.

```bash
./docker/setup.sh -t <target> --no-up
./docker/deploy_aks.sh -g <rg> -r <acr> -l <região> [--dry-run]
kubectl --context <cluster> -n rc18 port-forward svc/rc18-app 8010:8000
```

- Cria o que faltar (resource group, ACR, cluster) e roda uma réplica `ClusterIP`, sem exposição externa (o app não autentica usuário). Rode de novo para publicar código ou config.
- `-c dqx-studio` usa o cluster da DQX Studio.
- O API server só aceita `--api-server-ip-ranges` (default: seu IP); mudou de IP, rode de novo.
- O build no ACR usa PyPI/npm públicos; sem ACR Tasks, `--local-build` ou `--image`.

## Problemas comuns

- `unknown shorthand flag: 'f'`: o plugin Compose não está registrado (comum com Colima via Homebrew). Adicione `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` ao `~/.docker/config.json`, ou use `docker-compose` com os mesmos argumentos.
- Porta 8000 ocupada: `RC18_PORT=8010` no `docker/.env`.
- Rede sem acesso ao PyPI/npm públicos: `PIP_INDEX_URL` e `NPM_CONFIG_REGISTRY` no `docker/.env` — o compose repassa ao build.

## Diferenças para o Databricks Apps

- **Sem autenticação de usuário.** No Databricks Apps a plataforma faz o SSO e injeta `X-Forwarded-Email`/`-User`/`-Preferred-Username`, que o app grava como autor de incidentes e vínculos. No container, quem alcança a porta age com os privilégios do SP e escolhe esses headers — por isso o compose publica só em `127.0.0.1`. Para expor, use um proxy com SSO que sobrescreva esses headers (ex.: oauth2-proxy, que envia os mesmos nomes).
- **Embeds de dashboard e Genie:** o host do container precisa estar em Approved domains ([Aprovar o domínio do app](../README.md#aprovar-o-domínio-do-app)), e o navegador precisa de sessão ativa no workspace.
- **DQX Studio:** o embed em `/rules` não é tratado por este modo.
- **Branding** (logo/tema) fica no filesystem do container e some ao recriá-lo, como no Databricks Apps.
- **Grants:** o task `grant_warehouse_perms` do `rc18_end_to_end` só aplica o grant reverso (SP da DQX Studio) com `app_hosting: container`; os do SP do container vêm do `grant_sp.sh`.

## Sem compose

```bash
docker build -f docker/Dockerfile -t rc18-app app
docker run --rm -p 127.0.0.1:8000:8000 --env-file docker/.env --env-file docker/.env.bundle rc18-app
```

- Build em Mac Apple Silicon gera imagem arm64; para servidor x86, `--platform linux/amd64`.
- Rede restrita: aqui os mirrors vão por `--build-arg NPM_CONFIG_REGISTRY=<mirror>` e `--build-arg PIP_INDEX_URL=<mirror>`; proxy corporativo via `--build-arg HTTPS_PROXY=<proxy>`.
