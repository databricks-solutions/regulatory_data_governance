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
| `notebooks/scr3040_generator/` | Notebooks | Lógica de geração do Doc 3040 (setup, dados, regras, XML) |
| `notebooks/scr3050_generator/` | Notebooks | Lógica de agregação 3040→3050 + validação automatizada |
| `prompts/` | Markdown | Meta-prompts que orientaram a construção dos geradores (docs, não runtime) |

## Como rodar

```bash
cd demo
databricks bundle validate -t dev --profile ssa-latam
databricks bundle deploy   -t dev --profile ssa-latam

# Executa os geradores
databricks bundle run scr3040_generator    -t dev --profile ssa-latam
databricks bundle run scr3050_generator    -t dev --profile ssa-latam
databricks bundle run synthetic_data_loader -t dev --profile ssa-latam
```

O bundle `rc18-demo` **inclui todos os recursos do acelerador** (app, pipelines, dashboards, genie) MAIS os geradores sintéticos. Para o cliente usar só o acelerador, rodar a partir da **raiz do repositório** (bundle `rc18-starter-kit`).

## Estrutura

```
demo/
├── README.md                          # este arquivo
├── databricks.yml                     # bundle rc18-demo (inclui core + demo)
├── notebooks/
│   ├── scr3040_generator/             # 4 etapas: setup, dados, regras, XML
│   ├── scr3050_generator/             # 5 etapas: setup, ingestão, agregação, XML, validação
│   └── synthetic_data_loader.py       # carrega dados fictícios nas tabelas
├── prompts/                           # meta-prompts dos geradores (docs)
│   ├── syntetic-dataset-generator-3040.md
│   └── syntetic-dataset-generator-3050.md
└── resources/                         # DAB jobs do demo
    ├── scr3040_generator.yml
    ├── scr3050_generator.yml
    ├── synthetic_data.yml
    └── scheduled_refresh.yml
```

## Parâmetros principais (jobs)

### `scr3040_generator`
- `dt_base` (ex: `2026-03`) — período de referência
- `cnpj_if` (ex: `99999999`) — CNPJ da IF emissora
- `n_clientes` (ex: `500`), `n_ops_por_cli` (ex: `3`) — tamanho da amostra
- `volume_out` — volume UC destino do XML

### `scr3050_generator`
- Consome tabelas `f_3040_*` produzidas pelo `scr3040_generator`
- Valida o XML gerado via `Validador TXB BACEN` (requer JVM no driver — usa cluster clássico single-node)
- `validador_zip`, `xsd_path` — artefatos BACEN pré-carregados em volume UC

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
databricks bundle destroy -t dev --profile ssa-latam
```

Isso remove **todos** os recursos deployados por este bundle (acelerador + demo). Se quer limpar só o demo e manter o acelerador, destrua os jobs individualmente via UI ou CLI.
