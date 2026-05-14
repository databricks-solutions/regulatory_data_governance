# Databricks notebook source
# MAGIC %md
# MAGIC # DQX na prática — validação cross-table e filter parametrizado
# MAGIC
# MAGIC Tutorial sobre [Databricks Labs DQX](https://databrickslabs.github.io/dqx/) cobrindo dois padrões comuns em projetos regulatórios:
# MAGIC
# MAGIC 1. **Validação cross-table** — verificar se um valor de uma tabela **não existe** em outra (denylist).
# MAGIC 2. **`filter` parametrizado** — reprocessar um subconjunto de linhas sem duplicar regras.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Pré-requisitos
# MAGIC
# MAGIC Este tutorial usa **DQX `0.14.0`**. O recurso de **Variable Substitution** (§3) foi adicionado em `0.14.0`.

# COMMAND ----------

# MAGIC %pip install databricks-labs-dqx==0.14.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "dqx_tutorial", "Schema didático (será criado)")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Working in: {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Conceitos centrais
# MAGIC
# MAGIC ### 1.1 Anatomia de uma regra
# MAGIC
# MAGIC ```yaml
# MAGIC - name: <id_regra>
# MAGIC   criticality: error | warn
# MAGIC   filter: "<expr SQL booleana>"      # opcional — só avalia linhas onde é true
# MAGIC   check:
# MAGIC     function: <sql_expression|foreign_key|is_not_null|...>
# MAGIC     arguments: { ... }
# MAGIC   user_metadata: { ... }             # K/V livres, propagam para _errors
# MAGIC ```
# MAGIC
# MAGIC | Campo | Função |
# MAGIC |---|---|
# MAGIC | `filter` | Restringe escopo — linhas fora do filtro não são avaliadas |
# MAGIC | `check.function` | Lógica de validação (`sql_expression` é o mais flexível) |
# MAGIC
# MAGIC ### 1.2 Fluxo principal
# MAGIC
# MAGIC ```python
# MAGIC dq = DQEngine(WorkspaceClient())
# MAGIC good_df, quarantine_df = dq.apply_checks_by_metadata_and_split(input_df, checks)
# MAGIC ```
# MAGIC
# MAGIC * `apply_checks_by_metadata_and_split` → par `(good, quarantine)`
# MAGIC * `apply_checks_by_metadata` → DataFrame único com `_errors`/`_warnings` (útil para debug)
# MAGIC * `apply_checks_and_save_in_table` → versão "tudo-em-um" que persiste em tabelas

# COMMAND ----------

from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient

dq = DQEngine(WorkspaceClient())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Exemplo cross-table — "cliente NÃO deve existir em outra tabela"
# MAGIC
# MAGIC ### 2.1 Cenário
# MAGIC
# MAGIC * `operacoes` — operações de crédito com `cliente_id`
# MAGIC * `clientes_bloqueados` — denylist de Compliance
# MAGIC
# MAGIC **Regra:** `cliente_id` presente em `clientes_bloqueados` → quarentena.
# MAGIC
# MAGIC > `foreign_key` valida que um valor **existe** em outra tabela. Para "não existe", usamos `sql_expression` com `NOT EXISTS`.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.2 Cria as tabelas de exemplo

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS operacoes")
spark.sql("DROP TABLE IF EXISTS clientes_bloqueados")

spark.sql("""
CREATE TABLE operacoes (
  operacao_id STRING,
  cliente_id  STRING,
  dt_base     DATE,
  saldo       DECIMAL(18,2)
) USING DELTA
""")

spark.sql("""
INSERT INTO operacoes VALUES
  ('OP001', 'CLI-100', DATE'2026-03-01', 50000.00),
  ('OP002', 'CLI-200', DATE'2026-03-01', 12000.00),
  ('OP003', 'CLI-300', DATE'2026-03-01', 75000.00),  -- CLI-300 está bloqueado → falha
  ('OP004', 'CLI-400', DATE'2026-03-01',  3000.00),
  ('OP005', 'CLI-500', DATE'2026-03-01', 99000.00),  -- CLI-500 está bloqueado → falha
  ('OP006', 'CLI-100', DATE'2026-04-01', 50500.00),  -- mês seguinte, mesmo cliente OK
  ('OP007', 'CLI-300', DATE'2026-04-01', 80000.00),  -- mês seguinte, bloqueado de novo → falha
  ('OP008', 'CLI-600', DATE'2026-04-01', 25000.00)
""")

spark.sql("""
CREATE TABLE clientes_bloqueados (
  cliente_id    STRING,
  motivo        STRING,
  dt_bloqueio   DATE
) USING DELTA
""")

spark.sql("""
INSERT INTO clientes_bloqueados VALUES
  ('CLI-300', 'sancao_internacional', DATE'2026-01-15'),
  ('CLI-500', 'restricao_interna',    DATE'2026-02-10')
""")

display(spark.table("operacoes"))
display(spark.table("clientes_bloqueados"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.3 A regra DQX
# MAGIC
# MAGIC Usamos `sql_expression` com `NOT EXISTS` — a expression deve ser `true` para a linha passar. Quando resolve para `false`, a linha vai para quarentena.

# COMMAND ----------

cross_table_check = {
    "name": "cliente_nao_bloqueado",
    "criticality": "error",
    "run_config_name": "tutorial_operacoes",
    "check": {
        "function": "sql_expression",
        "arguments": {
            "expression": f"""
                NOT EXISTS (
                  SELECT 1
                  FROM {CATALOG}.{SCHEMA}.clientes_bloqueados cli_bloq
                  WHERE cli_bloq.cliente_id = operacoes.cliente_id
                )
            """,
            "msg": "Operação aberta para cliente presente na denylist (clientes_bloqueados).",
            "negate": False,
        },
    },
    "user_metadata": {
        "dimensao_r18": "VIII",
        "descricao": (
            "cliente_id em operacoes não pode existir em clientes_bloqueados. "
            "Cross-table denylist check via NOT EXISTS."
        ),
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2.4 Aplica e inspeciona

# COMMAND ----------

# Alias necessário para NOT EXISTS: o Spark precisa desambiguar
operacoes_df = spark.table("operacoes").alias("operacoes")

# Mantém _errors/_warnings na linha
annotated_df = dq.apply_checks_by_metadata(operacoes_df, [cross_table_check])
display(annotated_df.select("operacao_id", "cliente_id", "dt_base", "_errors"))

# COMMAND ----------

# Versão "produção" — separa em good (limpo) e quarentena (com _errors)
good_df, quarantine_df = dq.apply_checks_by_metadata_and_split(operacoes_df, [cross_table_check])

print("good_df:")
display(good_df)

print("quarantine_df:")
display(quarantine_df)

# COMMAND ----------

# MAGIC %md
# MAGIC **Esperado:** 5 linhas em `good_df`, 3 em `quarantine_df` (OP003, OP005, OP007 — clientes bloqueados).
# MAGIC
# MAGIC ### 2.5 Variações do mesmo padrão
# MAGIC
# MAGIC | Caso | Expression |
# MAGIC |---|---|
# MAGIC | Cliente deve ter operação ativa | `EXISTS (SELECT 1 FROM ... WHERE ...)` |
# MAGIC | Status ≠ 'ENCERRADO' | `cliente_id NOT IN (SELECT ... WHERE status='ENCERRADO')` |
# MAGIC | Bloqueio temporal (`dt_bloqueio <= dt_base`) | `NOT EXISTS (... WHERE b.cliente_id = cliente_id AND b.dt_bloqueio <= dt_base)` |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. `filter` parametrizado — reprocessamento sem duplicar regras
# MAGIC
# MAGIC ### 3.1 O problema
# MAGIC
# MAGIC N regras rodam diariamente sobre toda a tabela. Compliance pede: _"reaplicar só em Março/2026, CNPJ 12345678"_.
# MAGIC
# MAGIC **Solução:** [Variable Substitution](https://databrickslabs.github.io/dqx/docs/guide/quality_checks_definition/#variable-substitution) — placeholders `{{ var }}` em campos string da regra, resolvidos via `variables=` em `load_checks(...)`. Único campo excluído: `criticality`.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.2 Setup — dados com várias datas e CNPJs

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS operacoes_multi")
spark.sql("""
CREATE TABLE operacoes_multi (
  operacao_id STRING,
  cnpj_if     STRING,
  cliente_id  STRING,
  dt_base     DATE,
  saldo       DECIMAL(18,2)
) USING DELTA
""")
spark.sql("""
INSERT INTO operacoes_multi VALUES
  ('OPA01', '12345678', 'CLI-100', DATE'2026-02-01',   1000.00),
  ('OPA02', '12345678', 'CLI-200', DATE'2026-02-01',  -50.00),   -- saldo negativo, erro
  ('OPA03', '12345678', 'CLI-300', DATE'2026-03-01',   5000.00),
  ('OPA04', '12345678', 'CLI-400', DATE'2026-03-01',     -1.00), -- saldo negativo, erro
  ('OPA05', '12345678', 'CLI-500', DATE'2026-03-01',   7000.00),
  ('OPA06', '99999999', 'CLI-600', DATE'2026-03-01',     -2.00), -- saldo negativo, MAS outro CNPJ
  ('OPA07', '12345678', 'CLI-700', DATE'2026-04-01',  10000.00),
  ('OPA08', '12345678', 'CLI-800', DATE'2026-04-01',     -3.00)  -- saldo negativo, mas mês fora do reprocesso
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.3 Regra YAML com `{{ scope }}`
# MAGIC
# MAGIC O placeholder `{{ scope }}` no campo `filter` é substituído em runtime pelo valor passado em `variables={"scope": "..."}`. A mesma regra serve para o run completo e para reprocessamento focado.

# COMMAND ----------

CHECKS_PATH = "dqx_tutorial_filter_checks.yml"

checks_yaml = """
- name: saldo_nao_negativo
  criticality: error
  run_config_name: tutorial_operacoes_multi
  filter: "{{ scope }}"
  check:
    function: sql_expression
    arguments:
      expression: "saldo >= 0"
      msg: "Saldo da operação não pode ser negativo."
  user_metadata:
    dimensao_r18: IV
    descricao: "Saldo >= 0. Escopo de avaliação injetado via {{ scope }}."
# Mais N regras viriam aqui — todas reutilizam o mesmo {{ scope }}.
"""

with open(CHECKS_PATH, "w") as f:
    f.write(checks_yaml)

print(f"YAML salvo em: {CHECKS_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3.4 Carregar e aplicar com variáveis diferentes
# MAGIC
# MAGIC #### Run 1 — produção (escopo total)
# MAGIC
# MAGIC `scope = "dt_base >= DATE'2000-01-01'"` → avalia todo o histórico.

# COMMAND ----------

from databricks.labs.dqx.config import FileChecksStorageConfig

df_multi = spark.table("operacoes_multi")

full_run_checks = dq.load_checks(
    config=FileChecksStorageConfig(location=CHECKS_PATH),
    variables={"scope": "dt_base >= DATE'2000-01-01'"},
)

good_full, quarantine_full = dq.apply_checks_by_metadata_and_split(df_multi, full_run_checks)

print("Quarentena no run completo:")
display(quarantine_full.select("operacao_id", "cnpj_if", "dt_base", "saldo"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Esperado:** 4 linhas na quarentena (OPA02, OPA04, OPA06, OPA08 — saldo < 0).
# MAGIC
# MAGIC #### Run 2 — reprocessamento focado
# MAGIC
# MAGIC Mesmo YAML, só muda `variables`. Linhas fora do escopo não são avaliadas — permanecem no `good_df`.

# COMMAND ----------

reprocess_checks = dq.load_checks(
    config=FileChecksStorageConfig(location=CHECKS_PATH),
    variables={"scope": "dt_base = DATE'2026-03-01' AND cnpj_if = '12345678'"},
)

good_reproc, quarantine_reproc = dq.apply_checks_by_metadata_and_split(df_multi, reprocess_checks)

print("Quarentena no reprocessamento focado:")
display(quarantine_reproc.select("operacao_id", "cnpj_if", "dt_base", "saldo"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Esperado:** 1 linha na quarentena (OPA04). OPA06 (outro CNPJ) e OPA08 (outro mês) ficam fora do escopo.
# MAGIC
# MAGIC ### 3.5 Outras variáveis úteis
# MAGIC
# MAGIC | Variável em | Uso |
# MAGIC |---|---|
# MAGIC | `filter: "{{ scope }}"` | Escopo de reprocessamento |
# MAGIC | `arguments.ref_table: "{{ catalog }}.ref.dominios"` | Mesma regra em dev/prod |
# MAGIC | `arguments.expression: "saldo <= {{ teto }}"` | Limites de negócio externalizados |
# MAGIC
# MAGIC Em produção, `variables=` tipicamente vem de widgets, bundle variables ou job parameters.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Caso completo — Regra 3 do CADOC 3040 traduzida para `sql_expression`
# MAGIC
# MAGIC Combina os conceitos do §2 (`sql_expression` + `EXISTS`) e §3 (Variable Substitution em `filter` e `expression`).
# MAGIC
# MAGIC ### 4.1 A regra original
# MAGIC
# MAGIC > Para cada operação reportada no **mês anterior**, exigir que ela esteja em uma das duas situações no **mês atual**:
# MAGIC > 1. ainda presente em `bacen_cadoc_3040` (remessa = 1), OU
# MAGIC > 2. com uma linha de "saída" em `bacen_cadoc_3040_informacoes_adicionais` (`informacao_tipo_codigo = '03'`).
# MAGIC >
# MAGIC > Operações que somem **sem** registro de saída → violação.
# MAGIC
# MAGIC ```sql
# MAGIC DECLARE OR REPLACE VARIABLE ano_mes_atual    STRING DEFAULT '2026-02';
# MAGIC DECLARE OR REPLACE VARIABLE ano_mes_anterior STRING DEFAULT
# MAGIC   date_format(add_months(to_date(ano_mes_atual || '-01'), -1), 'yyyy-MM');
# MAGIC
# MAGIC WITH atual AS (
# MAGIC   SELECT cliente_codigo, operacao_identificacao_padronizada
# MAGIC   FROM   bacen_cadoc_3040
# MAGIC   WHERE  ano_mes = ano_mes_atual AND remessa = 1
# MAGIC ),
# MAGIC anterior AS (
# MAGIC   SELECT cliente_codigo, operacao_identificacao_padronizada
# MAGIC   FROM   bacen_cadoc_3040
# MAGIC   WHERE  ano_mes = ano_mes_anterior
# MAGIC ),
# MAGIC informacao_saida AS (
# MAGIC   SELECT cliente_codigo, operacao_identificacao_padronizada
# MAGIC   FROM   bacen_cadoc_3040_informacoes_adicionais
# MAGIC   WHERE  informacao_tipo_codigo = '03' AND ano_mes = ano_mes_atual
# MAGIC )
# MAGIC SELECT anterior.cliente_codigo, anterior.operacao_identificacao_padronizada
# MAGIC FROM   anterior
# MAGIC LEFT ANTI JOIN atual            USING (cliente_codigo, operacao_identificacao_padronizada)
# MAGIC LEFT ANTI JOIN informacao_saida USING (cliente_codigo, operacao_identificacao_padronizada);
# MAGIC ```
# MAGIC
# MAGIC ### 4.2 Tradução mental
# MAGIC
# MAGIC A query original **calcula os violadores** com anti-joins. DQX inverte: você descreve quando uma linha é **válida** (predicate booleano por linha) e o engine quarentena o que falha.
# MAGIC
# MAGIC | Original (set-based) | DQX (per-row) |
# MAGIC |---|---|
# MAGIC | `DECLARE VARIABLE ano_mes_*` | `variables={"ano_mes_atual": ..., "ano_mes_anterior": ...}` |
# MAGIC | CTE `atual` + `LEFT ANTI JOIN` | `EXISTS (SELECT 1 FROM bacen_cadoc_3040 a WHERE ... ano_mes = '{{ ano_mes_atual }}' ...)` |
# MAGIC | CTE `informacao_saida` + `LEFT ANTI JOIN` | `EXISTS (SELECT 1 FROM ..._informacoes_adicionais s WHERE ... informacao_tipo_codigo = '03' ...)` |
# MAGIC | CTE `anterior` (universo) | `filter: "ano_mes = '{{ ano_mes_anterior }}'"` |
# MAGIC | Resultado = violadores | `quarantine_df` |

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4.3 Setup dos dados sintéticos
# MAGIC
# MAGIC 4 operações em 2026-01. Esperamos que **só OP-D** viole (sumiu do mês atual e não tem `tipo_codigo='03'`).

# COMMAND ----------

spark.sql("DROP TABLE IF EXISTS bacen_cadoc_3040")
spark.sql("""
CREATE TABLE bacen_cadoc_3040 (
  ano_mes                            STRING,
  remessa                            INT,
  cliente_codigo                     STRING,
  operacao_identificacao_padronizada STRING
) USING DELTA
""")
spark.sql("""
INSERT INTO bacen_cadoc_3040 VALUES
  -- Mês anterior (2026-01): universo a verificar
  ('2026-01', 1, 'C1', 'OP-A'),
  ('2026-01', 1, 'C2', 'OP-B'),
  ('2026-01', 1, 'C3', 'OP-C'),
  ('2026-01', 1, 'C4', 'OP-D'),
  -- Mês atual (2026-02), remessa 1: só OP-A e OP-C persistem
  ('2026-02', 1, 'C1', 'OP-A'),
  ('2026-02', 1, 'C3', 'OP-C')
""")

spark.sql("DROP TABLE IF EXISTS bacen_cadoc_3040_informacoes_adicionais")
spark.sql("""
CREATE TABLE bacen_cadoc_3040_informacoes_adicionais (
  ano_mes                            STRING,
  cliente_codigo                     STRING,
  operacao_identificacao_padronizada STRING,
  informacao_tipo_codigo             STRING
) USING DELTA
""")
spark.sql("""
INSERT INTO bacen_cadoc_3040_informacoes_adicionais VALUES
  -- OP-B sumiu do atual, mas tem saída registrada → válida
  ('2026-02', 'C2', 'OP-B', '03'),
  -- OP-D tem registro adicional, mas de outro tipo → continua violando
  ('2026-02', 'C4', 'OP-D', '05')
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4.4 A regra DQX
# MAGIC
# MAGIC 4 placeholders entram via `variables=`: `{{ catalog }}`, `{{ schema }}` (qualificam as tabelas nos `EXISTS`), `{{ ano_mes_anterior }}` (no `filter`), `{{ ano_mes_atual }}` (dentro das duas subqueries).

# COMMAND ----------

CHECKS_PATH_REGRA3 = "dqx_tutorial_regra3.yml"

regra3_yaml = """
- name: operacao_persistente_ou_com_saida
  criticality: error
  run_config_name: tutorial_cadoc_3040
  filter: "ano_mes = '{{ ano_mes_anterior }}'"
  check:
    function: sql_expression
    arguments:
      expression: |
        EXISTS (
          SELECT 1
          FROM {{ catalog }}.{{ schema }}.bacen_cadoc_3040 a
          WHERE a.cliente_codigo                     = bacen_cadoc_3040.cliente_codigo
            AND a.operacao_identificacao_padronizada = bacen_cadoc_3040.operacao_identificacao_padronizada
            AND a.ano_mes                            = '{{ ano_mes_atual }}'
            AND a.remessa                            = 1
        )
        OR EXISTS (
          SELECT 1
          FROM {{ catalog }}.{{ schema }}.bacen_cadoc_3040_informacoes_adicionais s
          WHERE s.cliente_codigo                     = bacen_cadoc_3040.cliente_codigo
            AND s.operacao_identificacao_padronizada = bacen_cadoc_3040.operacao_identificacao_padronizada
            AND s.ano_mes                            = '{{ ano_mes_atual }}'
            AND s.informacao_tipo_codigo             = '03'
        )
      msg: "Operacao do mes anterior nao persiste no mes atual (remessa=1) e nao tem informacao adicional de saida (tipo_codigo='03')."
  user_metadata:
    dimensao_r18: VIII
    descricao: "Regra 3 CADOC 3040 - reproducao via sql_expression + Variable Substitution."
"""

with open(CHECKS_PATH_REGRA3, "w") as f:
    f.write(regra3_yaml)

# COMMAND ----------

# Alias da tabela de entrada — mesma convenção do §2 (Spark precisa desambiguar
# as colunas correlacionadas dentro dos EXISTS).
df_3040 = spark.table("bacen_cadoc_3040").alias("bacen_cadoc_3040")

regra3_checks = dq.load_checks(
    config=FileChecksStorageConfig(location=CHECKS_PATH_REGRA3),
    variables={
        "catalog":          CATALOG,
        "schema":           SCHEMA,
        "ano_mes_atual":    "2026-02",
        "ano_mes_anterior": "2026-01",
    },
)

good_r3, quarantine_r3 = dq.apply_checks_by_metadata_and_split(df_3040, regra3_checks)

print("Quarentena (esperado: apenas OP-D):")
display(quarantine_r3.select("ano_mes", "cliente_codigo", "operacao_identificacao_padronizada"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4.5 Trade-offs
# MAGIC
# MAGIC * Query original: 1 job Spark com anti-joins set-based — provavelmente mais barato em volume alto.
# MAGIC * Versão DQX: entrega `good_df` + `quarantine_df` com `_errors[*].user_metadata`, `rule_fingerprint`, `run_id`, e plugga em `quality.dqx_summary_metrics`/Críticas SCR/incidentes do RC18.
# MAGIC * Para escalar, substitua `EXISTS` por `foreign_key` quando a checagem couber em lookup simples, ou pré-agregue as tabelas em CTEs materializadas.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Resumo
# MAGIC
# MAGIC * **Cross-table "não existe":** `sql_expression` com `NOT EXISTS`. `foreign_key` só cobre "deve existir".
# MAGIC * **Reprocessamento focado:** Variable Substitution (`{{ var }}` + `variables=` em `load_checks`). Funciona em qualquer campo string exceto `criticality`.
# MAGIC * **Regras inter-período com anti-joins:** uma única `sql_expression` com `EXISTS`/`NOT EXISTS` + variáveis substituídas em `filter` e `expression` simultaneamente (§4).
# MAGIC
# MAGIC **Links:**
# MAGIC * [Catálogo de funções DQX](https://databrickslabs.github.io/dqx/docs/reference/quality_rules/)
# MAGIC * [DQX Studio](https://databrickslabs.github.io/dqx/docs/guide/dqx_studio/)
# MAGIC * [Integração DQX no RC18](../../docs/spec/08_dqx_app_integration.md)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Cleanup (opcional)

# COMMAND ----------

# spark.sql(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA} CASCADE")
