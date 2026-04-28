# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Geração de Dados Sintéticos (Clientes, Operações, Vencimentos, Garantias)
# MAGIC
# MAGIC Produz quatro DataFrames staging:
# MAGIC
# MAGIC | DataFrame         | Tag XML | Conteúdo                                                |
# MAGIC |-------------------|---------|---------------------------------------------------------|
# MAGIC | `df_clientes`     | `<Cli>` | 1 linha por cliente, com `Cd` = 8 dígitos únicos        |
# MAGIC | `df_operacoes`    | `<Op>`  | N operações por cliente, com `Contrt` único             |
# MAGIC | `df_vencimentos`  | `<Venc>`| Buckets v110..v999 por operação (1:1 com `df_operacoes`)|
# MAGIC | `df_garantias`    | `<Gar>` | 0..k garantias por operação (reais ou fidejussórias)    |
# MAGIC
# MAGIC As chaves amarradas (`cli_cd`, `op_id`) garantem integridade relacional na
# MAGIC construção hierárquica do XML no notebook 03.
# MAGIC
# MAGIC **Importante:** CPFs/CNPJs são matematicamente válidos (módulo 11). Datas,
# MAGIC valores e relacionamentos são coerentes internamente; regras de
# MAGIC interdependência (IPOC, CaracEspecial, ClassCli≥ClassOp) são aplicadas no
# MAGIC notebook 02.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Dominios

# COMMAND ----------

import random
from datetime import date
from faker import Faker
from pyspark.sql import Row
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, DateType, DoubleType,
)

fake = Faker("pt_BR")
Faker.seed(42)
rng = random.Random(42)

# DT_BASE chega de 00 como "YYYY-MM"
DT_BASE_DATE = date(int(DT_BASE[:4]), int(DT_BASE[5:7]), 1)

print(f"Semente fixa (42). Gerando {N_CLIENTES} clientes com média {N_OPS_POR_CLI} ops.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clientes (`<Cli>`)
# MAGIC Cada cliente recebe um código interno de 8 dígitos (`Cd`) único — esse código
# MAGIC é o identificador sem os 6 dígitos finais do CNPJ (para PJ) ou um alias
# MAGIC numérico (para PF, onde o CPF completo é guardado em `ident_fiscal`).

# COMMAND ----------

def _gerar_cli(i: int) -> Row:
    """Gera um registro de cliente PJ conforme XSD 202601 (@DetCli=tipoCNPJ14)."""
    cd = f"{i:08d}"                                       # 8 dígitos — Cli/@Cd (base do CNPJ)
    ident = gerar_cnpj(rng, base8=cd, filial="0001")     # matriz
    return Row(
        cli_cd=cd,
        ident_fiscal=ident,
        tp="2",                                           # PJ (apenas PJ neste MVP)
        autorzc="S",                                      # S = autorização p/ SCR
        porte_cli=rng.choice(PORTES_PJ),
        tp_ctrl=rng.choice(TP_CTRL),
        ini_relact_cli=fake.date_between(start_date="-10y", end_date="-1y"),
        cong_econ="000000",
        # C31: FatAnual obrigatório para Tp=2,4,6 desde 2011-07 (valores em milhões)
        fat_anual=round(rng.uniform(500_000.0, 50_000_000.0), 2),
    )


rows_cli = [_gerar_cli(i + 1) for i in range(N_CLIENTES)]
schema_cli = StructType([
    StructField("cli_cd", StringType(), False),
    StructField("ident_fiscal", StringType(), False),
    StructField("tp", StringType(), False),
    StructField("autorzc", StringType(), False),
    StructField("porte_cli", StringType(), False),
    StructField("tp_ctrl", StringType(), False),
    StructField("ini_relact_cli", DateType(), False),
    StructField("cong_econ", StringType(), False),
    StructField("fat_anual", DoubleType(), False),
])
df_clientes = spark.createDataFrame(rows_cli, schema_cli)
print(f"df_clientes: {df_clientes.count()} registros")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Operações (`<Op>`)
# MAGIC Volume por cliente ~ Poisson(N_OPS_POR_CLI) truncado em [1, 10].
# MAGIC Contratos (`Contrt`) são strings alfanuméricas únicas (sufixo sequencial garante unicidade).

# COMMAND ----------

def _gerar_ops_para_cliente(cli: Row) -> list[Row]:
    n = max(1, min(10, int(rng.gauss(N_OPS_POR_CLI, 1.2))))
    ops = []
    for k in range(n):
        mod = rng.choice(MOD_OP)
        natu = rng.choice(NATU_OP)
        dt_contr = fake.date_between(start_date="-5y", end_date="-1m")
        # Prazo 6–60 meses; DtVencOp > DtBase p/ operações vivas
        prazo_meses = rng.randint(6, 60)
        dt_venc = add_dias(dt_contr, prazo_meses * 30)
        if dt_venc <= DT_BASE_DATE:
            dt_venc = add_dias(DT_BASE_DATE, rng.randint(30, 720))
        vlr_op = round(rng.uniform(1000, 500000), 2)       # saldo devedor
        prov = round(vlr_op * rng.uniform(0.001, 0.15), 2) # provisão 0.1%..15%
        # Contrato único por cliente (cli_cd + sequência)
        contrt = f"{cli.cli_cd[-4:]}{k:03d}{rng.randint(10, 99)}"
        # Origem/indexador/câmbio (Anexos 4/5) — correlacionados
        indx = rng.choice(INDX)
        var_camb = rng.choice(VAR_CAMB)
        # C32: PercIndx obrigatório desde 2011-09 (percentual do indexador)
        perc_indx = round(rng.uniform(80.0, 150.0), 2)
        # CaracEspecial: nulo em ~85% dos casos; nos demais, 1–2 valores concatenados
        if rng.random() < 0.15:
            k_sel = rng.choice([1, 1, 2])
            carac = ";".join(sorted(rng.sample(CARAC_ESPECIAL, k_sel)))
        else:
            carac = None
        ops.append(Row(
            cli_cd=cli.cli_cd,
            tp_cli=cli.tp,
            op_id=f"{cli.cli_cd}-{k:02d}",                 # chave interna p/ joins
            contrt=contrt,
            natu_op=natu,
            mod=mod,
            origem_rec=rng.choice(ORIGEM_REC),
            indx=indx,
            perc_indx=perc_indx,
            var_camb=var_camb,
            dt_venc_op=dt_venc,
            cep=f"{rng.randint(1000000, 99999999):08d}",
            tax_eft=round(rng.uniform(1.5, 65.0), 2),
            dt_contr=dt_contr,
            prov_consttd=prov,
            carac_especial=carac,
            vlr_op=vlr_op,
        ))
    return ops


rows_op = [r for cli in rows_cli for r in _gerar_ops_para_cliente(cli)]
schema_op = StructType([
    StructField("cli_cd", StringType(), False),
    StructField("tp_cli", StringType(), False),
    StructField("op_id", StringType(), False),
    StructField("contrt", StringType(), False),
    StructField("natu_op", StringType(), False),
    StructField("mod", StringType(), False),
    StructField("origem_rec", StringType(), False),
    StructField("indx", StringType(), False),
    StructField("perc_indx", DoubleType(), False),
    StructField("var_camb", StringType(), False),
    StructField("dt_venc_op", DateType(), False),
    StructField("cep", StringType(), False),
    StructField("tax_eft", DoubleType(), False),
    StructField("dt_contr", DateType(), False),
    StructField("prov_consttd", DoubleType(), False),
    StructField("carac_especial", StringType(), True),
    StructField("vlr_op", DoubleType(), False),
])
df_operacoes = spark.createDataFrame(rows_op, schema_op)
print(f"df_operacoes: {df_operacoes.count()} registros")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Vencimentos (`<Venc>`) — buckets v110..v999
# MAGIC Distribui `vlr_op` por prazo da operação, simulando PRICE/SAC: maior peso nos
# MAGIC primeiros buckets para operações curtas, peso em v999 (longo prazo) p/ as longas.

# COMMAND ----------

def _gerar_venc(op: Row) -> Row:
    """Concentra o saldo no bucket A VENCER coerente com o prazo restante.
    Faixas conforme Instruções de Preenchimento do Doc 3040:
      v110=0-30d, v120=31-60d, v130=61-90d, v140=91-180d, v150=181-360d,
      v160=361-720d, v165=721-1080d, v170=1081-1440d, v175=1441-1800d,
      v180=1801-5400d.
    Evita v2xx (vencidos) e v3xx (prejuízo) — exigem DiaAtraso > 0 (S28)."""
    dias = (op.dt_venc_op - DT_BASE_DATE).days
    if dias <= 30:         bucket = "v110"
    elif dias <= 60:       bucket = "v120"
    elif dias <= 90:       bucket = "v130"
    elif dias <= 180:      bucket = "v140"
    elif dias <= 360:      bucket = "v150"
    elif dias <= 720:      bucket = "v160"
    elif dias <= 1080:     bucket = "v165"
    elif dias <= 1440:     bucket = "v170"
    elif dias <= 1800:     bucket = "v175"
    else:                  bucket = "v180"
    out = {"op_id": op.op_id}
    for b in VENC_BUCKETS:
        out[b] = op.vlr_op if b == bucket else 0.0
    return Row(**out)


rows_venc = [_gerar_venc(op) for op in rows_op]
schema_venc = StructType(
    [StructField("op_id", StringType(), False)]
    + [StructField(b, DoubleType(), False) for b in VENC_BUCKETS]
)
df_vencimentos = spark.createDataFrame(rows_venc, schema_venc)
print(f"df_vencimentos: {df_vencimentos.count()} registros")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Garantias (`<Gar>`)
# MAGIC ~60% das operações possuem pelo menos 1 garantia; 20% têm 2 garantias.
# MAGIC Tipo fidejussório (09xx) implica `Ident`+`PercGar`; demais (real) implicam
# MAGIC `VlrOrig`/`VlrData`/`DtReav`.

# COMMAND ----------

def _gerar_gars(op: Row) -> list[Row]:
    n = rng.choices([0, 1, 2], weights=[0.4, 0.4, 0.2])[0]
    gars = []
    for _ in range(n):
        if rng.random() < 0.3:
            # Fidejussória — regra I08: 0901 (PF) → CPF11; 0902 (PJ) → CNPJ14.
            tp = rng.choice(GAR_TIPOS_FIDEJ)
            ident = gerar_cpf(rng) if tp == "0901" else gerar_cnpj(rng)
            gars.append(Row(
                op_id=op.op_id, tp=tp, ident=ident,
                perc_gar=round(rng.uniform(20.0, 100.0), 2),
                vlr_orig=None, vlr_data=None, dt_reav=None,
            ))
        else:
            # Real
            tp = rng.choice(GAR_TIPOS_REAIS)
            vorig = round(op.vlr_op * rng.uniform(0.5, 2.0), 2)
            vdata = round(vorig * rng.uniform(0.8, 1.1), 2)
            dt_reav = fake.date_between(start_date="-1y", end_date="today")
            gars.append(Row(
                op_id=op.op_id, tp=tp, ident=None, perc_gar=None,
                vlr_orig=vorig, vlr_data=vdata, dt_reav=dt_reav,
            ))
    return gars


rows_gar = [g for op in rows_op for g in _gerar_gars(op)]
schema_gar = StructType([
    StructField("op_id", StringType(), False),
    StructField("tp", StringType(), False),
    StructField("ident", StringType(), True),
    StructField("perc_gar", DoubleType(), True),
    StructField("vlr_orig", DoubleType(), True),
    StructField("vlr_data", DoubleType(), True),
    StructField("dt_reav", DateType(), True),
])
df_garantias = spark.createDataFrame(rows_gar, schema_gar) if rows_gar else spark.createDataFrame([], schema_gar)
print(f"df_garantias: {df_garantias.count()} registros")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persistência staging (Delta) para o notebook 02

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

staging_prefix = f"{CATALOG}.{SCHEMA}.stg_3040_"
df_clientes.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(staging_prefix + "clientes")
df_operacoes.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(staging_prefix + "operacoes")
df_vencimentos.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(staging_prefix + "vencimentos")
df_garantias.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(staging_prefix + "garantias")

print(f"Tabelas staging gravadas em {staging_prefix}*")
