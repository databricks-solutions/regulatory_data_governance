# `demo/` — Bundle de demonstração (uso interno Databricks)

> ⚠️ **Esta pasta é exclusiva do time Databricks para demos.**
> Se você é cliente usando este repositório como base para sua plataforma RC18, **ignore ou delete este diretório**. Nada no bundle do acelerador (raiz) depende do que está aqui.

Este bundle existe só para mostrar:
1. O **app** rodando em **modo mock** (UI completa do acelerador, sem dependência de dados reais).
2. Os **geradores sintéticos** de XML do Doc 3040 e Doc 3050, validados com os binários oficiais do BCB.

> O bundle do demo é **autocontido e enxuto** — não inclui as pipelines DLT (bronze/silver/gold), os dashboards Lakeview, nem o `setup_reference_tables` do acelerador. Para o stack completo do cliente, rodar o bundle `rc18-starter-kit` a partir da raiz do repo.

## O que o demo entrega

| Recurso | Tipo | Descrição |
|---------|------|-----------|
| `r18_compliance_app` | Databricks App | App em modo mock (`USE_MOCK_BACKEND=true`) — source compartilhado com o bundle do core (`../app/backend`) |
| `rc18_demo_catalog` | Catalog | Catálogo dedicado ao demo, criado pelo bundle |
| `bronze`, `reference` | Schemas | Homes para tabelas escritas pelos jobs (3040/3050 staging vai em `reference`; loader sintético vai em `bronze`) |
| `scr3040_generator` | Job (5 tasks) | Gera XML sintético do Doc 3040 + valida com o `Validador3040` oficial do BCB |
| `scr3050_generator` | Job (5 tasks) | Gera XML sintético do Doc 3050 (TXB V11) a partir do 3040 via equivalência + valida com o `ValidadorMDR` |
| `synthetic_data_loader` | Job | Popula `${var.catalog}.bronze` com SCR sintético (operacoes_raw, clientes_raw, raw_3050_diario) |
| `notebooks/scr3040_generator/` | Notebooks | Lógica de geração do Doc 3040 (setup, dados, regras, XML, validação) |
| `notebooks/scr3050_generator/` | Notebooks | Lógica de agregação 3040→3050 + validação automatizada |
| `prompts/` | Markdown | Meta-prompts que orientaram a construção dos geradores (docs, não runtime) |

## Como rodar

### Escolha do target

O alvo (`-t`) combina `<env>-<cloud>` — define o `mode` (development/production) e o node type do cluster clássico do validador BACEN (3050):

| Target | Env | Cloud | `validator_node_type` |
|--------|-----|-------|------------------------|
| `dev-azure` (default) | development | Azure | `Standard_DS3_v2` |
| `dev-aws` | development | AWS | `m5d.large` |
| `dev-gcp` | development | GCP | `n2-highmem-4` |
| `prod-azure` | production | Azure | `Standard_DS3_v2` |
| `prod-aws` | production | AWS | `m5d.large` |
| `prod-gcp` | production | GCP | `n2-highmem-4` |

`dev-*` deploya em `/Workspace/Users/<user>/.bundle/...` (escopo pessoal, prefixa recursos com `[dev <user>]`). `prod-*` deploya em `/Workspace/Shared/.bundle/...` (compartilhado, sem prefixo, com permissão CAN_MANAGE para o grupo `users`).

### Deploy

```bash
cd demo

# 1. Validate + deploy: cria o catálogo, schemas, jobs e o app
databricks bundle validate -t dev-azure --profile <your-databricks-profile>
databricks bundle deploy   -t dev-azure --profile <your-databricks-profile>

# 2. Executa os geradores e o loader sintético (use o mesmo target do deploy)
databricks bundle run scr3040_generator     -t dev-azure --profile <your-databricks-profile>
databricks bundle run scr3050_generator     -t dev-azure --profile <your-databricks-profile>
databricks bundle run synthetic_data_loader -t dev-azure --profile <your-databricks-profile>
```

> Re-rodar `bundle deploy` sempre que alterar o código do app — ele detecta a mudança no source e re-publica o container automaticamente.
>
> ⚠️ **Após `bundle destroy`**, o primeiro `bundle deploy` apenas inicia o compute do app sem publicar o código (conhecido bug do `lifecycle.started: true` no DABs em criação fresca). Sintoma: app fica em `UNAVAILABLE` apesar do compute `ACTIVE`. Para recuperar, rode `bundle deploy` uma segunda vez **ou** execute `databricks bundle run r18_compliance_app -t <target>`.

## Estrutura

```
demo/
├── README.md                          # este arquivo
├── databricks.yml                     # bundle rc18-demo (autocontido — não inclui ../resources)
├── assets/
│   └── validators/                    # binários oficiais do BCB (sincronizados pelo bundle)
│       ├── SCR3040_Validador.bin      # ZIP do Validador3040 (extensão .bin evita auto-extract no Workspace Files)
│       ├── SCR3050_Validador.bin      # ZIP do ValidadorMDR (idem)
│       └── Schema_TXB_V11.xsd         # XSD do Doc 3050 / TXB V11 (referenciado pelo ValidadorMDR)
├── notebooks/
│   ├── scr3040_generator/             # 5 etapas: setup, dados, regras, XML, validação BACEN
│   ├── scr3050_generator/             # 5 etapas: setup, ingestão, agregação, XML, validação
│   └── synthetic_data_loader.py       # carrega dados fictícios em ${var.catalog}.bronze
├── prompts/                           # meta-prompts dos geradores (docs)
│   ├── syntetic-dataset-generator-3040.md
│   └── syntetic-dataset-generator-3050.md
└── resources/                         # DAB resources do demo
    ├── app.yml                        # App em modo mock (USE_MOCK_BACKEND=true)
    ├── catalog.yml                    # rc18_demo_catalog
    ├── uc_assets.yml                  # schemas bronze + reference
    ├── synthetic_data.yml             # job r18-synthetic-data-loader
    ├── scr3040_generator.yml          # job rc18-scr3040-generator
    └── scr3050_generator.yml          # job rc18-scr3050-generator
```

## Parâmetros principais (jobs)

### `scr3040_generator`
- `dt_base` (ex: `2026-03`) — período de referência
- `cnpj_if` (ex: `99999999`) — CNPJ da IF emissora
- `n_clientes` (ex: `500`), `n_ops_por_cli` (ex: `3`) — tamanho da amostra
- `volume_out` — volume UC destino do XML (criado em runtime se não existir)
- `validador_zip` — caminho do `Validador3040` BACEN; default aponta para o binário versionado em `demo/assets/validators/` e sincronizado pelo bundle (não exige upload manual)
- `fail_on_error` — `true` faz a task falhar se o validador BACEN reportar erro
- Última etapa (`validacao_bacen`) roda em cluster clássico single-node SINGLE_USER (JVM no driver)

### `scr3050_generator`
- Consome tabelas `f_3040_*` produzidas pelo `scr3040_generator` — rode o 3040 antes
- Valida o XML gerado via ValidadorMDR (Doc 3050/TXB V11) do BCB — requer JVM no driver, usa cluster clássico single-node SINGLE_USER
- `validador_zip`, `xsd_path` — defaults apontam para artefatos versionados em `demo/assets/validators/` e sincronizados pelo bundle (não exigem upload manual)
- `volume_out` — volume UC destino do XML (criado em runtime se não existir)

### `synthetic_data_loader`
- `catalog`, `schema_bronze` — destino das tabelas (default: `${var.catalog}.bronze`)
- `n_operacoes` (default `50000`), `n_meses` (default `6`), `dt_base_inicio` (default `2025-09-01`)

## Dados sintéticos — características

- ~150 mil operações cobrindo Jan-Mar 2026
- Defeitos plantados para tornar o demo de qualidade crível:
  - 3% de nulos em campos obrigatórios
  - 2% de valores fora de domínio
  - 5% de divergências cross-document (3040 vs 3050 vs COSIF)
- Tendência de qualidade melhorando ao longo do tempo (Jan 82% → Fev 91% → Mar 96%)

## Teardown

Para limpar o workspace após a demo:

```bash
cd demo
databricks bundle destroy -t <env>-<cloud> --profile <your-databricks-profile>
# ex: -t dev-azure, -t prod-aws, etc.
```

Isso remove **apenas** os recursos do bundle do demo (app em mock, catálogo `rc18_demo_catalog`, schemas, e os 3 jobs). O acelerador (bundle `rc18-starter-kit`) não é tocado.
