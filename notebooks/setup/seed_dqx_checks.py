# Databricks notebook source
# MAGIC %md
# MAGIC # Seed RC18 rules into DQX Studio's `dq_quality_rules`
# MAGIC
# MAGIC O DQX Studio (app `databrickslabs/dqx`) lê de uma tabela externa
# MAGIC `{DQX_CATALOG}.{DQX_SCHEMA}.dq_quality_rules` cujo schema é
# MAGIC **incompatível** com o `dqx_checks` canônico do `DQEngine.save_checks`:
# MAGIC armazena a regra como JSON blob em `checks`, com versionamento e
# MAGIC `status`. Este notebook lê o YAML canônico de
# MAGIC `pipelines/silver/dqx_checks/*.yml`, converte cada regra para o shape
# MAGIC do Studio e faz `MERGE` idempotente.
# MAGIC
# MAGIC **Pré-requisito (UMA vez):** rodar `notebooks/setup/grant_dqx_studio_access.sql`
# MAGIC como admin do catálogo `dqx_catalog` para conceder permissões cross-catalog
# MAGIC ao service principal do bundle.

# COMMAND ----------

# MAGIC %pip install databricks-labs-dqx==0.14.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text(
    "dqx_checks_table",
    "dqx_catalog.dqx_app.dq_quality_rules",
    "FQN da tabela `dq_quality_rules` da DQX Studio (catalog.schema.table)",
)
dbutils.widgets.text(
    "checks_dir",
    "",
    "Caminho absoluto para o diretório com *.yml de regras DQX",
)

DQX_CHECKS_TABLE = dbutils.widgets.get("dqx_checks_table")
CHECKS_DIR = dbutils.widgets.get("checks_dir")

if not CHECKS_DIR:
    raise ValueError(
        "Widget `checks_dir` é obrigatório. O setup job passa "
        "${workspace.file_path}/pipelines/silver/dqx_checks."
    )

print(f"Target: {DQX_CHECKS_TABLE}")
print(f"YAML source: {CHECKS_DIR}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Verificar acesso à tabela externa
# MAGIC
# MAGIC Falha loudly se a tabela não existir ou se o SP do job não tem permissão.
# MAGIC NÃO criamos a tabela — ela é propriedade da DQX Studio.

# COMMAND ----------

try:
    spark.sql(f"DESCRIBE TABLE {DQX_CHECKS_TABLE}").limit(1).collect()
except Exception as e:  # pragma: no cover — failure path
    raise RuntimeError(
        f"Não foi possível acessar {DQX_CHECKS_TABLE}. "
        "Confirme (1) que a DQX Studio está deployada e a tabela existe, e "
        "(2) que o service principal deste job tem USE CATALOG/SCHEMA + "
        "SELECT/MODIFY na tabela. Veja "
        "notebooks/setup/grant_dqx_studio_access.sql."
    ) from e

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Descobrir YAMLs e carregar via DQX
# MAGIC
# MAGIC `dq.load_checks` faz o parse + Variable Substitution (`{{ catalog }}`).
# MAGIC O resultado é uma lista de dicts no shape **canônico** da DQX library
# MAGIC — não no shape do Studio. Convertemos abaixo.

# COMMAND ----------

from pathlib import Path

checks_root = Path(CHECKS_DIR)
if not checks_root.is_dir():
    raise FileNotFoundError(
        f"checks_dir {CHECKS_DIR!r} não existe ou não é diretório. "
        "Confirme `sync.paths` do bundle inclui `pipelines` e que o setup job "
        "usa `${workspace.file_path}/pipelines/silver/dqx_checks`."
    )

yaml_files = sorted(
    p for p in checks_root.iterdir()
    if p.is_file() and p.suffix.lower() in (".yml", ".yaml")
)

print(f"Encontrados {len(yaml_files)} YAML(s):")
for p in yaml_files:
    print(f"  - {p.name}")

if not yaml_files:
    dbutils.notebook.exit("Nenhum YAML encontrado — nada para seed.")

# COMMAND ----------

from databricks.labs.dqx.engine import DQEngine
from databricks.labs.dqx.config import FileChecksStorageConfig
from databricks.sdk import WorkspaceClient

dq = DQEngine(WorkspaceClient())

# Extrai catalog do FQN da tabela para resolver placeholders {{ catalog }} no YAML.
# Catalog aqui se refere ao catálogo de DADOS (rc18_catalog), não onde a tabela
# de regras vive. Pegamos do RC18 catalog via env (DATABRICKS_CATALOG) ou
# convenção do bundle.
import os
DATA_CATALOG = os.environ.get("DATABRICKS_CATALOG", "rc18_catalog")

all_checks: list[dict] = []
for yaml_path in yaml_files:
    print(f"\nCarregando {yaml_path.name}...")
    checks = dq.load_checks(
        config=FileChecksStorageConfig(location=str(yaml_path)),
        variables={"catalog": DATA_CATALOG},
    )
    print(f"  parsed {len(checks)} check(s)")
    all_checks.extend(checks)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Converter para o shape do Studio + MERGE idempotente
# MAGIC
# MAGIC Shape destino (`dq_quality_rules`):
# MAGIC
# MAGIC | Coluna | Origem |
# MAGIC |---|---|
# MAGIC | `rule_id` | `uuid.uuid5(NAMESPACE_OID, f"rc18:{run_config_name}:{check.name}")` — determinístico |
# MAGIC | `table_fqn` | Derivado de `run_config_name` (silver_3040_clientes → `<catalog>.silver.scr3040_clientes`) |
# MAGIC | `checks` | `json.dumps(check_dict)` — preserva tudo |
# MAGIC | `version` | 1 no insert; +1 só se conteúdo mudou |
# MAGIC | `status` | `'active'` |
# MAGIC | `source` | `'rc18-seed'` — marca origem; permite identificar nossas regras |

# COMMAND ----------

import json
import uuid

# Mapping run_config_name → table FQN. Mantém em sync com as 4 regras iniciais
# e qualquer regra futura adicionada via YAML deve seguir esta convenção.
_RUN_CFG_TO_TABLE = {
    "silver_3040_clientes": f"{DATA_CATALOG}.silver.scr3040_clientes",
    "silver_3040_operacoes": f"{DATA_CATALOG}.silver.scr3040_operacoes",
    "silver_3040_garantias": f"{DATA_CATALOG}.silver.scr3040_garantias",
    "silver_3040_vencimentos": f"{DATA_CATALOG}.silver.scr3040_vencimentos",
    "silver_3040_cont_4966": f"{DATA_CATALOG}.silver.scr3040_cont_4966",
    "silver_3050": f"{DATA_CATALOG}.silver.scr3050",
}

# Namespace fixo para UUIDv5. Trocar este UUID invalida todos os rule_ids
# existentes (e cria duplicatas no próximo MERGE). NÃO MUDE sem migração.
_RC18_NAMESPACE = uuid.UUID("4f7e9b6a-1d5c-4e8a-9b3d-2c1e6f4a8b7c")

staged_rows: list[dict] = []
for chk in all_checks:
    if not isinstance(chk, dict):
        raise TypeError(
            f"Esperado dict de check, recebido {type(chk).__name__}. "
            "Verifique a versão do DQX (>=0.14.0 retorna dicts)."
        )
    run_cfg = chk.get("run_config_name")
    name = chk.get("name")
    if not run_cfg or not name:
        raise ValueError(
            f"Check sem run_config_name ou name: {json.dumps(chk)[:200]}. "
            "Spec §1.1 (08_dqx_app_integration.md) exige ambos."
        )
    table_fqn = _RUN_CFG_TO_TABLE.get(run_cfg)
    if not table_fqn:
        raise ValueError(
            f"run_config_name {run_cfg!r} não mapeado para uma table_fqn. "
            f"Atualize _RUN_CFG_TO_TABLE em seed_dqx_checks.py."
        )
    rule_id = str(uuid.uuid5(_RC18_NAMESPACE, f"rc18:{run_cfg}:{name}"))
    # IMPORTANT: DQX Studio armazena `checks` como JSON ARRAY (mesmo para uma
    # única regra). Empacotamos `chk` em `[chk]` para casar com o shape esperado
    # pela Studio — senão a UI ignora silenciosamente as linhas do RC18.
    # `status='approved'` segue o vocabulário do workflow padrão da Studio
    # (rules-aware UI filtra por approved + active).
    staged_rows.append({
        "rule_id":    rule_id,
        "table_fqn":  table_fqn,
        "checks":     json.dumps([chk], ensure_ascii=False, sort_keys=True),
        "status":     "approved",
        "source":     "rc18-seed",
        "created_by": "system@rc18-seed",
        "updated_by": "system@rc18-seed",
    })

print(f"\n{len(staged_rows)} regra(s) prontas para MERGE:")
for r in staged_rows:
    print(f"  - {r['rule_id'][:8]}…  {r['table_fqn']}  ({r['source']})")

# COMMAND ----------

# Cria DataFrame temporário com a staging. Nomes/types alinhados com o schema
# do Studio (rule_id, table_fqn, checks, status, source, created_by, updated_by).
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType

_STAGE_SCHEMA = StructType([
    StructField("rule_id", StringType(), False),
    StructField("table_fqn", StringType(), False),
    StructField("checks", StringType(), False),
    StructField("status", StringType(), False),
    StructField("source", StringType(), False),
    StructField("created_by", StringType(), False),
    StructField("updated_by", StringType(), False),
])

staged_df = spark.createDataFrame(staged_rows, schema=_STAGE_SCHEMA)
staged_df.createOrReplaceTempView("_rc18_dqx_stage")

# MERGE idempotente:
#   - MATCH por rule_id (NÃO por (table_fqn, rule_id) — rule_id é único por convenção)
#   - UPDATE só se conteúdo mudou (evita inflar version desnecessariamente)
#   - INSERT cria com version=1, created_at=current_timestamp()
#   - NÃO toca em regras com outro `source` (criadas pelo usuário no Studio)
merge_sql = f"""
MERGE INTO {DQX_CHECKS_TABLE} AS tgt
USING _rc18_dqx_stage AS src
ON tgt.rule_id = src.rule_id

WHEN MATCHED AND tgt.source = 'rc18-seed' AND tgt.checks <> src.checks THEN
  UPDATE SET
    tgt.table_fqn  = src.table_fqn,
    tgt.checks     = src.checks,
    tgt.status     = src.status,
    tgt.source     = src.source,
    tgt.updated_by = src.updated_by,
    tgt.updated_at = current_timestamp(),
    tgt.version    = tgt.version + 1

WHEN NOT MATCHED THEN
  INSERT (rule_id, table_fqn, checks, version, status, source,
          created_by, created_at, updated_by, updated_at)
  VALUES (src.rule_id, src.table_fqn, src.checks, 1, src.status, src.source,
          src.created_by, current_timestamp(),
          src.updated_by, current_timestamp())
"""

result_df = spark.sql(merge_sql)
print("MERGE concluído.")
try:
    metrics = result_df.collect()[0].asDict()
    print(f"  rows affected: {metrics}")
except Exception:
    pass  # nem todo runtime expõe metrics de MERGE

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Summary

# COMMAND ----------

summary_df = spark.sql(f"""
SELECT
  source,
  COUNT(*) AS rules,
  MIN(version) AS min_version,
  MAX(version) AS max_version,
  MAX(updated_at) AS last_update
FROM {DQX_CHECKS_TABLE}
WHERE source = 'rc18-seed'
GROUP BY source
""")
summary_df.show(truncate=False)

print("=" * 60)
rc18_count = spark.sql(
    f"SELECT COUNT(*) AS n FROM {DQX_CHECKS_TABLE} WHERE source='rc18-seed'"
).collect()[0]["n"]
total_count = spark.sql(
    f"SELECT COUNT(*) AS n FROM {DQX_CHECKS_TABLE}"
).collect()[0]["n"]
print(f"RC18-seeded rules:      {rc18_count}")
print(f"Total rules in table:   {total_count}")
print("=" * 60)
