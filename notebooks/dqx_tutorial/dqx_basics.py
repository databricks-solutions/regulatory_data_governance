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
# MAGIC O notebook usa a versão da DQX fixada pelo acelerador RC18 (`0.13.0`).
# MAGIC Mantenha o pin para que o comportamento aqui descrito reproduza
# MAGIC exatamente — DQX é Databricks Labs (pré-1.0), versões menores podem
# MAGIC quebrar a API.

# COMMAND ----------

# MAGIC %pip install databricks-labs-dqx==0.13.0
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
# MAGIC O caminho ruim é duplicar as N regras com um `filter` hard-coded
# MAGIC (`dt_base = '2026-03-01' AND cnpj_if = '12345678'`). Você acaba com
# MAGIC duas cópias de cada regra que precisam ser mantidas em paralelo.
# MAGIC
# MAGIC O caminho bom é manter **uma única definição** e injetar o `filter` em
# MAGIC tempo de execução usando um template Python (substituição antes do
# MAGIC `apply_checks`).
# MAGIC
# MAGIC > **Nota: DQX Variable Substitution ≠ parametrização de `filter`**
# MAGIC >
# MAGIC > A [documentação DQX sobre Variable Substitution](https://databrickslabs.github.io/dqx/docs/guide/quality_checks_definition/#variable-substitution)
# MAGIC > refere-se ao mecanismo `{{ input_view }}` / `{{ ref_name }}` da
# MAGIC > check function `sql_query` — que permite referenciar DataFrames
# MAGIC > (input e referência via `ref_dfs`) dentro de queries SQL completas.
# MAGIC > Isso é útil para validações cross-table (ver §2), mas **não se
# MAGIC > aplica ao campo `filter`**.
# MAGIC >
# MAGIC > O `filter` é avaliado como `F.expr(filter_str)` pelo DQX engine.
# MAGIC > Não há mecanismo nativo de substituição de variáveis nele. A
# MAGIC > abordagem abaixo (template Python com `.replace()`) é uma
# MAGIC > **convenção do projeto**, não um recurso DQX.

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
# MAGIC ### 3.3 Template Python — substituição de placeholder no `filter`
# MAGIC
# MAGIC As regras carregam um placeholder `${scope}` no `filter`. Antes de
# MAGIC chamar `apply_checks_by_metadata`, fazemos um `.replace("${scope}", predicate)`
# MAGIC em cada regra. Se `predicate` for `"1=1"`, é run completo; se for
# MAGIC `"dt_base = '2026-03-01' AND cnpj_if = '12345678'"`, é reprocessamento
# MAGIC focado.
# MAGIC
# MAGIC Repare que **a regra fica idêntica** entre os dois cenários — só o
# MAGIC parâmetro muda.

# COMMAND ----------

import copy

# Catálogo de regras "abstrato" com placeholder de escopo.
checks_template = [
    {
        "name": "saldo_nao_negativo",
        "criticality": "error",
        "run_config_name": "tutorial_operacoes_multi",
        "filter": "${scope}",
        "check": {
            "function": "sql_expression",
            "arguments": {
                "expression": "saldo >= 0",
                "msg": "Saldo da operação não pode ser negativo.",
            },
        },
        "user_metadata": {
            "dimensao_r18": "IV",
            "descricao": "Saldo da operação >= 0. Filtro injetado em runtime via ${scope}.",
        },
    },
    # Mais N regras viriam aqui — todas com filter: "${scope}".
]


def resolve_scope(checks, predicate):
    """Substitui ${scope} por um predicate SQL booleano em todas as regras."""
    resolved = copy.deepcopy(checks)
    for c in resolved:
        if "filter" in c and c["filter"]:
            c["filter"] = c["filter"].replace("${scope}", predicate)
    return resolved

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC #### Run 1 — produção normal (escopo total)
# MAGIC
# MAGIC `predicate = "1=1"` faz com que o `filter` da regra fique
# MAGIC `filter: "1=1"`, equivalente a “avalie todas as linhas”.

# COMMAND ----------

df_multi = spark.table("operacoes_multi")

full_run_checks = resolve_scope(checks_template, "1=1")
good_full, quarantine_full = dq.apply_checks_by_metadata_and_split(df_multi, full_run_checks)

print("Quarentena no run completo:")
display(quarantine_full.select("operacao_id", "cnpj_if", "dt_base", "saldo"))

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC Esperado: **4 linhas** na quarentena (OPA02, OPA04, OPA06, OPA08 — todas com `saldo < 0`).
# MAGIC A regra avalia tudo porque `filter: "1=1"` não restringe nada.
# MAGIC
# MAGIC #### Run 2 — reprocessamento focado
# MAGIC
# MAGIC Agora aplicamos o **mesmo catálogo de regras** mudando apenas o
# MAGIC predicate. O `filter` da regra passa a ser
# MAGIC `dt_base = DATE'2026-03-01' AND cnpj_if = '12345678'`. Linhas fora desse
# MAGIC escopo simplesmente **não são avaliadas** pela regra — elas
# MAGIC continuam no `good_df` mesmo que estejam quebradas, porque para esse
# MAGIC run elas não fazem parte do escopo de reprocessamento.

# COMMAND ----------

reprocess_predicate = "dt_base = DATE'2026-03-01' AND cnpj_if = '12345678'"
reprocess_checks = resolve_scope(checks_template, reprocess_predicate)

# Inspeciona como a regra ficou após o template
print("Regra resolvida:")
print(reprocess_checks[0]["filter"])

good_reproc, quarantine_reproc = dq.apply_checks_by_metadata_and_split(df_multi, reprocess_checks)

print("Quarentena no reprocessamento focado:")
display(quarantine_reproc.select("operacao_id", "cnpj_if", "dt_base", "saldo"))

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC Esperado: **1 linha** na quarentena (OPA04 — única negativa no recorte
# MAGIC `2026-03-01` + `cnpj_if=12345678`). OPA06 (CNPJ diferente) e OPA08 (mês
# MAGIC diferente), apesar de terem saldo negativo, ficam de fora do escopo e
# MAGIC portanto não viram quarentena nesse run.
# MAGIC
# MAGIC ### 3.4 Quando usar este padrão
# MAGIC
# MAGIC | Cenário | Como |
# MAGIC |---|---|
# MAGIC | Produção (escopo total) | `predicate = "1=1"` |
# MAGIC | Reprocessamento focado | `predicate = "<condição SQL>"` |
# MAGIC | Job parametrizado | `predicate = dbutils.widgets.get("reprocess_predicate")` |
# MAGIC | Bundle variable | `predicate = spark.conf.get("var.reprocess_predicate", "1=1")` |
# MAGIC
# MAGIC A convenção `${scope}` é do projeto (não do DQX). Documente-a.
# MAGIC No acelerador RC18, o padrão é usado porque as regras são carregadas
# MAGIC via DQX Studio / `quality.dqx_checks` e os jobs Python fazem o
# MAGIC `.replace()` antes de invocar `apply_checks_and_save_in_table`.

# COMMAND ----------

# MAGIC %md
# MAGIC    
# MAGIC ### 3.5 Relação com o Variable Substitution nativo do DQX
# MAGIC
# MAGIC O DQX oferece [Variable Substitution](https://databrickslabs.github.io/dqx/docs/guide/quality_checks_definition/#variable-substitution)
# MAGIC **dentro de queries SQL** da check function `sql_query`:
# MAGIC
# MAGIC ```yaml
# MAGIC - name: exemplo_sql_query
# MAGIC   check:
# MAGIC     function: sql_query
# MAGIC     arguments:
# MAGIC       query: |
# MAGIC         SELECT operacao_id, (saldo < 0) AS condition
# MAGIC         FROM {{ input_view }}
# MAGIC         WHERE cliente_id NOT IN (SELECT cliente_id FROM {{ clientes_vip }})
# MAGIC       merge_columns: [operacao_id]
# MAGIC ```
# MAGIC
# MAGIC Neste exemplo:
# MAGIC - `{{ input_view }}` → substituido automaticamente pelo temp view do DataFrame de entrada.
# MAGIC - `{{ clientes_vip }}` → substituido pelo temp view do DataFrame passado em `ref_dfs={"clientes_vip": df_vip}`.
# MAGIC
# MAGIC **Esse mecanismo não se aplica ao campo `filter`**, que é uma expressão
# MAGIC SQL pura avaliada via `F.expr()`. Para parametrizar o `filter`, o
# MAGIC template Python (`.replace()`) é a abordagem recomendada.

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
# MAGIC - Para reprocessar um subconjunto sem duplicar regras, parametrize o
# MAGIC   `filter` com um template Python (`.replace("${scope}", predicate)`).
# MAGIC   Isso é uma convenção do projeto — DQX não tem substituição nativa no `filter`.
# MAGIC - O **Variable Substitution** nativo do DQX (`{{ input_view }}`,
# MAGIC   `{{ ref_name }}`) aplica-se apenas à query SQL da check function
# MAGIC   `sql_query`, permitindo referenciar DataFrames de entrada e referência.
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
