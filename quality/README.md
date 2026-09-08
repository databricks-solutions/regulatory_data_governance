# Regras de Qualidade RC18 — SCR, COSIF e DDR (DQX Studio)

Catálogo de **regras de qualidade executáveis** para o CADOC/Documento **SCR 3040**,
no formato de _checks_ do [DQX Studio](https://databrickslabs.github.io/dqx/) (Databricks Labs).
Você **aplica estas regras manualmente no DQX Studio** — este diretório entrega
apenas os artefatos `.yml`; nada aqui executa as regras.

## Por que estas regras (e não todas as ~200 críticas do BACEN)

A **Resolução Conjunta nº 18** é principiológica: exige a Política de Qualidade,
as **12 dimensões** e a governança, mas **não** enumera regras técnicas de campo.
As regras concretas do 3040 vêm do catálogo oficial
[`docs/scr3040/SCR3040_Criticas.xls`](../docs/scr3040/SCR3040_Criticas.xls) e são
executadas pelo **Validador do BACEN** no gate final, antes da remessa.

Reimplementar 1:1 o Validador seria duplicação sem valor. O ganho destas regras é:

1. **Rodar cedo (shift-left)** — sobre a `silver` conforme os dados chegam, dias
   antes do gate final, permitindo corrigir na origem (rastreável) sem estourar
   o prazo do 9º dia útil.
2. **Traduzir para as dimensões R.18** — cada resultado vira métrica de
   conformidade por dimensão (scorecard/governança), não só um pass/fail.

Por isso o foco é o subconjunto de **maior valor não-duplicativo**: **domínio +
consistência intra-documento + batimento inter-CADOC (3040 × COSIF 4010)**.
Regras puramente sintáticas/XSD ficam de fora (território do Validador).

## Arquivos

**Um arquivo por tabela-alvo** — o DQX Studio importa cada `.yml` vinculado a uma
tabela ("Regras de tabela única"). Cada arquivo agrupa os checks daquela tabela;
`critica_id`/dimensão de cada regra ficam em `user_metadata`.

| Arquivo (tabela-alvo) | Tabela-alvo | Categorias | Dimensão R.18 |
|---|---|---|:-:|
| [`dqx_checks/scr3040_operacoes.yml`](dqx_checks/scr3040_operacoes.yml) | `silver.scr3040_operacoes` | Domínio (NatuOp, Mod) + consistência (datas, IPOC, integridade ref.) | 9 · 2 · 8 |
| [`dqx_checks/scr3040_clientes.yml`](dqx_checks/scr3040_clientes.yml) | `silver.scr3040_clientes` | Domínio (TpCli, Autorzc, PorteCli, TpCtrl) | 9 · 3 |
| [`dqx_checks/scr3040_garantias.yml`](dqx_checks/scr3040_garantias.yml) | `silver.scr3040_garantias` | Consistência (garantidor ≠ cliente) | 8 |
| [`dqx_checks/scr3040_vencimentos.yml`](dqx_checks/scr3040_vencimentos.yml) | `silver.scr3040_vencimentos` | Consistência (≥ 1 vencimento) | 6 |
| [`dqx_checks/scr4010_saldos.yml`](dqx_checks/scr4010_saldos.yml) | `silver.scr4010_saldos` | Leiaute COSIF 4010 — formato/DV da conta, saldo, tipoRemessa, data-base | 9 · 2 · 6 · 8 |
| [`dqx_checks/scr4016_saldos.yml`](dqx_checks/scr4016_saldos.yml) | `silver.scr4016_saldos` | Idem 4010 + grupos 7/8 vedados + periodicidade semestral | 9 · 2 · 6 · 8 · 10 |
| [`dqx_checks/reconciliacao_cosif.yml`](dqx_checks/reconciliacao_cosif.yml) | `gold.reconciliacao_cosif` | Batimento inter-CADOC (3040 × 4010) | 8 |
| [`dqx_checks/scr2011_contas.yml`](dqx_checks/scr2011_contas.yml) | `silver.scr2011_contas` | Leiaute DDR 2011 — domínio das contas (Anexo 4), CNPJ, tipoEnvio, valor, bloco, data-base é dia útil | 3 · 9 · 6 · 2 · 12 |
| [`dqx_checks/scr2011_detalhamentos.yml`](dqx_checks/scr2011_detalhamentos.yml) | `silver.scr2011_detalhamentos` | Domínios dos eixos do DDR (moeda/país/posição — Anexos 5/6/7) + valor do detalhamento | 3 · 9 · 6 · 2 |
| [`dqx_checks/criticas_ddr_2011.yml`](dqx_checks/criticas_ddr_2011.yml) | `gold.criticas_ddr_2011` | Críticas oficiais intra-DDR 4693 e 4751 (via `status`) | 8 · 1 |

Cada check carrega em `user_metadata`: `dimensao_r18` (1–12), `critica_id`
(código oficial ancorado no catálogo), `descricao` e `nivel_verificacao`
(1=sintático, 2=inter-documento, 3=negocial). Esses metadados são exatamente os
que o app RC18 lê para montar as Críticas e o scorecard por dimensão.

## Mapeamento código → dimensão (resumo)

| Código(s) | Regra | Dimensão R.18 |
|-----------|-------|:-------------:|
| `S20_001/002/003`, `S-DOM-*`, `S17` | Domínios de campo (Autorzc, PorteCli, TpCtrl, NatuOp, Mod, TpCli) | 3 / 9 |
| `S10_004` | DiaAtraso ≥ 0 | 2 Acurácia |
| `S14`, `S15` | Compatibilidade de datas (contratação × vencimento × data-base) | 8 |
| `S87`/`S88` | IPOC bem-formado e consistente | 8 |
| `A04` | Cada agregação com ≥ 1 vencimento | 6 |
| `S13` | Garantidor fidejussório ≠ cliente principal | 8 |
| `REF-OP-CLI` | Integridade referencial operação → cliente | 8 |
| `N01` | Batimento SCR 3040 × COSIF (Doc 4010) | 8 |

## Execução mensal — escopo por data-base (via `filter`)

> **Exceção do DDR (Doc 2011), que é DIÁRIO.** Os checks de `scr2011_*` e de
> `criticas_ddr_2011` filtram por
> `data_base_month = (SELECT max(data_base_month) FROM <tabela>)`, e **não** por
> `dt_base = (SELECT max(dt_base) …)` como os CADOCs mensais. Com várias
> datas-base no mesmo mês, filtrar pelo último `dt_base` avaliaria só o último dia
> remetido; filtrar pelo mês avalia o mês corrente inteiro — que é o grão do
> seletor de Data-Base do app (mensal e compartilhado por todos os CADOCs).

As regras rodam mensalmente e devem avaliar apenas a **data-base mais recente** de
cada dataset — não reprocessar meses já validados.

O escopo é aplicado pelo campo **`filter`** de cada check, com uma subquery que
restringe à `MAX(dt_base)` da própria tabela:

```yaml
- name: dia_atraso_nao_negativo
  criticality: error
  filter: "dt_base = (SELECT max(dt_base) FROM rc18_catalog.silver.scr3040_operacoes)"
  check:
    function: sql_expression
    arguments:
      expression: "dia_atraso IS NULL OR dia_atraso >= 0"   # true = passa
```

Só as linhas da data-base mais recente são avaliadas. Não há coluna nem estado a
manter — o `MAX(dt_base)` é recomputado a cada execução, direto do dado.

Notas:

- **Escopo por dataset.** Cada `filter` referencia a `MAX(dt_base)` da sua própria
  tabela, então reprocessar um dataset (nova data-base) afeta só os checks dele.
- **A subquery no `filter` exige que o SP da DQX Studio leia `rc18_catalog`** — sem o
  grant (ver "Como aplicar", passo 3), a subquery não resolve e o DQX marca **100% das
  linhas como violação** (falso-positivo silencioso: o run passa como SUCCESS).

> ⚠️ **Amostragem (`sample_size`) na execução mensal: use "All rows" (`sample_size=0`).**
> O DQX aplica o `sample_size` **antes** do `filter`. Como as tabelas são particionadas
> por `dt_base`, um sample pequeno pode pegar só linhas de meses antigos e avaliar zero
> linhas da data-base corrente — o run passa como SUCCESS com 0 violações, mascarando
> problemas. Sempre execute/agende com **All rows**.

> **Limitação:** o escopo cobre só a data-base mais recente. Para revalidar um mês
> específico, ajuste o `filter` (ex.: `dt_base = '2026-03'`) pontualmente.

## Como aplicar no DQX Studio

1. **Substitua `rc18_catalog`** pelo seu catálogo nos `.yml` (caso BYOC).
2. No DQX Studio, em **Importar regras** (aba "From DQX YAML"), importe **um arquivo
   por vez** e selecione a **tabela-alvo** correspondente (indicada no cabeçalho de
   cada `.yml`). As regras entram como checks `sql_expression` de tabela única, com
   `filter` escopando à data-base corrente.
3. Garanta os pré-requisitos:
   - **Domínios**: rode `notebooks/setup/setup_reference_tables.py` — semeia
     `reference.dominios` e cria as views `reference.v_dom_3040_*` /
     `reference.v_recon_status_bloqueante` que os checks consultam.
   - **Silver/gold populadas**: rode o pipeline (silver) e o simulador do CADOC 4010
     (gold `reconciliacao_cosif`).
   - **GRANT para o SP da DQX Studio ler `rc18_catalog`** (⚠️ crítico e não-óbvio):
     os jobs de validação rodam como o SP da DQX Studio, que precisa de `USE CATALOG`
     + `SELECT` em `rc18_catalog.{silver,gold,reference}`. Sem isso, TODA subquery dos
     checks — o `filter` de escopo mensal E os checks de domínio/referência/batimento —
     não resolve e o check marca **100% como violação** (falso-positivo silencioso: o
     run passa como SUCCESS). Ver `notebooks/setup/grant_dqx_studio_access.sql`
     (seção "GRANT REVERSO").
4. **Aprove** (Submit → Approve) e **Execute** (Run Rules) — usando **All rows**
   (ver o aviso sobre `sample_size` acima). Revise no app RC18 (Críticas SCR /
   Qualidade R.18): cada regra aparece na sua dimensão, com o `critica_id`.

> **Semântica do `sql_expression`.** A `expression` retorna `true` = a linha **passa**;
> `false` = viola. O `filter` (`dt_base = (SELECT max…)`) restringe a avaliação à
> data-base corrente antes da expression.

> **Domínios via `IN (SELECT ... FROM reference.v_dom_*)`, sem literais string.** O
> DQX Studio grava cada check via `parse_json` inline; **literais string na
> `expression` são corrompidos** (aspas simples somem no round-trip; duplas quebram o
> import). Por isso o filtro `documento`/`campo` mora nas views `reference.v_dom_3040_*`
> (definidas no setup) e a `expression` só as referencia — nunca coloque `'...'` numa
> `expression` destinada ao DQX Studio.

## Limitações declaradas

- **Subconjunto representativo**, não o catálogo inteiro. Cada regra cita seu
  código oficial, mas não cobrimos as ~200 críticas.
- O **batimento COSIF** usa um mapeamento rubrica ↔ filtro 3040 **simplificado**
  (subconjunto de regras T/M), rotulado como simulação — não a lógica COSIF
  completa do BACEN.
- Regras **descontinuadas** (ligadas a `ClassOp`/Anexo 17, "Vigente até 12/2024")
  foram **excluídas** — a classificação de risco migrou para o modelo de perda
  esperada da Res. CMN 4.966/2021 a partir de jan/2025.
- Os checks usam `sql_expression` (`true` = passa). As subqueries de domínio assumem
  os nomes de coluna reais da `silver`/`gold` do 3040 e as views `reference.v_dom_3040_*`
  semeadas pelo setup.
- **Escopo mensal via subquery no `filter`** (`dt_base = (SELECT max(dt_base) …)`).
  Execute sempre com **All rows** — o `sample_size` é aplicado antes do `filter` (ver
  aviso na seção "Execução mensal"). Exige o grant do SP da DQX (passo 3).
