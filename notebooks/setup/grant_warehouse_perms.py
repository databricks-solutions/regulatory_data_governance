# Databricks notebook source
# MAGIC %md
# MAGIC # Grants post-deploy para o service principal do app
# MAGIC
# MAGIC Cada `bundle destroy + deploy` recria o SP do Databricks App com um
# MAGIC novo `client_id`. O ACL do warehouse e os grants cross-catalog em
# MAGIC `dqx_catalog.dqx_app.dq_quality_rules` ficam apontando pro SP antigo
# MAGIC (que foi deletado), então o app novo retorna HTTP 500 ("Error during
# MAGIC request to server" + INSUFFICIENT_PERMISSIONS) até alguém regrantar.
# MAGIC
# MAGIC Este notebook reaplica TODOS os grants necessários a CADA execução:
# MAGIC
# MAGIC   1. CAN_USE no warehouse `rc18-warehouse-dev` (via REST Permissions API)
# MAGIC   2. USE CATALOG + USE SCHEMA + SELECT/MODIFY em
# MAGIC      `dqx_catalog.dqx_app.dq_quality_rules` (via SQL GRANT)
# MAGIC
# MAGIC Idempotente — re-rodar concede de novo sem efeito colateral. Pré-req:
# MAGIC quem dispara o notebook precisa ser owner do warehouse e ter MANAGE em
# MAGIC `dqx_catalog`/`dqx_app` (o owner luiz.braz preenche os dois).

# COMMAND ----------

dbutils.widgets.text("app_name", "", "Nome do app (ex: rc18-starter-kit-dev)")
dbutils.widgets.text("warehouse_name", "", "Nome do warehouse (ex: rc18-warehouse-dev)")
dbutils.widgets.text("dqx_checks_table", "dqx_catalog.dqx_app.dq_quality_rules",
                     "FQN da tabela DQX Studio (catalog.schema.table)")

APP_NAME = dbutils.widgets.get("app_name")
WAREHOUSE_NAME = dbutils.widgets.get("warehouse_name")
DQX_CHECKS_TABLE = dbutils.widgets.get("dqx_checks_table")

if not APP_NAME or not WAREHOUSE_NAME:
    raise ValueError(
        "Widgets `app_name` e `warehouse_name` são obrigatórios. O orchestration "
        "job passa esses valores via base_parameters."
    )

# Quebra o FQN em catalog/schema/table pra montar os GRANTs corretamente.
_parts = DQX_CHECKS_TABLE.split(".")
if len(_parts) != 3:
    raise ValueError(f"dqx_checks_table deve ser catalog.schema.table; recebido: {DQX_CHECKS_TABLE!r}")
DQX_CATALOG, DQX_SCHEMA, _DQX_TABLE_NAME = _parts

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Resolve o SP a partir do app
app = w.apps.get(APP_NAME)
sp_client_id = getattr(app, "service_principal_client_id", None)
if not sp_client_id:
    raise RuntimeError(
        f"App {APP_NAME!r} não expõe service_principal_client_id — verifique se "
        "o deploy do app concluiu com sucesso."
    )
print(f"App SP client_id: {sp_client_id}")

# Resolve o warehouse pelo nome
warehouses = [h for h in w.warehouses.list() if h.name == WAREHOUSE_NAME]
if not warehouses:
    raise RuntimeError(f"Warehouse {WAREHOUSE_NAME!r} não encontrado no workspace.")
if len(warehouses) > 1:
    print(f"[WARN] {len(warehouses)} warehouses com nome {WAREHOUSE_NAME!r}; usando o primeiro.")
wh = warehouses[0]
print(f"Warehouse: id={wh.id} state={wh.state}")

# COMMAND ----------

# Usamos chamada direta à API de Permissions (genérica para qualquer
# object_type/object_id). Evita problemas de imports tipados entre versões
# diferentes do SDK e é o endpoint que `databricks warehouses update-permissions`
# também invoca. PATCH faz MERGE (adiciona/atualiza), não substitui o ACL.
resp = w.api_client.do(
    "PATCH",
    f"/api/2.0/permissions/warehouses/{wh.id}",
    body={
        "access_control_list": [
            {
                "service_principal_name": sp_client_id,
                "permission_level": "CAN_USE",
            }
        ]
    },
)
print(f"✓ Granted CAN_USE on warehouse {wh.id} to SP {sp_client_id}")

# COMMAND ----------

# Verificação: SP deve aparecer no ACL
perms = w.api_client.do("GET", f"/api/2.0/permissions/warehouses/{wh.id}")
acl = perms.get("access_control_list", []) if isinstance(perms, dict) else []
sp_entries = [
    a for a in acl
    if a.get("service_principal_name") == sp_client_id
]
assert sp_entries, f"Grant nao refletiu no ACL. Resposta GET: {perms}"
print(f"✓ Confirmado no ACL: {sp_entries[0].get('all_permissions')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. SQL GRANTs cross-catalog na tabela DQX Studio
# MAGIC
# MAGIC O SP do app precisa ler `dqx_catalog.dqx_app.dq_quality_rules` pra
# MAGIC popular o catálogo de regras de Críticas SCR. Como é cross-catalog
# MAGIC (RC18 vive em `rc18_catalog`), precisamos USE CATALOG/SCHEMA + SELECT.
# MAGIC O seed (`seed_dqx_checks`) também precisa de MODIFY pra fazer MERGE
# MAGIC da YAML; concedemos MODIFY também — ambos os papéis usam o mesmo SP
# MAGIC quando rodam no contexto do app/job do bundle.

# COMMAND ----------

# Mínimo necessário para o backend RC18 (4 grants base):
#   - USE CATALOG / USE SCHEMA — pré-requisito para qualquer SELECT em dqx_app
#   - SELECT/MODIFY em dq_quality_rules — catálogo de regras (lido por
#     /reference/criticas; escrito pelo task seed_dqx_checks)
# Para os outros endpoints (/validations/scr3040/results e /quality/dimensions)
# o backend lê das tabelas de execução do DQX Studio (validation_runs, metrics,
# quarantine_records). Concedemos SELECT em todas para o app conseguir popular
# Críticas SCR + Qualidade R.18 sem 500.
_DQX_READ_TABLES = ["dq_validation_runs", "dq_metrics", "dq_quarantine_records"]

grants = [
    f"GRANT USE CATALOG ON CATALOG `{DQX_CATALOG}` TO `{sp_client_id}`",
    f"GRANT USE SCHEMA  ON SCHEMA  `{DQX_CATALOG}`.`{DQX_SCHEMA}` TO `{sp_client_id}`",
    f"GRANT SELECT      ON TABLE   {DQX_CHECKS_TABLE} TO `{sp_client_id}`",
    f"GRANT MODIFY      ON TABLE   {DQX_CHECKS_TABLE} TO `{sp_client_id}`",
] + [
    f"GRANT SELECT      ON TABLE   `{DQX_CATALOG}`.`{DQX_SCHEMA}`.`{t}` TO `{sp_client_id}`"
    for t in _DQX_READ_TABLES
]
for g in grants:
    spark.sql(g)
    print(f"  ✓ {g}")

# Verificação rápida: SHOW GRANTS deve listar nosso SP
print("\nSHOW GRANTS:")
for row in spark.sql(f"SHOW GRANTS ON TABLE {DQX_CHECKS_TABLE}").collect():
    if sp_client_id in str(row):
        print(f"  {dict(row.asDict())}")
