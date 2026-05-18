-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Cross-catalog GRANTs for the seed_dqx_checks task
-- MAGIC
-- MAGIC O bundle RC18 (`rc18-starter-kit-dev`) faz seed das 4 regras iniciais
-- MAGIC na tabela externa **`dqx_catalog.dqx_app.dq_quality_rules`** — propriedade
-- MAGIC do app DQX Studio (`databrickslabs/dqx`). Para o service principal do
-- MAGIC bundle conseguir ler+escrever nessa tabela, é preciso conceder
-- MAGIC permissões cross-catalog **manualmente** (uma vez por workspace).
-- MAGIC
-- MAGIC ## Pré-requisitos
-- MAGIC
-- MAGIC - Você precisa ser **owner** do catálogo `dqx_catalog` ou ter `MANAGE`
-- MAGIC   sobre a tabela `dq_quality_rules`.
-- MAGIC - Descubra o service principal (SP) que executa o bundle:
-- MAGIC
-- MAGIC   ```bash
-- MAGIC   databricks apps get r18-compliance-app-dev --profile azure \
-- MAGIC     | grep -i "service_principal\|principal"
-- MAGIC   # ou:
-- MAGIC   databricks bundle summary -t dev --profile azure | grep -i principal
-- MAGIC   ```
-- MAGIC
-- MAGIC - Substitua `<RC18_SP>` abaixo pelo identificador retornado (geralmente
-- MAGIC   um UUID ou o email do usuário que rodou `bundle deploy` em ambiente dev).
-- MAGIC
-- MAGIC ## Quando rodar
-- MAGIC
-- MAGIC - **Uma vez**, depois do primeiro `databricks bundle deploy` e **antes**
-- MAGIC   do primeiro `databricks bundle run setup_reference_tables`.
-- MAGIC - Re-rodar é seguro: `GRANT` é idempotente.
-- MAGIC - Se a DQX Studio for redeployada em outro catálogo/schema, ajuste o
-- MAGIC   FQN abaixo e atualize `var.dqx_checks_table` em `databricks.yml`.
-- MAGIC
-- MAGIC ## Por que não está no setup_job
-- MAGIC
-- MAGIC O `seed_dqx_checks` task roda **como** o SP que precisa do grant — incluí-lo
-- MAGIC na chain criaria um deadlock circular. Este notebook é executado pelo
-- MAGIC humano-admin uma vez como pré-requisito.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## GRANTs

-- COMMAND ----------

-- Substitua <RC18_SP> pelo identificador real do service principal antes de rodar.
-- Backticks são necessários se o identificador contiver caracteres especiais.

GRANT USE CATALOG ON CATALOG dqx_catalog                          TO `<RC18_SP>`;
GRANT USE SCHEMA  ON SCHEMA  dqx_catalog.dqx_app                  TO `<RC18_SP>`;
GRANT SELECT      ON TABLE   dqx_catalog.dqx_app.dq_quality_rules TO `<RC18_SP>`;
GRANT MODIFY      ON TABLE   dqx_catalog.dqx_app.dq_quality_rules TO `<RC18_SP>`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Verificação
-- MAGIC
-- MAGIC Confirme que os grants apareceram:

-- COMMAND ----------

SHOW GRANTS ON TABLE dqx_catalog.dqx_app.dq_quality_rules;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC Após rodar, o próximo `databricks bundle run setup_reference_tables -t dev --profile azure`
-- MAGIC vai conseguir executar o task `seed_dqx_checks` sem erro de permissão.
