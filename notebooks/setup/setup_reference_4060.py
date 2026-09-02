# Databricks notebook source
# MAGIC %md
# MAGIC # Setup Reference — Críticas do CADOC 4060
# MAGIC
# MAGIC Semeia `reference.criticas_cosif` (**2 críticas de exemplo**),
# MAGIC `reference.cosif_anexo_i_res352` (vazia — ponto de extensão do fator de perda
# MAGIC esperada da Res. BCB 352) e as views de crítica consumidas pelos checks DQX.
# MAGIC
# MAGIC As críticas são DADOS: `gold.criticas_cosif_4060` é um avaliador genérico da
# MAGIC tabela, então carregar o catálogo da instituição é `INSERT`, não código novo.
# MAGIC
# MAGIC Cada regra é um `operador` + contas de cada lado com peso + `comparador` +
# MAGIC tolerância. Os cinco operadores levam o nome da crítica arquetípica do BCB
# MAGIC (Tabela de Críticas COSIF); as 2 de exemplo exercitam dois deles.
# MAGIC
# MAGIC `tipo_critica` guarda o `E`/`I` do BCB; `criticality` (o que o DQX consome) é
# MAGIC derivada dele. `is_ativo = false` exige `motivo_inativo`.
# MAGIC
# MAGIC ⚠️ As 2 citam contas COSIF reais, ausentes do sample sintético — no sample
# MAGIC dão `INDETERMINADO` (conta citada que não veio ⇒ nunca zero). O `OK` do
# MAGIC primeiro deploy vem da crítica estrutural `SOMA_PRUDENCIAL`.

# COMMAND ----------

from pyspark.sql import functions as F, types as T

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("reference_schema", "reference")
dbutils.widgets.text("gold_schema", "gold")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("reference_schema")

DOCUMENTO = "4060"
LEIAUTE_VERSAO = "4060v2022-11"

print(f"alvo: {CATALOG}.{SCHEMA}")

# COMMAND ----------
# As 2 de exemplo. Acrescente as suas aqui ou por INSERT na tabela.
CRITICAS = [
    # Lado ÚNICO: `contas_direita` vazia ⇒ a soma da esquerda tem de fechar em zero.
    {
        'critica_id': 'COS00584', 'critica_seq': 19025, 'documento': '4060', 'origem': 'indicio_bcb',
        'tipo_critica': 'I', 'criticality': 'warn',
        'descricao': (
            'As contas de relações interdependências ativas [1500000004] ou passivas [4500000001] não podem r'
            'egistrar saldos nos balancetes e balanços das entidades. São de uso exclusivo nos balancetes e b'
            'alanços de agências/dependências no País.'),
        'dimensao_r18': '8', 'revisar_dimensao': False, 'operador': 'TOTAL_DIFERE_DAS_PARCELAS',
        'comparador': None, 'comparador_direita': None,
        'contas_esquerda': [
            {'conta': '1500000004', 'peso': 1, 'variacao_mensal': False, 'fator_anexo_i': None},
            {'conta': '4500000001', 'peso': 1, 'variacao_mensal': False, 'fator_anexo_i': None},
        ],
        'contas_direita': [],
        'tolerancia': 0.0, 'tolerancia_pct': None, 'modulo_esquerda': False, 'modulo_direita': False,
        'simetrico': False, 'ignora_quando_tudo_zero': False, 'is_ativo': True, 'motivo_inativo': None,
        'avisos': [],
    },
    # Lado DUPLO: compara os dois lados. Peso -1 = convenção de sinal do COSIF.
    {
        'critica_id': 'COS00802', 'critica_seq': 19015, 'documento': '4060', 'origem': 'indicio_bcb',
        'tipo_critica': 'I', 'criticality': 'warn',
        'descricao': (
            'O saldo de Créditos a Liberar ([3341020007] + [3342020006]) não pode ser inferior às provisões p'
            'ara perdas esperadas como tais créditos ([4812000005]).'),
        'dimensao_r18': '8', 'revisar_dimensao': False, 'operador': 'SALDO_INFERIOR_AO_ESPERADO',
        'comparador': '<', 'comparador_direita': None,
        'contas_esquerda': [
            {'conta': '3341020007', 'peso': -1, 'variacao_mensal': False, 'fator_anexo_i': None},
            {'conta': '3342020006', 'peso': -1, 'variacao_mensal': False, 'fator_anexo_i': None},
        ],
        'contas_direita': [
            {'conta': '4812000005', 'peso': 1, 'variacao_mensal': False, 'fator_anexo_i': None},
        ],
        'tolerancia': 0.0, 'tolerancia_pct': None, 'modulo_esquerda': False, 'modulo_direita': False,
        'simetrico': False, 'ignora_quando_tudo_zero': False, 'is_ativo': True, 'motivo_inativo': None,
        'avisos': [],
    },
]

# Anexo I da Res. BCB 352: `(referencia, fator, amostras, concordancia_pct, origem)`.
# `referencia` casa com o `fator_anexo_i` da conta na crítica.
ANEXO_I = []

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Spec das críticas (embutida)

# COMMAND ----------

print(f"críticas na spec: {len(CRITICAS)}")

_CONTA = T.StructType([
    T.StructField("conta", T.StringType()),
    T.StructField("peso", T.IntegerType()),
    T.StructField("variacao_mensal", T.BooleanType()),
    T.StructField("fator_anexo_i", T.StringType()),
])

_SCHEMA_CRITICAS = T.StructType([
    T.StructField("critica_id", T.StringType(), False),
    T.StructField("critica_seq", T.IntegerType(), False),
    T.StructField("documento", T.StringType(), False),
    T.StructField("origem", T.StringType()),
    # Nomenclatura do BCB: E = Erro (reprova o documento), I = Indício (CRD).
    T.StructField("tipo_critica", T.StringType()),
    # O que o DQX consome, DERIVADO do tipo: E -> error, I -> warn.
    T.StructField("criticality", T.StringType()),
    T.StructField("descricao", T.StringType()),
    T.StructField("dimensao_r18", T.StringType()),
    T.StructField("revisar_dimensao", T.BooleanType()),
    T.StructField("operador", T.StringType()),
    T.StructField("comparador", T.StringType()),
    T.StructField("comparador_direita", T.StringType()),
    T.StructField("contas_esquerda", T.ArrayType(_CONTA)),
    T.StructField("contas_direita", T.ArrayType(_CONTA)),
    T.StructField("tolerancia", T.DoubleType()),
    T.StructField("tolerancia_pct", T.DoubleType()),
    T.StructField("modulo_esquerda", T.BooleanType()),
    T.StructField("modulo_direita", T.BooleanType()),
    T.StructField("simetrico", T.BooleanType()),
    T.StructField("ignora_quando_tudo_zero", T.BooleanType()),
    T.StructField("is_ativo", T.BooleanType(), False),
    T.StructField("motivo_inativo", T.StringType()),
    T.StructField("avisos", T.ArrayType(T.StringType())),
])

fqn = f"{CATALOG}.{SCHEMA}.criticas_cosif"

criticas_df = (
    spark.createDataFrame(CRITICAS, schema=_SCHEMA_CRITICAS)
    .withColumn("leiaute_versao", F.lit(LEIAUTE_VERSAO))
    .withColumn("updated_at", F.current_timestamp())
)

# `replaceWhere` faz overwrite SELETIVO (só as linhas deste documento, para vários
# CADOCs coexistirem) e por isso EXIGE que o schema da tabela seja igual ao do
# DataFrame — não combina com `overwriteSchema`. Juntar os dois devolve
# DELTA_METADATA_MISMATCH, que é o que acontece quando o formato das regras muda.
# Então: se o schema divergir, recria a tabela; se casar, usa o overwrite seletivo.
_esperado = criticas_df.columns
_recriar = False
if spark.catalog.tableExists(fqn):
    _atual = spark.table(fqn).columns
    if _atual != _esperado:
        print(f"schema de {fqn} mudou — recriando a tabela.")
        print(f"  saíram : {[c for c in _atual if c not in _esperado]}")
        print(f"  entraram: {[c for c in _esperado if c not in _atual]}")
        spark.sql(f"DROP TABLE {fqn}")
        _recriar = True

_writer = criticas_df.write.format("delta").mode("overwrite")
if not _recriar and spark.catalog.tableExists(fqn):
    _writer = _writer.option("replaceWhere", f"documento = '{DOCUMENTO}'")
else:
    _writer = _writer.option("overwriteSchema", "true")
_writer.saveAsTable(fqn)

spark.sql(
    f"COMMENT ON TABLE {fqn} IS "
    "'Criticas dos documentos COSIF como DADOS DE DOMINIO: operador + contas de "
    "cada lado (com peso) + comparador + tolerancia. Nenhuma expressao SQL "
    "embutida. Avaliada por gold.criticas_cosif_<doc>.'"
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")

display(
    spark.table(fqn)
    .groupBy("documento", "origem", "is_ativo")
    .agg(F.count("*").alias("criticas"))
    .orderBy("documento", "origem")
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Anexo I da Res. BCB 352 — percentuais de perda esperada
# MAGIC Usado pela crítica das perdas incorridas (COS00745/COS00745b), que aplica
# MAGIC o percentual da faixa a cada detalhamento das contas de provisão.
# MAGIC
# MAGIC ⚠️ Fatores recuperados por extração — confira contra a Res. BCB 352 antes de
# MAGIC usar em produção (a coluna `origem` registra a procedência).

# COMMAND ----------

_SCHEMA_ANEXO = T.StructType([
    T.StructField("referencia", T.StringType(), False),
    T.StructField("fator", T.DoubleType(), False),
    T.StructField("amostras", T.IntegerType()),
    T.StructField("concordancia_pct", T.DoubleType()),
    T.StructField("origem", T.StringType()),
])

fqn_anexo = f"{CATALOG}.{SCHEMA}.cosif_anexo_i_res352"
(
    spark.createDataFrame(ANEXO_I, schema=_SCHEMA_ANEXO)
    .withColumn("updated_at", F.current_timestamp())
    .write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(fqn_anexo)
)
spark.sql(
    f"COMMENT ON TABLE {fqn_anexo} IS "
    "'Percentuais do Anexo I da Res. BCB 352 usados na critica das perdas "
    "incorridas do CADOC 4060.'"
)
print(f"OK — {fqn_anexo}: {spark.table(fqn_anexo).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Views consumidas pelos checks DQX
# MAGIC O DQX corrompe aspas no round-trip de `parse_json`, então as `expression`
# MAGIC não podem ter literal string — os domínios vêm daqui.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_crit_4060_status_bloqueante AS
SELECT * FROM (VALUES ('BLOQUEADO'), ('INDETERMINADO')) AS t(valor_codigo)
""")

# Alvo dos checks DQX: resolve a data-base corrente e expõe `is_bloqueante`, o que
# deixa `filter` e `expression` de cada check mínimos (teto de 10.000 caracteres de
# job parameters no dry run da Studio).
#
# No modo CLÁSSICO quem cria esta view é `gold/criticas_cosif_4060.py`, no fim da
# execução — o lugar natural, porque ela depende daquela tabela. Aqui a criação é
# um fallback para o modo SDP, onde o notebook do gold termina num `@dlt.table` e
# não há ponto pós-escrita. Consequência: no SDP a view só existe a partir da
# SEGUNDA execução do setup, quando o gold já materializou.
_gold_4060 = f"{CATALOG}.{dbutils.widgets.get('gold_schema')}.criticas_cosif_{DOCUMENTO}"
if spark.catalog.tableExists(_gold_4060):
    spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_crit_{DOCUMENTO}_corrente AS
    SELECT c.*,
           c.status IN (
               SELECT valor_codigo
               FROM {CATALOG}.{SCHEMA}.v_crit_{DOCUMENTO}_status_bloqueante
           ) AS is_bloqueante
    FROM   {_gold_4060} c
    WHERE  c.dt_base = (SELECT max(dt_base) FROM {_gold_4060})
    """)
    print(f"OK — view {CATALOG}.{SCHEMA}.v_crit_{DOCUMENTO}_corrente")
else:
    print(f"{_gold_4060} ainda não existe — a view do DQX será criada pelo gold "
          f"(clássico) ou na próxima execução deste setup (SDP).")

spark.sql(f"""
CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_crit_4060_ativas AS
SELECT critica_id, critica_seq, tipo_critica, criticality, operador,
       dimensao_r18, descricao
FROM {CATALOG}.{SCHEMA}.criticas_cosif
WHERE documento = '{DOCUMENTO}' AND is_ativo
""")

print("views criadas")
