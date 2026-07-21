# Bundle Genie SCR R.18 (`rc18-genie`) — opt-in

Bundle **separado e opcional** que provisiona o **Genie Space** (agente de
consultas em linguagem natural sobre os dados SCR/R.18). Fica fora do deploy
principal de propósito — ver "Por que separado" abaixo.

## Por que é um bundle separado

A API `POST /genie/spaces` **valida, no momento da criação, que todas as tabelas
do space já existem**. No deploy do core (`rc18-starter-kit`), as tabelas
(`gold.posicao_3040/3050`, `reference.*`, `governance.incidents`) ainda **não
existem** — elas só nascem quando o job `rc18_end_to_end` roda, depois do deploy.

Se o Genie fosse provisionado junto com o core, o deploy falhava com
`403 PERMISSION_DENIED: Catalog '...' does not exist` e — como o app referenciava
o space — derrubava app, permissions e job em cascata. Isolando o Genie aqui, o
deploy principal fica limpo e o Genie vira um passo **opcional e posterior**.

## Pré-requisitos

1. O core (`rc18-starter-kit`) já deployado (`./bundle.sh deploy` na raiz).
2. O job `rc18_end_to_end` já executado (as 9 tabelas do space existem e estão
   populadas).
3. `genie/target.yml` criado a partir de `genie/target.yml.example`, com o
   **mesmo profile e catálogo** do core, e um `warehouse_id` válido.

## Passos

```bash
# 1. Descubra o warehouse do core (ou use um existente)
databricks warehouses list --profile <profile>     # ex.: rc18-warehouse-dev

# 2. Configure o target local
cp genie/target.yml.example genie/target.yml
#    preencha: profile, warehouse_id (e catalog, se o core não usa rc18_catalog)

# 3. Provisione o Genie Space
cd genie
databricks bundle deploy                            # cria o Genie Space "Genie Agent — SCR R.18"

# 4. Pegue o space_id gerado
databricks genie list-spaces --profile <profile>    # copie o space_id do "Genie Agent — SCR R.18"
```

## Conectar o Genie ao app

O app (bundle core) lê o Genie via a variável `genie_space_id`. Bundles não
compartilham `${resources...}` entre si, então o wiring é manual (2 passos):

```bash
# No target.yml do CORE (raiz do repo), defina o ID copiado acima:
#   variables:
#     genie_space_id: 01f1....
# e redeploy o core para o app receber a env var:
./bundle.sh deploy
```

Sem esse passo, o app mostra o placeholder "disponível após deploy" na aba Genie
(o backend trata o default `__unset__` como Genie desativado). O embed do iframe
exige também que o domínio do app esteja em **Settings → Security → Approved
domains** (ver README principal, seção "Aprovar o domínio do app").

## Re-sincronizar após editar o space na UI

```bash
cd genie
databricks bundle generate genie-space --resource rc18_genie --force
# depois: reverta rc18_catalog -> ${var.catalog} nos identifiers das tabelas
# e reconverta file_path -> serialized_space inline (a interpolação de
# ${var.catalog} só funciona inline — ver CLAUDE.md "Bundle gotchas").
```

## Destruir

```bash
cd genie
databricks bundle destroy        # remove apenas o Genie Space; não toca no core
```
