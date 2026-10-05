# App RC18 em container (Docker)

Roda o app (FastAPI + SPA) numa imagem Docker, fora do Databricks Apps. Catálogo, pipelines e dashboards continuam no bundle; a DQX Studio segue como app Databricks à parte.

## Modo mock (sem workspace)

```bash
docker compose -f docker/compose.yaml up --build
```

Abra http://localhost:8000. Sem `docker/.env` o container usa os dados mock, como o `./run_local.sh`.

- `unknown shorthand flag: 'f'`: o plugin Compose não está registrado (comum com Colima via Homebrew). Adicione `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` ao `~/.docker/config.json`, ou use `docker-compose` com os mesmos argumentos.
- Porta 8000 ocupada: `RC18_PORT=8010 docker compose -f docker/compose.yaml up --build`.
- Rede sem acesso ao PyPI/npm públicos: exporte `PIP_INDEX_URL` e `NPM_CONFIG_REGISTRY` (ou ponha no `docker/.env`) — o compose repassa ao build.

## Dados reais

1. Core bundle deployado e `rc18_end_to_end` rodado ([Início rápido](../README.md#início-rápido)).
2. Crie um service principal para o container e gere um OAuth secret para ele (Settings → Identity and access → Service principals → Secrets).
3. Conceda a esse SP o que o bundle concede ao SP do Databricks App — o bundle só cuida do SP do app:
   - **UC + warehouse:** os GRANTs de [`grant_warehouse_perms.py`](../notebooks/setup/grant_warehouse_perms.py), com o client id do container no lugar do SP do app.
   - **Lakebase (regras):** o role Postgres abaixo e o GRANT de [`grant_dqx_lakebase_access.sql`](../notebooks/setup/grant_dqx_lakebase_access.sql). Esse role não é recriado pelo `bundle deploy`, então o GRANT não cai a cada deploy.
     ```bash
     databricks postgres create-role projects/dqx-studio-db/branches/dqx --role-id sp-<client-id> \
       --json '{"spec": {"identity_type": "SERVICE_PRINCIPAL", "postgres_role": "<client-id>", "auth_method": "LAKEBASE_OAUTH_V1"}}'
     ```
   - **Linhagem gravável:** seção GRANT BYOL de [`grant_dqx_studio_access.sql`](../notebooks/setup/grant_dqx_studio_access.sql).
4. Configure e suba:
   ```bash
   cp docker/.env.example docker/.env      # preencha host, SP, warehouse, dashboards e DQX Studio
   docker compose -f docker/compose.yaml up --build -d
   ```
5. Confira `http://localhost:8000/api/v1/diagnostics/prereqs`: cada acesso faltante vem com o comando já preenchido com o client id do container. Se `lakebase_connection` prescrever `databricks bundle deploy`, a correção aqui é o `create-role` do passo 3.

## Diferenças para o Databricks Apps

- **Sem autenticação de usuário.** No Databricks Apps a plataforma faz o SSO e injeta `X-Forwarded-Email`/`-User`/`-Preferred-Username`, que o app grava como autor de incidentes e vínculos. No container, quem alcança a porta age com os privilégios do SP e escolhe esses headers — por isso o compose publica só em `127.0.0.1`. Para expor, use um proxy com SSO que sobrescreva esses headers (ex.: oauth2-proxy, que envia os mesmos nomes).
- **Embeds de dashboard e Genie:** o host do container precisa estar em Approved domains ([Aprovar o domínio do app](../README.md#aprovar-o-domínio-do-app)), e o navegador precisa de sessão ativa no workspace.
- **DQX Studio:** o embed em `/rules` não é tratado por este modo.
- **Branding** (logo/tema) fica no filesystem do container e some ao recriá-lo, como no Databricks Apps.
- **O Databricks App continua no bundle:** o role do Lakebase e o task de grants dependem do SP dele.

## Sem compose

```bash
docker build -f docker/Dockerfile -t rc18-app app
docker run --rm -p 127.0.0.1:8000:8000 --env-file docker/.env rc18-app
```

- Build em Mac Apple Silicon gera imagem arm64; para servidor x86, `--platform linux/amd64`.
- Rede restrita: aqui os mirrors vão por `--build-arg NPM_CONFIG_REGISTRY=<mirror>` e `--build-arg PIP_INDEX_URL=<mirror>`; proxy corporativo via `--build-arg HTTPS_PROXY=<proxy>`.
