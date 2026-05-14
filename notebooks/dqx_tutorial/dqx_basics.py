# Databricks notebook source
# MAGIC %md
# MAGIC # DQX na prática — validação cross-table e regras com `filter` parametrizado
# MAGIC
# MAGIC Este notebook é um tutorial **autocontido** sobre o uso de
# MAGIC [Databricks Labs DQX](https://databrickslabs.github.io/dqx/) para escrever
# MAGIC regras de qualidade de dados. Ele foca em dois padrões que aparecem com
# MAGIC frequência em projetos regulatórios (como o acelerador RC18) mas que não
# MAGIC têm um único caminho óbvio quando você está começando:
# MAGIC
# MAGIC 1. **Validação cross-table** — quando o que define se uma linha é válida
# MAGIC    depende de **outra tabela**. Aqui mostramos o caso "um código de cliente
# MAGIC    de uma tabela **não pode** existir em outra tabela".
# MAGIC 2. **`filter` parametrizado** — quando você quer **reprocessar** apenas
# MAGIC    um subconjunto de linhas (uma data, um CNPJ, uma janela específica) sem
# MAGIC    duplicar todas as regras só para mudar a cláusula `WHERE`.
# MAGIC
# MAGIC Tudo abaixo roda em um cluster ou serverless com acesso ao Unity Catalog.
# MAGIC Nenhuma dependência do bundle RC18 — você pode rodar isolado, em qualquer
# MAGIC workspace.
# MAGIC
# MAGIC > **DQX em uma frase.** DQX recebe um DataFrame de entrada, aplica uma
# MAGIC > lista de regras (`checks`) e devolve **dois** DataFrames: `good_df` com
# MAGIC > as linhas que passaram e `quarantine_df` com as que falharam — cada
# MAGIC > linha de quarentena carrega as colunas `_errors` / `_warnings` com o
# MAGIC > detalhamento de qual regra disparou e por quê.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Pré-requisitos
# MAGIC
# MAGIC Este tutorial usa **DQX `0.14.0`**, uma versão à frente do pin de
# MAGIC produção do RC18 (que está em `0.13.0`). A diferença é intencional: o
# MAGIC recurso de **Variable Substitution** usado na §3 foi adicionado em
# MAGIC `0.14.0` (parâmetro `variables=` em `load_checks(...)`). O notebook é
# MAGIC didático e standalone — não compartilha runtime com os pipelines silver,
# MAGIC então o bump aqui não afeta o resto do projeto.
# MAGIC
# MAGIC > **Importante:** não atualize o pin de produção (`app/backend/requirements.txt`,
# MAGIC > `resources/pipelines/silver.yml`) para `0.14.0` sem revisar o changelog
# MAGIC > — há breaking changes (default save mode mudou de `overwrite` para
# MAGIC > `append`, ordem de parâmetros alterada em `apply_checks_and_save_in_table`,
# MAGIC > novos campos no schema do resultado). Veja o
# MAGIC > [release notes v0.14.0](https://github.com/databrickslabs/dqx/releases/tag/v0.14.0).

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
# MAGIC Toda regra DQX tem o mesmo esqueleto (YAML ou dict Python — equivalentes):
# MAGIC
# MAGIC ```yaml
# MAGIC - name: <identificador_unico_da_regra>     # aparece em _errors[].name
# MAGIC   criticality: error | warn                 # error => quarentena; warn => passa, mas sinaliza
# MAGIC   filter: "<expr SQL booleana opcional>"    # pré-filtro: só avalia linhas onde isso é true
# MAGIC   run_config_name: <bucket_logico>          # ex: silver_3040_operacoes (vira partição em dqx_checks)
# MAGIC   check:
# MAGIC     function: <regex_match|foreign_key|sql_expression|is_not_null|...>
# MAGIC     arguments: { ... }                      # depende da function
# MAGIC   user_metadata:                            # K/V livres, propagam para _errors[].user_metadata
# MAGIC     dimensao_r18: VIII
# MAGIC     descricao: "..."
# MAGIC ```
# MAGIC
# MAGIC Vale destacar duas peças:
# MAGIC
# MAGIC | Campo | Para que serve | Observação |
# MAGIC |---|---|---|
# MAGIC | `filter` | Restringe o **escopo** da regra a um subconjunto de linhas | Linhas que não passam no filtro não viram falha — elas são simplesmente **não avaliadas** por essa regra. Essencial para o cenário de "reprocessamento" da §3. |
# MAGIC | `check.function` | A lógica de validação propriamente dita | `sql_expression` é o canivete suíço; `foreign_key` cobre "deve existir em outra tabela"; pra "**não deve** existir", precisamos de `sql_expression` (§2). |
# MAGIC
# MAGIC ### 1.2 O fluxo `apply_checks_*`
# MAGIC
# MAGIC ```python
# MAGIC from databricks.labs.dqx.engine import DQEngine
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC
# MAGIC dq = DQEngine(WorkspaceClient())
# MAGIC good_df, quarantine_df = dq.apply_checks_by_metadata_and_split(input_df, checks)
# MAGIC ```
# MAGIC
# MAGIC - `apply_checks_by_metadata_and_split(...)` → retorna o par `(good, quarantine)` e **descarta** as colunas `_errors`/`_warnings` do good (forma recomendada para tabelas silver "limpas").
# MAGIC - `apply_checks_by_metadata(...)` → retorna **um único** DataFrame com todas as linhas mais as colunas `_errors`/`_warnings` (útil pra debugar).
# MAGIC - `apply_checks_and_save_in_table(...)` → versão "tudo-em-um" usada nos pipelines DLT do acelerador (escreve `<tabela>` + `<tabela>_quarantine` em uma chamada).

# COMMAND ----------

from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient

dq = DQEngine(WorkspaceClient())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Exemplo cross-table — "código de cliente NÃO deve existir em outra tabela"
# MAGIC
# MAGIC ### 2.1 Cenário
# MAGIC
# MAGIC Você tem duas tabelas:
# MAGIC
# MAGIC - `operacoes` — operações de crédito abertas. Cada linha referencia um `cliente_id`.
# MAGIC - `clientes_bloqueados` — denylist mantida pela área de Compliance. Clientes
# MAGIC   listados aqui **não podem** ter operações ativas (sanções, restrições
# MAGIC   internas, etc.).
# MAGIC
# MAGIC **Regra:** toda linha em `operacoes` cujo `cliente_id` aparece em
# MAGIC `clientes_bloqueados` é uma violação `error` → vai para quarentena.
# MAGIC
# MAGIC Note que isso é o **inverso** do que `foreign_key` faz nativamente
# MAGIC (`foreign_key` valida que o valor **existe** em outra tabela). Para
# MAGIC "não existe" precisamos de `sql_expression` com `NOT EXISTS`.

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
# MAGIC `NOT EXISTS` em DQX é uma `sql_expression` cuja `expression` é uma
# MAGIC condição **booleana** avaliada por linha. Quando a expression resolve
# MAGIC para `false`, a linha vira erro. A subquery correlaciona o `cliente_id`
# MAGIC da linha corrente com a tabela `clientes_bloqueados`.
# MAGIC
# MAGIC > **Por que `sql_expression` e não `foreign_key`?**
# MAGIC > `foreign_key` na DQX 0.13.0 verifica que o valor **está** em uma
# MAGIC > tabela de referência (semântica "lookup"). Para a semântica oposta
# MAGIC > ("não está em uma denylist"), `sql_expression` com `NOT EXISTS` é a
# MAGIC > forma idiomática. Ele também é a sua saída quando a regra precisa
# MAGIC > de qualquer lógica mais elaborada (joins, agregados, subqueries com
# MAGIC > múltiplas colunas, etc.).

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
# MAGIC
# MAGIC `apply_checks_by_metadata_and_split` devolve duas DataFrames. Para
# MAGIC entender o que aconteceu, é didático olhar a **versão completa** (com
# MAGIC `_errors`) antes de separar.

# COMMAND ----------

# Alias necessário para NOT EXISTS: o Spark precisa desambiguar
# outer_tbl.cliente_id (DataFrame externo) de b.cliente_id (subquery)
operacoes_df = spark.table("operacoes").alias("operacoes")

# Versão "espia tudo" — mantém _errors/_warnings na linha
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
# MAGIC Esperado: 5 linhas em `good_df` (clientes não bloqueados) e 3 linhas em
# MAGIC `quarantine_df` (OP003, OP005 e OP007 — todas referenciam clientes
# MAGIC bloqueados). Cada linha de quarentena tem em `_errors[0].name` o
# MAGIC valor `cliente_nao_bloqueado` e em `_errors[0].user_metadata` os
# MAGIC metadados da regra (dimensão R.18, descrição, etc.).
# MAGIC
# MAGIC ### 2.5 Variações úteis do mesmo padrão
# MAGIC
# MAGIC O mesmo `sql_expression` cobre vários casos cross-table:
# MAGIC
# MAGIC | Variação | `expression` |
# MAGIC |---|---|
# MAGIC | Pelo menos 1 operação ativa exigida pra um cliente "VIP" | `EXISTS (SELECT 1 FROM ... WHERE ...)` |
# MAGIC | Status do cliente em outra tabela ≠ 'ENCERRADO' | `cliente_id NOT IN (SELECT cliente_id FROM ... WHERE status='ENCERRADO')` |
# MAGIC | Cliente bloqueado **em uma data ≤ dt_base** (regra temporal) | `NOT EXISTS (SELECT 1 FROM clientes_bloqueados b WHERE b.cliente_id = cliente_id AND b.dt_bloqueio <= dt_base)` |
# MAGIC
# MAGIC A última é interessante: ela impede que **bloqueios futuros** invalidem
# MAGIC retroativamente operações que eram válidas na data de competência —
# MAGIC algo que aparece com frequência em conformidade BCB.

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC ## 3. Cláusula `filter` parametrizada — reprocessamento sem reescrever regras
# MAGIC
# MAGIC ### 3.1 O problema operacional
# MAGIC
# MAGIC Você tem um conjunto de N regras DQX rodando todo dia sobre a tabela
# MAGIC inteira. Em algum momento, o time de Compliance pede:
# MAGIC
# MAGIC > _"Reaplicar todas as regras só nas operações de Março/2026 do CNPJ
# MAGIC > 12345678."_
# MAGIC
# MAGIC O caminho ruim é duplicar as N regras com um `filter` hard-coded — você
# MAGIC acaba com duas cópias de cada regra para manter em paralelo.
# MAGIC
# MAGIC O caminho bom é manter **uma única definição** e usar o recurso oficial
# MAGIC de [**Variable Substitution**](https://databrickslabs.github.io/dqx/docs/guide/quality_checks_definition/#variable-substitution)
# MAGIC do DQX: você coloca um placeholder `{{ nome_da_variavel }}` em qualquer
# MAGIC **campo string** da regra (`filter`, `expression`, `ref_table`, etc.) e
# MAGIC passa os valores em runtime via o argumento `variables=` do
# MAGIC `DQEngine.load_checks(...)`. O único campo que **não** aceita
# MAGIC substituição é `criticality` (precisa ser literal `error` ou `warn`).

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC ### 3.2 Setup — uma regra “real” e dados com várias datas / CNPJs

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
# MAGIC    
# MAGIC ### 3.3 Definir a regra em YAML com `{{ scope }}`
# MAGIC
# MAGIC O `filter` carrega um placeholder `{{ scope }}`. Quando o DQX carrega o
# MAGIC YAML via `load_checks(..., variables={"scope": "<predicate SQL>"})`, o
# MAGIC valor de `scope` substitui o placeholder antes de a regra entrar no
# MAGIC engine. A mesma regra serve para o run completo e para o
# MAGIC reprocessamento focado — só o dict `variables` muda.

# COMMAND ----------

CHECKS_PATH = "/tmp/dqx_tutorial_filter_checks.yml"

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
# MAGIC
# MAGIC ### 3.4 Carregar e aplicar com variáveis diferentes
# MAGIC
# MAGIC `DQEngine.load_checks(config=..., variables=...)` lê o YAML, resolve os
# MAGIC placeholders e devolve a lista de regras pronta para
# MAGIC `apply_checks_by_metadata_and_split`.
# MAGIC
# MAGIC #### Run 1 — produção normal (escopo total)
# MAGIC
# MAGIC Passamos `scope = "dt_base >= DATE'2000-01-01'"` — qualquer registro a
# MAGIC partir do ano 2000, ou seja, **todo o histórico** da tabela. É o tipo de
# MAGIC limite inferior que pipelines de produção costumam carregar como default.

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
# MAGIC
# MAGIC Esperado: **4 linhas** na quarentena (OPA02, OPA04, OPA06, OPA08 — todas com `saldo < 0`).
# MAGIC
# MAGIC #### Run 2 — reprocessamento focado
# MAGIC
# MAGIC Reaproveitamos o **mesmo YAML**. Só muda o dict `variables`. Linhas
# MAGIC fora do escopo simplesmente **não são avaliadas** pela regra — elas
# MAGIC continuam no `good_df` mesmo se estiverem quebradas, porque nesse run
# MAGIC não fazem parte do escopo de reprocessamento.

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
# MAGIC
# MAGIC Esperado: **1 linha** na quarentena (OPA04 — única negativa no recorte
# MAGIC `2026-03-01` + `cnpj_if=12345678`). OPA06 (CNPJ diferente) e OPA08 (mês
# MAGIC diferente), apesar de terem saldo negativo, ficam fora do escopo.
# MAGIC
# MAGIC ### 3.5 Outras variáveis úteis do mesmo mecanismo
# MAGIC
# MAGIC `variables=` resolve placeholders em **qualquer campo string** da regra.
# MAGIC Alguns casos comuns:
# MAGIC
# MAGIC | Variável usada em | Para que serve |
# MAGIC |---|---|
# MAGIC | `filter: "{{ scope }}"` | Escopo de reprocessamento (este §) |
# MAGIC | `arguments.ref_table: "{{ catalog }}.reference.dominios"` | Mesma regra em dev/prod variando só o catálogo |
# MAGIC | `arguments.expression: "saldo <= {{ teto_modalidade }}"` | Limites de negócio versionados fora do YAML |
# MAGIC | `for_each_column: ["{{ partition_col }}"]` | Reaproveitar template entre datasets |
# MAGIC
# MAGIC Em produção, o dict `variables=` costuma vir de:
# MAGIC
# MAGIC ```python
# MAGIC variables = {
# MAGIC     "scope":   dbutils.widgets.get("scope"),                   # widget do notebook
# MAGIC     "catalog": spark.conf.get("var.catalog", "rc18_catalog"),  # bundle variable
# MAGIC     # ou via job parameter: {{job.parameters.scope}}
# MAGIC }
# MAGIC ```
# MAGIC
# MAGIC O mesmo argumento `variables=` é aceito por `TableChecksStorageConfig`,
# MAGIC então as regras podem estar versionadas em `quality.dqx_checks` (como o
# MAGIC RC18 mantém) e ainda assim ser parametrizadas em runtime.

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC ## 4. Resumo
# MAGIC
# MAGIC - DQX expõe regras como dicts/YAML com `name`, `criticality`, `check.function`,
# MAGIC   `check.arguments`, `filter` (opcional) e `user_metadata` (livre).
# MAGIC - Para "valor **não deve** existir em outra tabela", use `sql_expression`
# MAGIC   com `NOT EXISTS (SELECT 1 FROM <denylist> WHERE ...)`. `foreign_key` só
# MAGIC   cobre o caso inverso ("deve existir").
# MAGIC - Para reprocessar um subconjunto sem duplicar regras, use o recurso
# MAGIC   oficial de **Variable Substitution** do DQX: placeholders
# MAGIC   `{{ nome }}` em qualquer campo string da regra (`filter`, `expression`,
# MAGIC   `ref_table`, …) são resolvidos por
# MAGIC   `DQEngine.load_checks(config=..., variables=...)`. O único campo
# MAGIC   excluído é `criticality`.
# MAGIC
# MAGIC ### Próximos passos
# MAGIC
# MAGIC - Catálogo completo de `check.function` na DQX 0.13.0:
# MAGIC   [databrickslabs.github.io/dqx/docs/reference/quality_rules/](https://databrickslabs.github.io/dqx/docs/reference/quality_rules/)
# MAGIC - DQX Studio (UI para gerenciar regras sem editar YAML):
# MAGIC   [databrickslabs.github.io/dqx/docs/guide/dqx_studio/](https://databrickslabs.github.io/dqx/docs/guide/dqx_studio/)
# MAGIC - Como o RC18 integra DQX em silver: [`docs/spec/08_dqx_app_integration.md`](../../docs/spec/08_dqx_app_integration.md)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Cleanup (opcional)
# MAGIC
# MAGIC Descomenta para remover o schema de tutorial.

# COMMAND ----------

# spark.sql(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA} CASCADE")
