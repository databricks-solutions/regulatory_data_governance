# Databricks notebook source
# MAGIC %md
# MAGIC # Grants post-deploy para o service principal do app
# MAGIC
# MAGIC Cada `bundle destroy + deploy` recria o SP do Databricks App com um
# MAGIC novo `client_id`. O ACL do warehouse e os grants cross-catalog nas tabelas
# MAGIC da DQX Studio ficam apontando pro SP antigo (que foi deletado), então o app
# MAGIC novo retorna HTTP 500 ("Error during request to server" +
# MAGIC INSUFFICIENT_PERMISSIONS) até alguém regrantar.
# MAGIC
# MAGIC Este notebook reaplica os grants de **Unity Catalog** a CADA execução:
# MAGIC
# MAGIC   1. CAN_USE no warehouse `rc18-warehouse-dev` (via REST Permissions API)
# MAGIC   2. USE CATALOG + USE SCHEMA no catálogo/schema da DQX Studio + SELECT em
# MAGIC      `dq_validation_runs` / `dq_metrics` / `dq_quarantine_records`
# MAGIC      (o RC18 apenas LÊ as tabelas da DQX Studio)
# MAGIC   3. USE CATALOG no catálogo do deployment + SELECT nos schemas de dados
# MAGIC      (`silver`, `reference`, `bronze`, `gold`) + SELECT/MODIFY na
# MAGIC      tabela `governance.incidents` (necessário para criação de
# MAGIC      incidentes via POST /governance/incidents)
# MAGIC   4. GRANT REVERSO — USE CATALOG + SELECT em `{silver,gold,reference}` do
# MAGIC      catálogo do deployment para o SP da DQX Studio (o `run_as` dos jobs
# MAGIC      de validação), para que os checks com subquery resolvam. Só aplicado
# MAGIC      se o widget `dqx_studio_sp` for informado.
# MAGIC
# MAGIC ⚠️ **O grant da tabela de REGRAS não está aqui e NÃO é automatizável.**
# MAGIC `dq_quality_rules` saiu do Unity Catalog na DQX 0.15/0.16 e vive em Lakebase
# MAGIC Postgres. Privilégio de objeto no Postgres precisa ser concedido pelo dono
# MAGIC das tabelas (o SP da Studio), e este notebook roda como o SP do RC18 — que
# MAGIC não pode conceder privilégio a si mesmo. Ou seja: exatamente o problema do
# MAGIC "client id novo a cada destroy" que este notebook resolve para o UC continua
# MAGIC MANUAL no lado Lakebase, e precisa ser refeito a cada destroy+deploy. Ver
# MAGIC `notebooks/setup/grant_dqx_lakebase_access.sql`.
# MAGIC
# MAGIC Idempotente — re-rodar concede de novo sem efeito colateral. Pré-req:
# MAGIC quem dispara o notebook precisa ser owner do warehouse e ter USE/SELECT no
# MAGIC catálogo/schema da DQX Studio (widgets `dqx_catalog`/`dqx_schema`, defaults
# MAGIC `dqx`/`dqx_studio`).
# MAGIC
# MAGIC ⚠️ O catálogo vem do widget `catalog` (obrigatório) — NUNCA hardcoded. Com
# MAGIC vários deployments no mesmo workspace, um catálogo fixo aqui concederia
# MAGIC acesso ao catálogo do deployment ERRADO: o app novo ficaria sem permissão
# MAGIC no seu próprio catálogo e o SP da DQX Studio marcaria 100% de violação nos
# MAGIC checks com subquery, silenciosamente. Os nomes dos schemas seguem os
# MAGIC defaults (`bronze`/`silver`/`gold`/`reference`/`governance`); se o target
# MAGIC sobrescrever `var.schema_*`, o GRANT falha alto com SCHEMA_NOT_FOUND.

# COMMAND ----------

dbutils.widgets.text("app_name", "", "Nome do app (ex: rc18-starter-kit-dev)")
dbutils.widgets.text("warehouse_name", "", "Nome do warehouse (ex: rc18-warehouse-dev)")
# Catálogo DESTE deployment. Sem default de propósito: um default silencioso é o
# que faria um segundo deployment grantar no catálogo do primeiro.
dbutils.widgets.text("catalog", "", "Catálogo do deployment (ex: rc18_catalog)")
# Catálogo/schema DELTA da DQX Studio — onde vivem as tabelas de EXECUÇÃO. A
# tabela de regras NÃO entra aqui: está no Lakebase Postgres, cujo grant é manual
# (grant_dqx_lakebase_access.sql).
dbutils.widgets.text("dqx_catalog", "dqx", "Catálogo da DQX Studio")
dbutils.widgets.text("dqx_schema", "dqx_studio", "Schema da DQX Studio")
# Service principal da DQX Studio (o run_as dos jobs de validação). Precisa LER o
# catálogo deste deployment para os checks com subquery (domínio/referência/
# batimento + o filter de escopo mensal dt_base=(SELECT max…)) resolverem. Vazio =
# pula o grant reverso (mas esses checks falharão com "invalid check filter" /
# 100% de violação). Ver grant_dqx_studio_access.sql.
dbutils.widgets.text("dqx_studio_sp", "", "SP da DQX Studio (run_as dos jobs de validação)")

APP_NAME = dbutils.widgets.get("app_name")
WAREHOUSE_NAME = dbutils.widgets.get("warehouse_name")
CATALOG = dbutils.widgets.get("catalog")
DQX_CATALOG = dbutils.widgets.get("dqx_catalog")
DQX_SCHEMA = dbutils.widgets.get("dqx_schema")
DQX_STUDIO_SP = dbutils.widgets.get("dqx_studio_sp")

if not APP_NAME or not WAREHOUSE_NAME or not CATALOG:
    raise ValueError(
        "Widgets `app_name`, `warehouse_name` e `catalog` são obrigatórios. O "
        "orchestration job passa esses valores via base_parameters."
    )
if not DQX_CATALOG or not DQX_SCHEMA:
    raise ValueError("Widgets `dqx_catalog` e `dqx_schema` são obrigatórios.")

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
# MAGIC ## 2. SQL GRANTs cross-catalog nas tabelas Delta da DQX Studio
# MAGIC
# MAGIC O SP do app precisa ler `dq_validation_runs` / `dq_metrics` pra
# MAGIC alimentar os KPIs de qualidade e as validações. Como é cross-catalog
# MAGIC (o RC18 vive no catálogo do deployment), precisamos USE CATALOG/SCHEMA
# MAGIC + SELECT.
# MAGIC Apenas leitura: as regras são autoradas na DQX Studio, não pelo RC18 —
# MAGIC nenhum MODIFY é concedido nas tabelas da Studio.

# COMMAND ----------

# Grants no catálogo DQX (tabelas DELTA de execução do DQX Studio):
#   - USE CATALOG / USE SCHEMA — pré-requisito para qualquer SELECT no schema DQX
#   - SELECT em validation_runs/metrics/quarantine_records — feeds para os
#     endpoints /validations/*/results e /quality/dimensions
# `dq_quality_rules` NÃO está aqui: vive no Lakebase Postgres desde a DQX
# 0.15/0.16, e grantar aqui falharia com TABLE_OR_VIEW_NOT_FOUND. Ver
# notebooks/setup/grant_dqx_lakebase_access.sql.
_DQX_READ_TABLES = ["dq_validation_runs", "dq_metrics", "dq_quarantine_records"]

# Grants no catálogo do deployment (catálogo de DADOS — silver/bronze/gold/
# reference) + tabela mutável governance.incidents. O app SP precisa ler
# silver/reference (para joins e enriquecimentos no backend) e ler+escrever em
# governance. Granularidade por TABELA na governance pra não conceder MODIFY ao
# schema inteiro acidentalmente.
_RC18_READ_SCHEMAS = ["silver", "reference", "bronze", "gold"]

grants = [
    # catálogo DQX (DQX Studio) — pré-requisitos de acesso ao schema (SELECT only;
    # o RC18 apenas lê as tabelas da Studio).
    f"GRANT USE CATALOG ON CATALOG `{DQX_CATALOG}` TO `{sp_client_id}`",
    f"GRANT USE SCHEMA  ON SCHEMA  `{DQX_CATALOG}`.`{DQX_SCHEMA}` TO `{sp_client_id}`",
] + [
    f"GRANT SELECT      ON TABLE   `{DQX_CATALOG}`.`{DQX_SCHEMA}`.`{t}` TO `{sp_client_id}`"
    for t in _DQX_READ_TABLES
] + [
    # catálogo do deployment — USE CATALOG raiz + read em schemas de dados
    f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{sp_client_id}`",
] + [
    cmd.format(cat=CATALOG, s=s, sp=sp_client_id)
    for s in _RC18_READ_SCHEMAS
    for cmd in (
        "GRANT USE SCHEMA ON SCHEMA `{cat}`.`{s}` TO `{sp}`",
        "GRANT SELECT     ON SCHEMA `{cat}`.`{s}` TO `{sp}`",
    )
] + [
    # governance.incidents — SP precisa ler (Gestão de Incidentes) E escrever
    # (POST /governance/incidents da Críticas SCR drilldown). MODIFY restrito
    # à TABELA, não ao schema inteiro.
    f"GRANT USE SCHEMA ON SCHEMA `{CATALOG}`.`governance` TO `{sp_client_id}`",
    f"GRANT SELECT     ON TABLE  `{CATALOG}`.`governance`.`incidents` TO `{sp_client_id}`",
    f"GRANT MODIFY     ON TABLE  `{CATALOG}`.`governance`.`incidents` TO `{sp_client_id}`",
] + [
    # governance.<cadoc_documentos|cadoc_tabelas|regra_vinculos> — tabelas de
    # vínculo Regra↔CADOC↔Dimensão, escritas pela tela /linking (routers/linking.py).
    # SELECT+MODIFY por TABELA (mesma granularidade de incidents).
    cmd.format(cat=CATALOG, t=t, sp=sp_client_id)
    for t in ("cadoc_documentos", "cadoc_tabelas", "regra_vinculos")
    for cmd in (
        "GRANT SELECT ON TABLE `{cat}`.`governance`.`{t}` TO `{sp}`",
        "GRANT MODIFY ON TABLE `{cat}`.`governance`.`{t}` TO `{sp}`",
    )
]
for g in grants:
    spark.sql(g)
    print(f"  ✓ {g}")

# Verificação rápida: SHOW GRANTS deve listar nosso SP
print("\nSHOW GRANTS:")
for row in spark.sql(
    f"SHOW GRANTS ON TABLE `{DQX_CATALOG}`.`{DQX_SCHEMA}`.`dq_validation_runs`"
).collect():
    if sp_client_id in str(row):
        print(f"  {dict(row.asDict())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. GRANT REVERSO: o SP da DQX Studio precisa LER o catálogo do deployment
# MAGIC
# MAGIC Os jobs de validação do DQX Studio rodam como o SP da PRÓPRIA DQX Studio
# MAGIC (o `run_as`/creator do job — uma identidade DIFERENTE do SP do app RC18
# MAGIC acima). Todo check com subquery — os de domínio
# MAGIC (`IN (SELECT … FROM reference.v_dom_3040_*)`), integridade referencial
# MAGIC (`EXISTS … silver.scr3040_clientes`), batimento COSIF
# MAGIC (`NOT IN reference.v_recon_status_bloqueante`) E o `filter` de escopo mensal
# MAGIC (`dt_base = (SELECT max(dt_base) …)`) — exige que esse SP tenha
# MAGIC USE CATALOG + SELECT no catálogo deste deployment. SEM isso, a subquery não
# MAGIC resolve e o DQX marca 100% das linhas como violação / "invalid check filter"
# MAGIC — SILENCIOSO (o run reporta SUCCESS). Este grant é reaplicado a cada
# MAGIC execução do job, igual aos demais, para sobreviver a `destroy + deploy`.
# MAGIC
# MAGIC Com a Studio COMPARTILHADA entre deployments, o mesmo SP acaba com leitura
# MAGIC em vários catálogos — esperado: é o que permite os checks de cada
# MAGIC deployment rodarem. O isolamento das REGRAS é feito no app, por catálogo
# MAGIC (`app/backend/dqx_rules.py`), não por permissão.

# COMMAND ----------

if not DQX_STUDIO_SP:
    print("[SKIP] Widget `dqx_studio_sp` vazio — grant reverso NÃO aplicado. Os checks "
          "com subquery (domínio/referência/escopo mensal) falharão com "
          "'invalid check filter'. Defina o SP da DQX Studio no target.yml para "
          "habilitar, ou rode grant_dqx_studio_access.sql (seção GRANT REVERSO).")
else:
    print(f"DQX Studio SP: {DQX_STUDIO_SP}")
    reverse_grants = [
        f"GRANT USE CATALOG ON CATALOG `{CATALOG}` TO `{DQX_STUDIO_SP}`",
    ] + [
        cmd.format(cat=CATALOG, s=s, sp=DQX_STUDIO_SP)
        for s in ("silver", "gold", "reference")
        for cmd in (
            "GRANT USE SCHEMA ON SCHEMA `{cat}`.`{s}` TO `{sp}`",
            "GRANT SELECT     ON SCHEMA `{cat}`.`{s}` TO `{sp}`",
        )
    ]
    for g in reverse_grants:
        spark.sql(g)
        print(f"  ✓ {g}")
