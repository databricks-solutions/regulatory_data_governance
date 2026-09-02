# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — Críticas do CADOC 4060 → `gold.criticas_cosif_4060`
# MAGIC
# MAGIC As regras ficam em `reference.criticas_cosif`: um operador, as contas de cada
# MAGIC lado com seus pesos, o comparador e a tolerância. Este notebook soma os dois
# MAGIC lados e aplica o operador. Regra nova = linha nova na tabela.
# MAGIC
# MAGIC | Operador | Violado quando |
# MAGIC |---|---|
# MAGIC | `TOTAL_DIFERE_DAS_PARCELAS` | `abs(esq − dir) > tolerancia` |
# MAGIC | `CONTRAPARTIDA_AUSENTE` | há saldo num lado e o outro não registra |
# MAGIC | `SALDO_INFERIOR_AO_ESPERADO` | `esq <comparador> dir` |
# MAGIC | `SALDO_INDEVIDO` | `esq <comparador> 0` |
# MAGIC | `DIVERGENCIA_ACIMA_DA_TOLERANCIA` | `esq <comparador> pct × dir` |
# MAGIC
# MAGIC Os nomes vêm da Tabela de Críticas COSIF (`TOTAL_DIFERE_DAS_PARCELAS` é a
# MAGIC crítica E3, por exemplo). O agrupamento em famílias é nosso — o BCB numera
# MAGIC críticas individuais, não famílias.
# MAGIC
# MAGIC **`coluna_logica`** é o eixo de avaliação: uma por entidade (blocos 4/6/7) e
# MAGIC três por bloco consolidado (`#AGLUTINADO`, `#ELIMINACOES`, `#CONSOLIDADO`).
# MAGIC
# MAGIC **Conta citada que não veio no documento ⇒ `INDETERMINADO`**, não zero.
# MAGIC
# MAGIC Gêmeo DLT: `pipelines/gold/transformations/criticas_cosif_4060.py`.

# COMMAND ----------
# MAGIC %md
# MAGIC %md
# MAGIC ## Como conferir uma regra
# MAGIC
# MAGIC ```sql
# MAGIC SELECT operador, comparador, comparador_direita, contas_esquerda, contas_direita
# MAGIC FROM   reference.criticas_cosif WHERE critica_id = 'COS00802';
# MAGIC
# MAGIC SELECT coluna_logica, soma_esquerda, soma_direita, diferenca, status
# MAGIC FROM   gold.criticas_cosif_4060
# MAGIC WHERE  critica_id = 'COS00802' AND coluna_logica = 'Z0000002';
# MAGIC ```
# MAGIC
# MAGIC Não há `Z0000001`: no leiaute a líder é o bloco 3, não uma assemelhada —
# MAGIC emiti-la como assemelhada faria `SOMA_PRUDENCIAL` contá-la duas vezes.
# MAGIC
# MAGIC Os DOIS comparadores importam: `comparador` testa o lado que dispara,
# MAGIC `comparador_direita` testa a ausência do registro esperado (quando a
# MAGIC contrapartida é despesa, negativa, o gatilho é `>= 0`).

# COMMAND ----------

import uuid
from functools import reduce

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog")
dbutils.widgets.text("silver_schema", "silver")
dbutils.widgets.text("gold_schema", "gold")
dbutils.widgets.text("reference_schema", "reference")

CATALOG = dbutils.widgets.get("catalog")
SILVER_SCHEMA = dbutils.widgets.get("silver_schema")
GOLD_SCHEMA = dbutils.widgets.get("gold_schema")
REFERENCE_SCHEMA = dbutils.widgets.get("reference_schema")

DOCUMENTO = "4060"
_PIPELINE_RUN_ID = f"run_{uuid.uuid4()}"

STATUS_OK = "OK"
STATUS_BLOQUEADO = "BLOQUEADO"
STATUS_INDETERMINADO = "INDETERMINADO"

# Tolerância de fechamento: 1 centavo. Abaixo disso é ruído de arredondamento.
TOL_CENTAVO = F.lit(0.01)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Valores por coluna lógica
# MAGIC Reconstrói o eixo de avaliação a partir dos blocos do documento.

# COMMAND ----------

entidade = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr{DOCUMENTO}_saldos_entidade")
consolidado = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.scr{DOCUMENTO}_saldos_consolidado")

valores = entidade.select(
    "codigo_conglomerado", "dt_base", "dt_base_mes",
    F.col("entidade_id").alias("coluna_logica"),
    F.lit("entidade").alias("tipo_coluna"),
    "codigo_conta",
    F.col("saldo").cast("double").alias("valor"),
).unionByName(
    reduce(
        lambda a, b: a.unionByName(b),
        [
            consolidado.select(
                "codigo_conglomerado", "dt_base", "dt_base_mes",
                F.concat_ws("#", F.col("bloco"), F.lit(sufixo)).alias("coluna_logica"),
                F.lit("consolidado").alias("tipo_coluna"),
                "codigo_conta",
                F.col(coluna).cast("double").alias("valor"),
            )
            for sufixo, coluna in (
                ("AGLUTINADO", "saldo_aglutinado"),
                ("ELIMINACOES", "valor_eliminacoes"),
                ("CONSOLIDADO", "saldo_consolidado"),
            )
        ],
    )
).filter(F.col("codigo_conta").isNotNull())

eixo = valores.select(
    "codigo_conglomerado", "dt_base", "dt_base_mes", "coluna_logica", "tipo_coluna"
).distinct()

# Data-base anterior, para as críticas que avaliam VARIAÇÃO mensal.
anterior = valores.select(
    "codigo_conglomerado",
    F.add_months(F.col("dt_base"), 1).alias("dt_base"),   # alinha t-1 em t
    "coluna_logica", "codigo_conta",
    F.col("valor").alias("valor_anterior"),
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Agregação dos dois lados
# MAGIC Soma dos saldos × peso. `variacao_mensal` usa a diferença contra a data-base
# MAGIC anterior; `fator_anexo_i` multiplica pelo percentual da Res. BCB 352;
# MAGIC `modulo` soma em valor absoluto (`|a|+|b|` ≠ `|a+b|`).

# COMMAND ----------

spec = spark.table(f"{CATALOG}.{REFERENCE_SCHEMA}.criticas_cosif").filter(
    (F.col("documento") == DOCUMENTO) & F.col("is_ativo")
)

anexo_fqn = f"{CATALOG}.{REFERENCE_SCHEMA}.cosif_anexo_i_res352"
if spark.catalog.tableExists(anexo_fqn):
    fatores = spark.table(anexo_fqn).select(
        F.col("referencia").alias("fator_anexo_i"),
        F.col("fator").cast("double").alias("fator"),
    )
else:
    print(f"AVISO — {anexo_fqn} ausente; críticas com fator do Anexo I ficarão indeterminadas")
    fatores = spark.createDataFrame([], "fator_anexo_i string, fator double")


def agregar_lado(coluna_contas: str, lado: str):
    """Soma um lado da crítica por (crítica, coluna lógica, data-base)."""
    contas = (
        spec.select("critica_id", f"modulo_{lado}", F.explode(coluna_contas).alias("c"))
        .select(
            "critica_id",
            F.col(f"modulo_{lado}").alias("modulo"),
            F.col("c.conta").alias("codigo_conta"),
            F.col("c.peso").cast("double").alias("peso"),
            F.col("c.variacao_mensal").alias("variacao_mensal"),
            F.col("c.fator_anexo_i").alias("fator_anexo_i"),
        )
    )
    juncao = ["codigo_conglomerado", "dt_base", "coluna_logica", "codigo_conta"]
    resolvido = (
        eixo.join(contas, how="cross")
        .join(valores.select(*juncao, "valor"), on=juncao, how="left")
        .join(anterior, on=juncao, how="left")
        .join(fatores, on="fator_anexo_i", how="left")
        .withColumn(
            "valor_base",
            F.when(
                F.col("variacao_mensal"),
                # Sem a data-base anterior não há variação a apurar.
                F.when(
                    F.col("valor").isNotNull() & F.col("valor_anterior").isNotNull(),
                    F.col("valor") - F.col("valor_anterior"),
                ),
            ).otherwise(F.col("valor")),
        )
        .withColumn(
            "parcela",
            F.col("peso") * F.col("valor_base")
            * F.coalesce(F.col("fator"), F.lit(1.0)),
        )
        # O módulo é aplicado ANTES da agregação, não dentro dela: `when` em volta
        # de agregados é frágil, e assim `sum` fica com uma única forma.
        .withColumn(
            "parcela_somada",
            F.when(F.col("modulo"), F.abs(F.col("parcela"))).otherwise(F.col("parcela")),
        )
    )
    return (
        resolvido.groupBy(
            "codigo_conglomerado", "dt_base", "dt_base_mes",
            "coluna_logica", "tipo_coluna", "critica_id",
        )
        .agg(
            F.sum("parcela_somada").alias(f"soma_{lado}"),
            F.count("*").alias(f"citadas_{lado}"),
            F.count("valor_base").alias(f"resolvidas_{lado}"),
        )
    )


chaves = ["codigo_conglomerado", "dt_base", "dt_base_mes",
          "coluna_logica", "tipo_coluna", "critica_id"]

lados = (
    agregar_lado("contas_esquerda", "esquerda")
    .join(agregar_lado("contas_direita", "direita"), on=chaves, how="full_outer")
    .fillna({"soma_esquerda": 0.0, "soma_direita": 0.0,
             "citadas_esquerda": 0, "citadas_direita": 0,
             "resolvidas_esquerda": 0, "resolvidas_direita": 0})
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Os cinco operadores
# MAGIC O comparador vem da regra, então `SALDO_INDEVIDO` cobre "não pode ter saldo"
# MAGIC (`<>`) e "não pode ser positivo" (`>`) sem operador novo.

# COMMAND ----------

def compara(esq, dir_, operador_col):
    """`esq <comparador> dir`, com o comparador vindo da regra."""
    return (
        F.when(operador_col == F.lit(">"), esq > dir_)
        .when(operador_col == F.lit(">="), esq >= dir_)
        .when(operador_col == F.lit("<"), esq < dir_)
        .when(operador_col == F.lit("<="), esq <= dir_)
        .when(operador_col == F.lit("<>"), esq != dir_)
        .when(operador_col == F.lit("="), esq == dir_)
    )


com_regra = lados.join(
    spec.select(
        "critica_id", "critica_seq", "origem", "tipo_critica", "criticality",
        "dimensao_r18", "descricao", "operador", "comparador", "comparador_direita",
        "tolerancia", "tolerancia_pct", "simetrico", "ignora_quando_tudo_zero",
    ),
    on="critica_id", how="inner",
)

_esq, _dir = F.col("soma_esquerda"), F.col("soma_direita")
_zero = F.lit(0.0)

# Gatilho e contrapartida, para o operador CONTRAPARTIDA_AUSENTE.
_gatilho = compara(_esq, _zero, F.col("comparador"))
_sem_contrapartida = compara(_dir, _zero, F.col("comparador_direita"))

violado = (
    F.when(
        F.col("operador") == F.lit("TOTAL_DIFERE_DAS_PARCELAS"),
        F.abs(_esq - _dir) > F.greatest(F.col("tolerancia"), TOL_CENTAVO),
    )
    .when(
        F.col("operador") == F.lit("CONTRAPARTIDA_AUSENTE"),
        # Forma simétrica: a origem aprova só quando os DOIS lados têm saldo,
        # então falta em qualquer um dos lados é violação.
        F.when(
            F.col("simetrico"),
            (F.abs(_esq) <= TOL_CENTAVO) != (F.abs(_dir) <= TOL_CENTAVO),
        ).otherwise(_gatilho & _sem_contrapartida),
    )
    .when(
        F.col("operador") == F.lit("SALDO_INFERIOR_AO_ESPERADO"),
        compara(_esq, _dir, F.col("comparador")),
    )
    .when(
        F.col("operador") == F.lit("SALDO_INDEVIDO"),
        compara(_esq - _dir, _zero, F.col("comparador")),
    )
    .when(
        F.col("operador") == F.lit("DIVERGENCIA_ACIMA_DA_TOLERANCIA"),
        # Com SINAL, como a origem escreve. O texto do BCB fala em "diferença
        # superior a X%", que é magnitude — a origem só testa um sentido. Está
        # registrado como achado; trocar para módulo é decisão do cliente.
        compara(_esq, F.coalesce(F.col("tolerancia_pct"), _zero) * _dir,
                F.col("comparador")),
    )
)

# Conta citada que não veio no documento: não se assume zero.
_faltando = (
    (F.col("citadas_esquerda") > F.col("resolvidas_esquerda"))
    | (F.col("citadas_direita") > F.col("resolvidas_direita"))
)
# Guarda da origem: nada informado nas contas da crítica → nada a avaliar.
_nada_a_avaliar = (
    F.col("ignora_quando_tudo_zero")
    & (F.abs(_esq) <= TOL_CENTAVO)
    & (F.abs(_dir) <= TOL_CENTAVO)
)

resultado = com_regra.select(
    "codigo_conglomerado", "dt_base", "dt_base_mes",
    "coluna_logica", "tipo_coluna",
    "critica_id", "critica_seq", "origem", "tipo_critica", "criticality",
    "dimensao_r18", "descricao", "operador",
    _esq.cast("decimal(20,2)").alias("soma_esquerda"),
    _dir.cast("decimal(20,2)").alias("soma_direita"),
    (_esq - _dir).cast("decimal(20,2)").alias("diferenca"),
    F.col("tolerancia").cast("decimal(20,2)").alias("tolerancia"),
    F.when(_faltando, F.lit(STATUS_INDETERMINADO))
     .when(_nada_a_avaliar, F.lit(STATUS_OK))
     .when(violado.isNull(), F.lit(STATUS_INDETERMINADO))
     .when(violado, F.lit(STATUS_BLOQUEADO))
     .otherwise(F.lit(STATUS_OK)).alias("status"),
    (F.col("citadas_esquerda") + F.col("citadas_direita")).alias("contas_citadas"),
    (F.col("resolvidas_esquerda") + F.col("resolvidas_direita")).alias("contas_resolvidas"),
    F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
    F.current_timestamp().alias("_gold_timestamp"),
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Crítica estrutural
# MAGIC Sobre a FORMAÇÃO do documento — não cabe como linha de `criticas_cosif`.
# MAGIC
# MAGIC | Código | Regra |
# MAGIC |---|---|
# MAGIC | `SOMA_PRUDENCIAL` | aglutinado do bloco 5 = bloco 3 + `saldoContabil` das assemelhadas |

# COMMAND ----------

# Seq reservado (fora da faixa das críticas), para nunca colidir. É por ele que
# os checks DQX recortam a crítica.
SEQ_ESTRUTURAL = {"SOMA_PRUDENCIAL": 900001}


def estrutural(df, critica_id, descricao, dim, esquerdo, direito, coluna_logica):
    return df.select(
        "codigo_conglomerado", "dt_base", "dt_base_mes",
        coluna_logica.alias("coluna_logica"),
        F.lit("estrutural").alias("tipo_coluna"),
        F.lit(critica_id).alias("critica_id"),
        F.lit(SEQ_ESTRUTURAL[critica_id]).alias("critica_seq"),
        F.lit("critica_bcb").alias("origem"),
        F.lit("E").alias("tipo_critica"),
        F.lit("error").alias("criticality"),
        F.lit(dim).alias("dimensao_r18"),
        F.lit(descricao).alias("descricao"),
        F.lit("TOTAL_DIFERE_DAS_PARCELAS").alias("operador"),
        esquerdo.cast("decimal(20,2)").alias("soma_esquerda"),
        direito.cast("decimal(20,2)").alias("soma_direita"),
        (esquerdo - direito).cast("decimal(20,2)").alias("diferenca"),
        F.lit(0.01).cast("decimal(20,2)").alias("tolerancia"),
        F.when(F.abs(esquerdo - direito) > TOL_CENTAVO, F.lit(STATUS_BLOQUEADO))
         .otherwise(F.lit(STATUS_OK)).alias("status"),
        F.lit(2).alias("contas_citadas"),
        F.lit(2).alias("contas_resolvidas"),
        F.lit(_PIPELINE_RUN_ID).alias("pipeline_run_id"),
        F.current_timestamp().alias("_gold_timestamp"),
    )


k = ["codigo_conglomerado", "dt_base", "dt_base_mes", "codigo_conta"]

base_soma = (
    consolidado.filter(F.col("bloco") == "consolidadoPrudencial")
    .select(*k, F.col("saldo_aglutinado").cast("double").alias("_prudencial"))
    .join(
        consolidado.filter(F.col("bloco") == "consolidadoPaisExterior")
        .select(*k, F.col("saldo_aglutinado").cast("double").alias("_pais_exterior")),
        on=k, how="full_outer",
    )
    .join(
        entidade.filter(F.col("bloco") == "assemelhadas")
        .groupBy(*k).agg(F.sum("saldo").cast("double").alias("_assemelhadas")),
        on=k, how="full_outer",
    )
)

partes = [
    resultado,
    estrutural(
        base_soma, "SOMA_PRUDENCIAL",
        "Aglutinado do Conglomerado Prudencial deve ser igual ao aglutinado da "
        "posicao Pais e Exterior somado ao saldo contabil das assemelhadas.",
        "8",
        F.coalesce(F.col("_prudencial"), F.lit(0.0)),
        F.coalesce(F.col("_pais_exterior"), F.lit(0.0))
        + F.coalesce(F.col("_assemelhadas"), F.lit(0.0)),
        F.concat_ws("#", F.lit("conta"), F.col("codigo_conta")),
    ),
]

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Materialização

# COMMAND ----------

fqn = f"{CATALOG}.{GOLD_SCHEMA}.criticas_cosif_{DOCUMENTO}"

# ─────────────────────────── colunas que o DQX consome ──────────────────────
# `is_bloqueante` e `is_last_refresh` são colunas REAIS, não view. Motivo: o DQX
# valida a `sql_expression` contra o schema da tabela-alvo selecionada, e apontar
# os checks para uma view deixava tudo dependente de qual alvo foi escolhido na
# Studio — o sintoma foi "invalid sql expression: 'NOT is_bloqueante'".
#
# Com as colunas na tabela, o check fica curto (cabe no teto de 10.000 caracteres
# de job parameters do dry run) E sem subquery no `filter` — que era o que
# obrigava rodar com "All rows" e dependia do grant de leitura do SP da Studio.
_janela_global = Window.partitionBy()
final = (
    reduce(lambda a, b: a.unionByName(b), partes)
    .withColumn(
        "is_bloqueante",
        F.col("status").isin(STATUS_BLOQUEADO, STATUS_INDETERMINADO),
    )
    .withColumn(
        "is_last_refresh",
        F.col("dt_base") == F.max("dt_base").over(_janela_global),
    )
)

(
    final
    .write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("dt_base")
    .saveAsTable(fqn)
)
spark.sql(
    f"ALTER TABLE {fqn} SET TBLPROPERTIES ("
    "'delta.logRetentionDuration' = 'interval 1825 days', "
    "'quality' = 'gold')"
)

display(
    spark.table(fqn)
    .groupBy("dt_base", "tipo_critica", "status")
    .agg(F.countDistinct("critica_id").alias("criticas"),
         F.count("*").alias("avaliacoes"))
    .orderBy("dt_base", "tipo_critica", "status")
)
print(f"OK — {fqn}: {spark.table(fqn).count()} linha(s)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. View de conveniência
# MAGIC Só o recorte da data-base corrente. Os checks DQX apontam para a TABELA,
# MAGIC usando as colunas `is_last_refresh` e `is_bloqueante` — não dependem desta view.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {CATALOG}.{REFERENCE_SCHEMA}.v_crit_{DOCUMENTO}_corrente AS
SELECT * FROM {fqn} WHERE is_last_refresh
""")
print(f"OK — view {CATALOG}.{REFERENCE_SCHEMA}.v_crit_{DOCUMENTO}_corrente")
