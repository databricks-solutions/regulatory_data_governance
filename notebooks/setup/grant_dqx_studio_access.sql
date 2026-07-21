-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Cross-catalog read GRANTs para o app RC18 acessar a DQX Studio
-- MAGIC
-- MAGIC O app RC18 **lê** (não escreve) as tabelas da DQX Studio
-- MAGIC (`databrickslabs/dqx`) para popular o catálogo de Críticas SCR, os KPIs de
-- MAGIC qualidade e as validações. As regras em si são criadas pelo usuário na
-- MAGIC própria DQX Studio — o RC18 não faz mais seed automático de regras.
-- MAGIC
-- MAGIC Para o service principal do bundle conseguir LER essas tabelas
-- MAGIC (que vivem em `dqx.dqx_studio`, um catálogo/schema diferente do
-- MAGIC `rc18_catalog`), é preciso conceder SELECT cross-catalog **uma vez por
-- MAGIC workspace**. Apenas leitura — nenhum MODIFY é necessário.
-- MAGIC
-- MAGIC ## Pré-requisitos
-- MAGIC
-- MAGIC - Você precisa ser **owner** do catálogo `dqx` ou ter `MANAGE` sobre o
-- MAGIC   schema `dqx.dqx_studio`.
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
-- MAGIC - **Uma vez**, depois do primeiro `databricks bundle deploy`.
-- MAGIC - Re-rodar é seguro: `GRANT` é idempotente.
-- MAGIC - Se a DQX Studio for redeployada em outro catálogo/schema, ajuste os
-- MAGIC   FQNs abaixo e atualize `var.dqx_catalog`/`var.dqx_schema` no target.yml.
-- MAGIC - Alternativa automática: o task `grant_warehouse_perms` do job
-- MAGIC   `rc18_end_to_end` reaplica esses mesmos grants a cada execução (útil
-- MAGIC   porque `bundle destroy` recria o SP do app). Este SQL é o equivalente
-- MAGIC   manual, para quando você quer conceder acesso sem rodar o job.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## GRANTs (somente leitura)

-- COMMAND ----------

-- Substitua <RC18_SP> pelo identificador real do service principal antes de rodar.
-- Backticks são necessários se o identificador contiver caracteres especiais.

GRANT USE CATALOG ON CATALOG dqx                                     TO `<RC18_SP>`;
GRANT USE SCHEMA  ON SCHEMA  dqx.dqx_studio                          TO `<RC18_SP>`;
GRANT SELECT      ON TABLE   dqx.dqx_studio.dq_quality_rules         TO `<RC18_SP>`;
GRANT SELECT      ON TABLE   dqx.dqx_studio.dq_validation_runs       TO `<RC18_SP>`;
GRANT SELECT      ON TABLE   dqx.dqx_studio.dq_metrics               TO `<RC18_SP>`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Verificação
-- MAGIC
-- MAGIC Confirme que os grants apareceram:

-- COMMAND ----------

SHOW GRANTS ON TABLE dqx.dqx_studio.dq_quality_rules;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC Após rodar, o app RC18 (página Críticas SCR / `/rules`) conseguirá ler as
-- MAGIC regras autoradas na DQX Studio sem erro de permissão.
