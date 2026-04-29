# `demo/` — Bundle de demonstração (uso interno Databricks)

> ⚠️ **Esta pasta é exclusiva do time Databricks para demos.**
> Se você é cliente usando este repositório como base para sua plataforma RC18, **ignore ou delete este diretório**. Nada no bundle do acelerador (raiz) depende do que está aqui.

Este bundle existe só para demonstrar o acelerador rodando fim-a-fim com dados sintéticos do Doc 3040 e Doc 3050 — sem depender dos dados reais do cliente.

## O que o demo entrega (além do acelerador)

| Recurso | Tipo | Descrição |
|---------|------|-----------|
| `scr3040_generator` | Job (4 etapas) | Gera XML sintético do Doc 3040 válido para o Validador BACEN |
| `scr3050_generator` | Job (5 etapas) | Gera XML sintético do Doc 3050 (TXB V11) a partir do 3040 via equivalência; valida com o Validador TXB |
| `synthetic_data_loader` | Job | Carrega dados fictícios nas tabelas `bronze/silver/gold` do catálogo |
| `scheduled_refresh` | Job agendado | Cron diário que re-executa o `synthetic_data_loader` |
| `rc18_demo_warehouse` | SQL Warehouse | Serverless 2X-Small (auto-stop 10 min) que alimenta dashboards, Genie e jobs do demo |
| `notebooks/scr3040_generator/` | Notebooks | Lógica de geração do Doc 3040 (setup, dados, regras, XML) |
| `notebooks/scr3050_generator/` | Notebooks | Lógica de agregação 3040→3050 + validação automatizada |
| `prompts/` | Markdown | Meta-prompts que orientaram a construção dos geradores (docs, não runtime) |

## Como rodar

O bundle do demo é **autocontido**: o próprio deploy provisiona um SQL Warehouse serverless 2X-Small (`rc18-demo-warehouse`) e usa ele para dashboards, Genie e jobs. Não é preciso passar `--var warehouse_id`.

Se você prefere reutilizar um warehouse existente, sobreponha o variable: `--var warehouse_id=<id>` ou `BUNDLE_VAR_warehouse_id=<id>`.

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

```bash
cd demo

# Dev (default)
databricks bundle validate -t dev-azure --profile <your-databricks-profile>
databricks bundle deploy   -t dev-azure --profile <your-databricks-profile>

# Outras combinações
databricks bundle deploy   -t dev-aws    --profile <your-databricks-profile>
databricks bundle deploy   -t prod-azure --profile <your-databricks-profile>

# Executa os geradores (use o mesmo target do deploy)
databricks bundle run scr3040_generator    -t dev-azure --profile <your-databricks-profile>
databricks bundle run scr3050_generator    -t dev-azure --profile <your-databricks-profile>
databricks bundle run synthetic_data_loader -t dev-azure --profile <your-databricks-profile>
```

O bundle `rc18-demo` **inclui todos os recursos do acelerador** (app, pipelines, dashboards, genie) MAIS os geradores sintéticos e o warehouse serverless. Para o cliente usar só o acelerador, rodar a partir da **raiz do repositório** (bundle `rc18-starter-kit`) — esse bundle não cria warehouse, o cliente aponta para o seu próprio via `--var warehouse_id=<id>`.

## Estrutura

```
demo/
├── README.md                          # este arquivo
├── databricks.yml                     # bundle rc18-demo (inclui core + demo)
├── assets/
│   └── validators/                    # binários oficiais do BCB (sincronizados pelo bundle)
│       ├── SCR3040_Validador.bin      # ZIP do Validador3040 (extensão .bin evita auto-extract no Workspace Files)
│       ├── SCR3050_Validador.bin      # ZIP do ValidadorMDR (idem)
│       └── Schema_TXB_V11.xsd         # XSD do Doc 3050 / TXB V11 (referenciado pelo ValidadorMDR)
├── notebooks/
│   ├── scr3040_generator/             # 5 etapas: setup, dados, regras, XML, validação BACEN
│   ├── scr3050_generator/             # 5 etapas: setup, ingestão, agregação, XML, validação
│   └── synthetic_data_loader.py       # carrega dados fictícios nas tabelas
├── prompts/                           # meta-prompts dos geradores (docs)
│   ├── syntetic-dataset-generator-3040.md
│   └── syntetic-dataset-generator-3050.md
└── resources/                         # DAB jobs do demo
    ├── scr3040_generator.yml
    ├── scr3050_generator.yml
    ├── synthetic_data.yml
    ├── scheduled_refresh.yml
    └── warehouse.yml                   # SQL Warehouse serverless 2X-Small
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

Isso remove **todos** os recursos deployados por este bundle (acelerador + demo). Se quer limpar só o demo e manter o acelerador, destrua os jobs individualmente via UI ou CLI.
