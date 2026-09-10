-- GRANT Postgres: leitura de `dq_quality_rules` pelo SP do app RC18
-- ============================================================================
-- ⚠️ NÃO é notebook Databricks. É SQL **Postgres**, rodado contra o endpoint
-- Lakebase da DQX Studio — num notebook/SQL editor do Databricks falha na 1ª linha.
--
-- É manual porque privilégio de objeto no Postgres não é expressável em DABs nem
-- alcançável por GRANT de UC, e o task `grant_warehouse_perms` roda COMO o SP do
-- RC18, que não concede privilégio a si mesmo.
--
-- ⚠️ REAPLICAR após `bundle destroy` + `deploy`: o SP novo tem outro client id, e
-- os GRANTs abaixo passam a apontar para um role inexistente. Sintoma: Críticas
-- SCR vazia + `permission denied for table dq_quality_rules` no log do app.
--
-- QUEM RODA: quem tem `DATABRICKS_SUPERUSER` no branch (na prática, quem
-- deployou a Studio) — no Postgres só o dono das tabelas ou um superuser concede.
--
-- COMO RODAR:
--   1. client id do app:
--      databricks apps get r18-compliance-app-dev --profile <perfil> \
--        | grep -i service_principal_client_id
--   2. troque <RC18_APP_SP_CLIENT_ID> e rode:
--      databricks psql --project dqx-studio-db --branch dqx --profile <perfil> \
--        -- -d databricks_postgres -f notebooks/setup/grant_dqx_lakebase_access.sql
--   3. confira na tela Críticas SCR do app (ou clique "Re-verificar" no aviso).
-- ============================================================================

-- Aspas duplas obrigatórias: o nome do role é um UUID.

-- Sem USAGE no schema, o SELECT falha mesmo com grant na tabela.
GRANT USAGE ON SCHEMA dqx_studio TO "<RC18_APP_SP_CLIENT_ID>";
GRANT SELECT ON TABLE dqx_studio.dq_quality_rules TO "<RC18_APP_SP_CLIENT_ID>";

-- OPCIONAL — trilha de auditoria das regras (o RC18 ainda não consome).
-- GRANT SELECT ON TABLE dqx_studio.dq_quality_rules_history TO "<RC18_APP_SP_CLIENT_ID>";

-- Nada mais é concedido: o resto (`dq_app_settings`, `dq_role_mappings`,
-- `dq_comments`, `dq_schedule_*`) é estado interno da Studio, e nenhuma escrita
-- é concedida em lugar nenhum (o cliente do app já abre a sessão read-only).

-- Verificação: deve listar SELECT para o client id do SP.
SELECT grantee, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'dqx_studio'
  AND table_name = 'dq_quality_rules';
