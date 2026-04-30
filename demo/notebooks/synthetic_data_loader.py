# Databricks notebook source
# MAGIC %md
# MAGIC # Synthetic Data Loader
# MAGIC Generates synthetic SCR 3040 and 3050 data and loads it into bronze tables
# MAGIC for development and demo purposes. Uses Faker for realistic Brazilian data.

# COMMAND ----------

# MAGIC %pip install faker

# COMMAND ----------

dbutils.widgets.text("n_operacoes", "50000", "Number of operations per month")
dbutils.widgets.text("n_meses", "6", "Number of months to generate")
dbutils.widgets.text("dt_base_inicio", "2025-09-01", "Start date (YYYY-MM-DD)")
dbutils.widgets.text("catalog", "rc18_demo_catalog", "Unity Catalog")
dbutils.widgets.text("schema_bronze", "bronze", "Bronze schema name")

N_OPERACOES = int(dbutils.widgets.get("n_operacoes"))
N_MESES = int(dbutils.widgets.get("n_meses"))
DT_BASE_INICIO = dbutils.widgets.get("dt_base_inicio")

CATALOG = dbutils.widgets.get("catalog")
BRONZE = dbutils.widgets.get("schema_bronze")
CNPJ_IF = "99999999"  # Synthetic CNPJ-base for demo

# Schema is declared by the bundle (demo/resources/uc_assets.yml) but we ensure
# it exists here so the notebook is also runnable standalone (e.g. attached to
# a cluster outside the bundle).
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{BRONZE}")

print(f"Generating {N_OPERACOES} operations/month × {N_MESES} months starting from {DT_BASE_INICIO}")
print(f"Target: {CATALOG}.{BRONZE}")

# COMMAND ----------

import random
import hashlib
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from faker import Faker
from pyspark.sql import Row
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DecimalType, DateType, BooleanType, TimestampType
)

fake = Faker("pt_BR")
Faker.seed(42)
random.seed(42)

MODALIDADES = ["0201", "0202", "0204", "0301", "0401", "0402", "0501", "0701"]
NATUREZAS = ["01", "01", "01", "01", "04", "11"]  # Weighted towards normal
CLASSIFICACOES = ["AA", "A", "A", "B", "B", "C", "D", "E", "F", "G", "H"]
INDEXADORES = ["11", "12", "13", "14", "15", "21", "31"]
TIPOS_CLIENTE = ["1", "1", "1", "2", "5"]  # Weighted towards PF
PORTES = ["1", "2", "3", "4", "5", "6"]
ENCARGOS_3050 = ["pre", "flu", "vc", "ipca", "igpm"]
SEGMENTOS_3050 = ["pesJuridica", "pesFisica"]
MODALIDADES_3050 = ["capitalDeGiro", "crdPessoal", "descDuplicatas", "aquisicaoImovel", "cartaoCredito", "chqEspecial"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate SCR 3040 Operations

# COMMAND ----------

def generate_operations(dt_base_str: str, n: int) -> list[dict]:
    """Generate n synthetic credit operations for a given dt_base."""
    rows = []
    dt_base_date = date.fromisoformat(dt_base_str + "-01") if len(dt_base_str) == 7 else date.fromisoformat(dt_base_str)

    for i in range(n):
        cli_tp = random.choice(TIPOS_CLIENTE)
        if cli_tp == "1":
            cli_cd = fake.cpf().replace(".", "").replace("-", "")
        else:
            cli_cd = fake.cnpj().replace(".", "").replace("/", "").replace("-", "")[:8]

        mod = random.choice(MODALIDADES)
        natu_op = random.choice(NATUREZAS)
        contrt = f"CONTR{i:010d}"
        ipoc = f"{CNPJ_IF}{mod}{cli_tp}{cli_cd[:14].ljust(14,'0')}{contrt}"[:70]

        dt_contr = dt_base_date - timedelta(days=random.randint(30, 1800))
        dt_venc = dt_contr + timedelta(days=random.randint(180, 3600))
        vlr_contr = round(random.uniform(500, 5000000), 2)

        pk_data = f"{CNPJ_IF}|{contrt}|{dt_base_str}"
        pk_hash = hashlib.sha256(pk_data.encode()).hexdigest()

        rows.append({
            "_pk_hash": pk_hash,
            "cnpj_if": CNPJ_IF,
            "dt_base": dt_base_str[:7],
            "remessa": 1,
            "tipo_arquivo": "F",
            "cli_tp": cli_tp,
            "cli_cd": cli_cd,
            "contrt": contrt,
            "natu_op": natu_op,
            "mod": mod,
            "ipoc": ipoc,
            "origem_rec": "0001",
            "indx": random.choice(INDEXADORES),
            "dt_venc_op": dt_venc.isoformat(),
            "class_op": random.choice(CLASSIFICACOES),
            "tax_eft": round(random.uniform(0.5, 35.0), 4),
            "dt_contr": dt_contr.isoformat(),
            "vlr_contr": vlr_contr,
            "dia_atraso": max(0, random.randint(-30, 180)),
            "prov_consttd": round(vlr_contr * random.uniform(0, 0.15), 2),
        })
    return rows


# Generate operations for all months
all_ops = []
start_date = date.fromisoformat(DT_BASE_INICIO)
for m in range(N_MESES):
    dt = start_date + relativedelta(months=m)
    dt_base_str = dt.strftime("%Y-%m")
    print(f"Generating {N_OPERACOES} operations for {dt_base_str}...")
    all_ops.extend(generate_operations(dt_base_str, N_OPERACOES))

ops_df = spark.createDataFrame(all_ops)
ops_df = (
    ops_df
    .withColumn("_source_system", F.lit("synthetic_generator"))
    .withColumn("_source_table", F.lit("synthetic_3040"))
    .withColumn("_ingestion_timestamp", F.current_timestamp())
    .withColumn("_change_type", F.lit("FULL_LOAD"))
    .withColumn("_ingestion_date", F.current_date())
    .withColumn("_source_column_map", F.lit(None).cast("string"))
)

ops_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{BRONZE}.operacoes_raw")
print(f"Written {ops_df.count()} rows to {CATALOG}.{BRONZE}.operacoes_raw")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate SCR 3040 Clients (deduplicated from operations)

# COMMAND ----------

clients_df = (
    ops_df
    .select("cnpj_if", "dt_base", "cli_tp", "cli_cd")
    .distinct()
    .withColumn("cli_porte", F.lit(random.choice(PORTES)))
    .withColumn("cli_class", F.lit(random.choice(CLASSIFICACOES)))
    .withColumn("_pk_hash", F.sha2(F.concat_ws("|", "cli_cd", "cli_tp", "dt_base"), 256))
    .withColumn("_source_system", F.lit("synthetic_generator"))
    .withColumn("_source_table", F.lit("synthetic_clientes"))
    .withColumn("_ingestion_timestamp", F.current_timestamp())
    .withColumn("_change_type", F.lit("FULL_LOAD"))
    .withColumn("_ingestion_date", F.current_date())
    .withColumn("_source_column_map", F.lit(None).cast("string"))
)

clients_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{BRONZE}.clientes_raw")
print(f"Written {clients_df.count()} rows to {CATALOG}.{BRONZE}.clientes_raw")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate SCR 3050 Data (Daily + Monthly)

# COMMAND ----------

def generate_3050_diario(dt_base_str: str) -> list[dict]:
    """Generate daily 3050 data for a week."""
    rows = []
    dt = date.fromisoformat(dt_base_str)
    for mod in MODALIDADES_3050:
        for enc in ENCARGOS_3050:
            for seg in SEGMENTOS_3050:
                rows.append({
                    "cnpj_if": CNPJ_IF,
                    "dt_base_semanal": dt_base_str,
                    "ind_remessa": 1,
                    "dt_referencia": dt_base_str,
                    "tipo_periodo": "diario",
                    "modalidade": f"{mod}.{seg}.{enc}",
                    "encargo": enc,
                    "segmento": seg,
                    "vlr_concessoes": round(random.uniform(100, 500000), 3),
                    "tx_med_juros": round(random.uniform(1.0, 45.0), 4),
                    "sld_car_ativa": round(random.uniform(1000, 10000000), 3),
                    "sld_cedido": round(random.uniform(0, 500000), 3),
                    "sld_adquirido": round(random.uniform(0, 200000), 3),
                    "leiaute_versao": "V11",
                })
    return rows


all_3050 = []
for m in range(N_MESES):
    dt = start_date + relativedelta(months=m)
    # Generate a few weeks per month
    for w in range(4):
        week_dt = dt + timedelta(days=w * 7)
        if week_dt.weekday() >= 5:
            week_dt += timedelta(days=(7 - week_dt.weekday()))
        all_3050.extend(generate_3050_diario(week_dt.isoformat()))

df_3050 = spark.createDataFrame(all_3050)
df_3050 = (
    df_3050
    .withColumn("_pk_hash", F.sha2(F.concat_ws("|", "cnpj_if", "dt_base_semanal", "dt_referencia", "modalidade", "encargo", "segmento"), 256))
    .withColumn("_source_system", F.lit("synthetic_generator"))
    .withColumn("_source_table", F.lit("synthetic_3050"))
    .withColumn("_ingestion_timestamp", F.current_timestamp())
    .withColumn("_change_type", F.lit("FULL_LOAD"))
    .withColumn("_ingestion_date", F.current_date())
    .withColumn("_source_column_map", F.lit(None).cast("string"))
)

df_3050.write.mode("overwrite").saveAsTable(f"{CATALOG}.{BRONZE}.raw_3050_diario")
print(f"Written {df_3050.count()} rows to {CATALOG}.{BRONZE}.raw_3050_diario")

# COMMAND ----------

print(f"""
Synthetic data generation complete:
  - {CATALOG}.{BRONZE}.operacoes_raw: {N_OPERACOES * N_MESES} operations
  - {CATALOG}.{BRONZE}.clientes_raw: deduplicated clients
  - {CATALOG}.{BRONZE}.raw_3050_diario: daily 3050 records

Next steps:
  1. Run the bronze pipeline to validate data is readable
  2. Run the silver pipeline to apply DLT expectations
  3. Run the gold pipeline for the curated position tables
""")
