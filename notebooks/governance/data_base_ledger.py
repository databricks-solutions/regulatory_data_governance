# Databricks notebook source
# MAGIC %md
# MAGIC # Histórico de data-base por tabela → `governance.data_base_ledger`
# MAGIC
# MAGIC O run da DQX não registra qual data-base avaliou: o `filter` dos checks lê
# MAGIC `max(dt_base)` na hora. Este notebook guarda, por tabela de `cadoc_tabelas`
# MAGIC e por mês, uma impressão digital do conteúdo com o intervalo em que valeu
# MAGIC (`valid_from`/`valid_to`). O app cruza o início de cada run com esse
# MAGIC intervalo (`app/backend/data_base.py`).
# MAGIC
# MAGIC Linha nova só quando o CONTEÚDO do mês muda: a silver é gravada com
# MAGIC `overwrite` a cada execução, então versão Delta nova não significa dado novo.
# MAGIC Colunas técnicas (`_*`, `pipeline_run_id`) ficam fora da impressão digital.
# MAGIC
# MAGIC Incremental pelo `DESCRIBE HISTORY`: processa as versões ainda não vistas, com
# MAGIC o horário do commit como `valid_from`. Na primeira execução isso vira carga
# MAGIC inicial, limitada ao que o VACUUM ainda não apagou. Tabela sem histórico
# MAGIC (materialized view do modo SDP) usa o estado atual com o horário de agora.

# COMMAND ----------

from datetime import datetime, timezone

from pyspark.sql import functions as F
from pyspark.sql import types as T

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("governance_schema", "governance")
# Teto de versões lidas por tabela e por execução — limita o custo da carga inicial.
dbutils.widgets.text("max_versions", "10")

CATALOG = dbutils.widgets.get("catalog")
GOV_SCHEMA = dbutils.widgets.get("governance_schema")
MAX_VERSIONS = int(dbutils.widgets.get("max_versions"))
LEDGER = f"{CATALOG}.{GOV_SCHEMA}.data_base_ledger"

# Mesmo DDL de notebooks/setup/setup_reference_tables.py (8.4) — mude os dois juntos.
# Repetido aqui para o job `gold` sozinho não falhar num deployment anterior a ela.
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {LEDGER} (
    table_fqn          STRING NOT NULL,
    data_base_month    STRING NOT NULL,
    dt_base_max        STRING,
    row_count          BIGINT,
    content_hash       STRING,
    delta_version      BIGINT,
    last_seen_version  BIGINT,
    valid_from         TIMESTAMP NOT NULL,
    valid_to           TIMESTAMP,
    recorded_at        TIMESTAMP
)
USING DELTA
COMMENT 'Conteúdo de cada data-base (mês) por tabela ao longo do tempo. Mapeia runs da DQX para a data-base avaliada.'
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# COMMAND ----------

# Operações que não mudam dado: ler essas versões só custaria tempo.
_SKIP_OPS = {
    "OPTIMIZE", "VACUUM START", "VACUUM END", "SET TBLPROPERTIES", "UNSET TBLPROPERTIES",
    "ADD CONSTRAINT", "DROP CONSTRAINT", "CHANGE COLUMN", "UPGRADE PROTOCOL",
    "COMPUTE STATS", "ANALYZE STATS", "ROW TRACKING BACKFILL",
}
_TECH_COLS = {"pipeline_run_id"}

_SCHEMA = T.StructType([
    T.StructField("table_fqn", T.StringType(), False),
    T.StructField("data_base_month", T.StringType(), False),
    T.StructField("dt_base_max", T.StringType(), True),
    T.StructField("row_count", T.LongType(), True),
    T.StructField("content_hash", T.StringType(), True),
    T.StructField("delta_version", T.LongType(), True),
    T.StructField("last_seen_version", T.LongType(), True),
    T.StructField("valid_from", T.TimestampType(), False),
    T.StructField("valid_to", T.TimestampType(), True),
    T.StructField("recorded_at", T.TimestampType(), True),
])


def _month(c):
    """Mês `yyyy-MM` de DATE, `yyyy-MM-dd`, `yyyy-MM` ou `yyyyMMdd`; nulo se não reconhecer."""
    s = c.cast("string")
    return (
        F.when(s.rlike(r"^\d{4}-\d{2}"), F.substring(s, 1, 7))
        .when(s.rlike(r"^\d{6}"), F.concat(F.substring(s, 1, 4), F.lit("-"), F.substring(s, 5, 2)))
    )


def _data_base_column(columns):
    # O DDR é recortado por mês nos checks (`data_base_month`); os demais por `dt_base`.
    for c in ("data_base_month", "dt_base"):
        if c in columns:
            return c
    return None


def _fingerprint(df, db_col):
    """{mês: (dt_base_max, row_count, content_hash)} do snapshot.

    `dt_base_max` é a data-base que o check avalia no mês — o maior `dt_base`.
    Vem do `dt_base` mesmo quando o recorte é por `data_base_month` (DDR), para
    sair o último DIA remetido, não o mês.
    """
    cols = sorted(c for c in df.columns if not c.startswith("_") and c not in _TECH_COLS)
    max_col = "dt_base" if "dt_base" in df.columns else db_col
    rows = (
        df.withColumn("_mes", _month(F.col(db_col)))
        .where(F.col("_mes").isNotNull())
        .groupBy("_mes")
        .agg(
            F.max(F.col(max_col).cast("string")).alias("dt_base_max"),
            F.count(F.lit(1)).alias("row_count"),
            # decimal: a soma de xxhash64 estoura BIGINT.
            F.sum(F.xxhash64(*cols).cast("decimal(38,0)")).cast("string").alias("content_hash"),
        )
        .collect()
    )
    return {r["_mes"]: (r["dt_base_max"], int(r["row_count"]), r["content_hash"]) for r in rows}


def _history(fqn):
    """[(versão, horário do commit)] das versões com dado, ou None se não houver histórico."""
    try:
        hist = spark.sql(f"DESCRIBE HISTORY {fqn}").select("version", "timestamp", "operation").collect()
    except Exception as exc:  # noqa: BLE001 — MV/streaming table do SDP
        print(f"  sem DESCRIBE HISTORY ({str(exc).splitlines()[0][:120]})")
        return None
    return sorted((int(h["version"]), h["timestamp"]) for h in hist if h["operation"] not in _SKIP_OPS)


def _apply(fqn, rows, fp, version, ts, now):
    """Aplica um snapshot ao histórico da tabela (SCD2 por mês). Devolve True se mudou."""
    changed = False
    open_by_month = {r["data_base_month"]: r for r in rows if r["valid_to"] is None}
    for month, (dt_max, n, h) in fp.items():
        cur = open_by_month.get(month)
        if cur is not None and cur["content_hash"] == h and cur["row_count"] == n:
            cur["last_seen_version"] = version
            # Mesmo conteúdo: só corrige o dt_base_max (linhas gravadas com o mês no DDR).
            changed = changed or cur["dt_base_max"] != dt_max
            cur["dt_base_max"] = dt_max
            continue
        if cur is not None:
            cur["valid_to"] = ts
            cur["last_seen_version"] = version
        rows.append({
            "table_fqn": fqn, "data_base_month": month, "dt_base_max": dt_max,
            "row_count": n, "content_hash": h, "delta_version": version,
            "last_seen_version": version, "valid_from": ts, "valid_to": None, "recorded_at": now,
        })
        changed = True
    # Mês que sumiu da tabela: fecha o intervalo.
    for month, cur in open_by_month.items():
        if month not in fp:
            cur["valid_to"] = ts
            cur["last_seen_version"] = version
            changed = True
    return changed

# COMMAND ----------

tabelas = [
    r["table_fqn"]
    for r in spark.sql(
        f"SELECT DISTINCT table_fqn FROM {CATALOG}.{GOV_SCHEMA}.cadoc_tabelas WHERE is_ativo"
    ).collect()
]
ledger_rows = [r.asDict() for r in spark.table(LEDGER).collect()]

for fqn in sorted(tabelas):
    print(f"• {fqn}")
    if not spark.catalog.tableExists(fqn):
        print("  [SKIP] tabela não existe — CADOC fora deste deployment.")
        continue
    db_col = _data_base_column(spark.table(fqn).columns)
    if db_col is None:
        print("  [SKIP] sem dt_base/data_base_month — data-base não se aplica.")
        continue

    rows = [dict(r) for r in ledger_rows if r["table_fqn"] == fqn]
    seen = max((r["last_seen_version"] for r in rows if r["last_seen_version"] is not None), default=-1)
    # Naive em UTC, como os horários que o Spark devolve (sessão em UTC).
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    hist = _history(fqn)
    if hist is None:
        snapshots = [(None, now)]
    else:
        snapshots = [(v, ts) for v, ts in hist if v > seen][-MAX_VERSIONS:]
        if not snapshots:
            print(f"  sem versão nova (última vista: {seen})")
            continue

    changed = False
    for version, ts in snapshots:
        try:
            df = spark.sql(f"SELECT * FROM {fqn} VERSION AS OF {version}") if version is not None else spark.table(fqn)
            fp = _fingerprint(df, db_col)
        except Exception as exc:  # noqa: BLE001 — arquivos já removidos pelo VACUUM
            print(f"  [SKIP] versão {version} ilegível ({str(exc).splitlines()[0][:120]})")
            continue
        changed = _apply(fqn, rows, fp, version, ts, now) or changed
        # A versão vista avança mesmo sem mudança de conteúdo.
        changed = changed or version is not None

    if not changed:
        print("  sem mudança")
        continue
    (
        spark.createDataFrame(rows, _SCHEMA)
        .write.mode("overwrite")
        .option("replaceWhere", f"table_fqn = '{fqn}'")
        .saveAsTable(LEDGER)
    )
    abertos = sorted(r["data_base_month"] for r in rows if r["valid_to"] is None)
    print(f"  {len(snapshots)} snapshot(s); meses vigentes: {', '.join(abertos) or '—'}")

print(f"OK — {LEDGER}")
