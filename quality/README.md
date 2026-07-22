# Regras de Qualidade RC18 — SCR 3040 (DQX Studio)

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

| Arquivo | Categoria | Tabela-alvo (silver/gold) | Dimensão R.18 |
|---------|-----------|---------------------------|:-------------:|
| [`dqx_checks/scr3040_dominio.yml`](dqx_checks/scr3040_dominio.yml) | Valores válidos por campo | `silver.scr3040_operacoes`, `silver.scr3040_clientes` | 9 Integridade · 3 Adaptabilidade |
| [`dqx_checks/scr3040_consistencia.yml`](dqx_checks/scr3040_consistencia.yml) | Consistência intra-documento | `silver.scr3040_operacoes/clientes/vencimentos/garantias` | 8 Consistência · 6 Completude |
| [`dqx_checks/scr3040_batimento_cosif.yml`](dqx_checks/scr3040_batimento_cosif.yml) | Batimento inter-CADOC (3040 × 4010) | `gold.reconciliacao_cosif` | 8 Consistência |

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

## Como aplicar no DQX Studio

1. **Substitua `rc18_catalog`** pelo seu catálogo em todos os `.yml` (caso BYOC).
2. No DQX Studio, crie/importe os checks a partir de cada arquivo, associando ao
   **run_config / tabela-alvo** indicado no cabeçalho de cada `.yml`.
3. Garanta os pré-requisitos de cada categoria:
   - **Domínio**: a tabela `reference.dominios` deve estar semeada
     (`notebooks/setup/setup_reference_tables.py`).
   - **Consistência**: a `silver` do 3040 deve estar populada (rode o pipeline).
   - **Batimento**: a tabela `gold.reconciliacao_cosif` deve existir — produzida
     pelo **simulador do CADOC 4010** (`demo/notebooks/doc4010_generator/`).
4. Execute e revise no app RC18 (Críticas SCR / Qualidade R.18): cada regra
   aparece na sua dimensão, com o `critica_id` como identificador.

## Limitações declaradas

- **Subconjunto representativo**, não o catálogo inteiro. Cada regra cita seu
  código oficial, mas não cobrimos as ~200 críticas.
- O **batimento COSIF** usa um mapeamento rubrica ↔ filtro 3040 **simplificado**
  (subconjunto de regras T/M), rotulado como simulação — não a lógica COSIF
  completa do BACEN.
- Regras **descontinuadas** (ligadas a `ClassOp`/Anexo 17, "Vigente até 12/2024")
  foram **excluídas** — a classificação de risco migrou para o modelo de perda
  esperada da Res. CMN 4.966/2021 a partir de jan/2025.
- O `expression` do DQX (`sql_expression`) retorna **true = passa**. As
  subqueries `EXISTS` assumem os nomes de coluna reais da `silver` do 3040.
