-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Cross-catalog GRANTs entre o RC18 e a DQX Studio (BIDIRECIONAL)
-- MAGIC
-- MAGIC São DOIS grants cross-catalog, em direções opostas — ambos necessários:
-- MAGIC   1. **RC18 → DQX** (abaixo): o SP do app RC18 LÊ `dqx.dqx_studio.*` para
-- MAGIC      popular o catálogo de Críticas SCR, KPIs e validações.
-- MAGIC   2. **DQX → RC18** (mais abaixo, seção "GRANT REVERSO"): o SP da DQX Studio
-- MAGIC      LÊ `rc18_catalog.{silver,gold,reference}` para os jobs de validação
-- MAGIC      resolverem os checks de domínio/referência. **Sem ele, esses checks dão
-- MAGIC      falso-positivo silencioso de 100%** — ver a seção para o porquê.
-- MAGIC
-- MAGIC As regras em si são criadas pelo usuário na própria DQX Studio — o RC18 não
-- MAGIC faz mais seed automático de regras.
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
-- MAGIC ## GRANT REVERSO (obrigatório): o SP da DQX Studio precisa LER `rc18_catalog`
-- MAGIC
-- MAGIC **Por que:** os jobs de validação da DQX Studio rodam como o service
-- MAGIC principal da PRÓPRIA DQX Studio (o `run_as` do job, NÃO o SP do RC18). Esse
-- MAGIC SP lê a tabela-alvo do run via uma view temporária, mas os checks que
-- MAGIC referenciam OUTRAS tabelas do `rc18_catalog` — os de DOMÍNIO
-- MAGIC (`IN (SELECT valor_codigo FROM reference.v_dom_3040_*)`), a integridade
-- MAGIC referencial (`EXISTS ... silver.scr3040_clientes`) e o batimento COSIF
-- MAGIC (`NOT IN reference.v_recon_status_bloqueante`) — precisam que esse SP tenha
-- MAGIC `USE CATALOG` + `SELECT` em `rc18_catalog`.
-- MAGIC
-- MAGIC **⚠️ Sintoma se faltar (silencioso e perigoso):** os checks de domínio/
-- MAGIC referência marcam **100% das linhas como violação** (a subquery não resolve
-- MAGIC por falta de permissão → expressão vira NULL → tudo falha). O run reporta
-- MAGIC SUCCESS, então passa despercebido. `foreign_key` falha explícito com
-- MAGIC `INSUFFICIENT_PERMISSIONS: USE CATALOG on rc18_catalog`.
-- MAGIC
-- MAGIC **Como achar o SP da DQX Studio** (é o `run_as` dos jobs dela — pode diferir
-- MAGIC do `service_principal_client_id` do app):
-- MAGIC
-- MAGIC   ```bash
-- MAGIC   # pegue um run_id recente de validação na UI (Runs History) e:
-- MAGIC   databricks api get "/api/2.1/jobs/runs/get?run_id=<RUN_ID>" \
-- MAGIC     | python3 -c "import sys,json;print(json.load(sys.stdin).get('creator_user_name'))"
-- MAGIC   ```
-- MAGIC
-- MAGIC Substitua `<DQX_STUDIO_SP>` pelo identificador retornado.

-- COMMAND ----------

GRANT USE CATALOG ON CATALOG  rc18_catalog                  TO `<DQX_STUDIO_SP>`;
GRANT USE SCHEMA  ON SCHEMA   rc18_catalog.silver           TO `<DQX_STUDIO_SP>`;
GRANT SELECT      ON SCHEMA   rc18_catalog.silver           TO `<DQX_STUDIO_SP>`;
GRANT USE SCHEMA  ON SCHEMA   rc18_catalog.gold             TO `<DQX_STUDIO_SP>`;
GRANT SELECT      ON SCHEMA   rc18_catalog.gold             TO `<DQX_STUDIO_SP>`;
GRANT USE SCHEMA  ON SCHEMA   rc18_catalog.reference        TO `<DQX_STUDIO_SP>`;
GRANT SELECT      ON SCHEMA   rc18_catalog.reference        TO `<DQX_STUDIO_SP>`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## GRANT BYOL (obrigatório para a Linhagem gravável): o SP do app precisa
-- MAGIC ## gerenciar External Metadata / External Lineage
-- MAGIC
-- MAGIC **Por que:** a página **Linhagem** do app RC18 virou uma superfície de
-- MAGIC gestão (read/write) sobre as APIs `external-metadata` / `external-lineage`
-- MAGIC do Unity Catalog. As escritas (criar/editar/remover objeto externo e
-- MAGIC relacionamento de linhagem) rodam como o **service principal do app**.
-- MAGIC
-- MAGIC Privilégios necessários para o SP do app:
-- MAGIC   - `CREATE EXTERNAL METADATA` no **metastore** — criar objetos externos;
-- MAGIC   - `MODIFY` no objeto externo — definir relacionamentos a partir dele
-- MAGIC     (o owner recebe MODIFY automaticamente ao criar);
-- MAGIC   - nas tabelas UC alvo de relacionamento: `SELECT` (relacionamento
-- MAGIC     DOWNSTREAM, ex. gold→validador) e `MODIFY` (relacionamento UPSTREAM,
-- MAGIC     ex. fonte→bronze). O SP do app já costuma ter esses no `rc18_catalog`.
-- MAGIC
-- MAGIC **Sintoma se faltar:** o formulário "Novo metadado externo" / "Novo
-- MAGIC relacionamento" retorna HTTP 403 e o app mostra a mensagem
-- MAGIC "O service principal do app não tem privilégio para gravar metadados/
-- MAGIC linhagem externa…". A LEITURA do grafo (visualização) não exige esses
-- MAGIC grants — só a escrita.
-- MAGIC
-- MAGIC Descubra o SP do app com:
-- MAGIC   ```bash
-- MAGIC   databricks apps get r18-compliance-app-dev --profile <perfil> \
-- MAGIC     | grep -i "service_principal"
-- MAGIC   ```
-- MAGIC Substitua `<RC18_APP_SP>` abaixo. `CREATE EXTERNAL METADATA` é concedido no
-- MAGIC metastore (não há FQN — é privilégio de metastore).

-- COMMAND ----------

GRANT CREATE EXTERNAL METADATA ON METASTORE TO `<RC18_APP_SP>`;
-- Escrita de relacionamentos que apontam para tabelas do rc18_catalog:
GRANT USE CATALOG ON CATALOG rc18_catalog                   TO `<RC18_APP_SP>`;
GRANT MODIFY      ON SCHEMA  rc18_catalog.bronze            TO `<RC18_APP_SP>`;
GRANT MODIFY      ON SCHEMA  rc18_catalog.gold              TO `<RC18_APP_SP>`;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Verificação
-- MAGIC
-- MAGIC Confirme que os grants apareceram:

-- COMMAND ----------

SHOW GRANTS ON TABLE dqx.dqx_studio.dq_quality_rules;

-- COMMAND ----------

SHOW GRANTS ON CATALOG rc18_catalog;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC Após rodar, o app RC18 (página Críticas SCR / `/rules`) conseguirá ler as
-- MAGIC regras autoradas na DQX Studio sem erro de permissão, E os checks de domínio/
-- MAGIC referência/batimento executarão corretamente (sem falso-positivo de 100%).
