# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Setup e Plano de Contas COSIF (Documento 4010)
# MAGIC
# MAGIC Gerador sintético do **CADOC 4010 — Balancete Patrimonial Analítico (COSIF)**,
# MAGIC espelhando os geradores 3040/3050 do bundle demo. Este documento é a fonte
# MAGIC contábil do **batimento inter-CADOC** (SCR 3040 × COSIF 4010, crítica N01).
# MAGIC
# MAGIC ## Regra de Ouro
# MAGIC O 4010 **deriva** dos microdados do 3040 já gerados (`f_3040_*`): cada
# MAGIC rubrica COSIF recebe o somatório das operações 3040 que a ela mapeiam.
# MAGIC Assim o batimento **fecha por construção** — exceto pelas divergências que
# MAGIC injetamos de propósito (~5%), para o batimento ter o que detectar.
# MAGIC
# MAGIC ## ⚠️ Escopo / simulação
# MAGIC - O mapeamento rubrica-COSIF ↔ filtro do 3040 é **representativo e
# MAGIC   simplificado** (subconjunto de regras T/M), não a lógica COSIF completa
# MAGIC   do BACEN.
# MAGIC - **Não há binário validador oficial do 4010** no repo (só 3040/3050);
# MAGIC   portanto este gerador NÃO tem passo de validação BACEN.
# MAGIC
# MAGIC Este notebook define parâmetros + o plano de contas + o mapa conta→filtro.
# MAGIC É chamado via `%run` pelos notebooks seguintes.

# COMMAND ----------

dbutils.widgets.text("dt_base", "2026-03", "Data-base (YYYY-MM)")
dbutils.widgets.text("cnpj_if", "99999999", "CNPJ-base da IF (8 dígitos)")
dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Schema das tabelas staging/finais")
dbutils.widgets.text("src_prefix_3040", "rc18_catalog.reference.f_3040_",
                     "Prefixo das tabelas 3040 (clientes/operacoes/vencimentos)")
dbutils.widgets.text("pct_divergencia", "0.05", "Fração de rubricas com divergência injetada (~5%)")
dbutils.widgets.text("tolerancia_pct", "0.10", "Tolerância do batimento em % (default 0,10%)")
dbutils.widgets.text("seed", "42", "Semente para reprodutibilidade")

DT_BASE = dbutils.widgets.get("dt_base")
CNPJ_IF = dbutils.widgets.get("cnpj_if")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
SRC_PREFIX_3040 = dbutils.widgets.get("src_prefix_3040")
PCT_DIVERGENCIA = float(dbutils.widgets.get("pct_divergencia"))
TOLERANCIA_PCT = float(dbutils.widgets.get("tolerancia_pct"))
SEED = int(dbutils.widgets.get("seed"))

print(f"DtBase={DT_BASE} CNPJ={CNPJ_IF}")
print(f"Fonte 3040: {SRC_PREFIX_3040}* (operacoes/vencimentos)")
print(f"Divergência injetada: {PCT_DIVERGENCIA:.0%} | tolerância batimento: {TOLERANCIA_PCT}%")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Plano de contas COSIF + mapa conta → filtro 3040
# MAGIC
# MAGIC Cada rubrica define:
# MAGIC - `cosif_conta` / `cosif_descricao` — a conta contábil (rubrica do 4010).
# MAGIC - `tipo_regra` — 'T' (totais) ou 'M' (por modalidade), como na spec
# MAGIC   `docs/spec/03_data_model.md §4.3` (gold.reconciliacao_cosif).
# MAGIC - `codigo_regra` — código de batimento (T01, M02, ...).
# MAGIC - `filtro_3040` — expressão SQL sobre a operação 3040 que seleciona as
# MAGIC   operações somadas nesta rubrica (a "perna SCR" do batimento).
# MAGIC - `modalidade_3040` — só para tipo 'M'.
# MAGIC
# MAGIC As contas e os filtros abaixo são um SUBCONJUNTO REPRESENTATIVO — o
# MAGIC objetivo é demonstrar a dimensão Consistência ponta a ponta, não replicar
# MAGIC o batimento COSIF completo do BACEN.

# COMMAND ----------

# tipo_regra, codigo_regra, cosif_conta, descricao, modalidade_3040, filtro_3040
PLANO_CONTAS_COSIF = [
    # ── Totais (T) ────────────────────────────────────────────────────────────
    ("T", "T01", "3.1.0.00.00-0", "Total de créditos (carteira ativa)", None,
     "total_saldo > 0"),
    ("T", "T06", "3.0.9.80.00-4", "Créditos a liberar e limites", None,
     "total_limites > 0"),
    # ── Por modalidade (M) — uma rubrica por Mod do 3040 ───────────────────────
    ("M", "M01", "1.6.1.10.00-1", "Adiantamentos a depositantes", "0101",
     "mod = '0101'"),
    ("M", "M02", "1.6.1.20.00-8", "Empréstimos (capital de giro)", "0201",
     "mod IN ('0201','0202')"),
    ("M", "M03", "1.6.1.30.00-5", "Títulos descontados", "0301",
     "mod = '0301'"),
    ("M", "M04", "1.6.2.10.00-4", "Financiamentos", "0401",
     "mod IN ('0401','0402')"),
    ("M", "M13", "1.8.1.00.00-2", "Crédito pessoal / outros créditos", "0204",
     "mod = '0204'"),
]

# Coluna do 3040 que representa o SALDO a somar em cada rubrica.
# `total_saldo_venc` = soma dos buckets de vencimento (a fonte canônica de saldo).
COL_SALDO_3040 = "total_saldo_venc"

print(f"Plano de contas COSIF: {len(PLANO_CONTAS_COSIF)} rubricas "
      f"({sum(1 for r in PLANO_CONTAS_COSIF if r[0]=='T')} T, "
      f"{sum(1 for r in PLANO_CONTAS_COSIF if r[0]=='M')} M).")
