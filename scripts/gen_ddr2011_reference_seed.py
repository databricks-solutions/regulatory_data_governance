#!/usr/bin/env python3
"""Gera `notebooks/setup/setup_reference_2011.py` a partir do leiaute oficial do BCB.

Os 7 anexos do CADOC 2011 (DDR) somam ~530 domínios — contas (90), moedas (185)
e países (248) são grandes demais para transcrever à mão sem erro. Este script
lê a aba `Anexos` do XLS oficial e EMITE o notebook de seed com os domínios
embutidos, de forma que o notebook seja autocontido em runtime (sem depender de
arquivo sincronizado pelo bundle).

Rode novamente quando o BCB publicar uma versão nova do leiaute:

    python scripts/gen_ddr2011_reference_seed.py

Fonte: docs/ddr2011/Leiaute_DDR_2011_v5_01072023.xls (aba `Anexos`), baixado de
https://www.bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011

⚠️ `docs/` é git-ignored neste repositório, então o XLS de origem NÃO é versionado
— apenas o notebook gerado é. Um clone novo roda o seed sem problema (o notebook é
autocontido), mas para REGENERAR é preciso baixar o leiaute da página do BCB antes:

    curl -sSL -o docs/ddr2011/Leiaute_DDR_2011_v5_01072023.xls \\
      'https://www.bcb.gov.br/content/estabilidadefinanceira/Leiautes2011/Atual/informacoes_tecnicas/Leiaute_DDR_2011_Versao_Publicacao.v5%2001072023.xls'
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
XLS = REPO / "docs/ddr2011/Leiaute_DDR_2011_v5_01072023.xls"
OUT = REPO / "notebooks/setup/setup_reference_2011.py"

# Leiaute vigente a partir de 01/07/2023 (v5) — carimbado em `leiaute_versao`.
LEIAUTE_VERSAO = "DDRv5"

# Anexo → (campo em `reference.dominios`, rótulo humano). A ordem é a do XLS.
ANEXOS = {
    1: ("tipoEnvio", "Indicador de inclusão ou alteração de documento"),
    2: ("codigoParametro", "Código do parâmetro"),
    3: ("codigoElemento", "Código do elemento de cálculo"),
    4: ("Conta", "Contas do DDR"),
    5: ("moeda", "Moedas"),
    6: ("posicaoPaisExterior", "Posição País/Exterior"),
    7: ("pais", "País"),
}


def _clean(value) -> str:
    """Normaliza uma célula do XLS em texto de uma linha."""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _as_date(value) -> str | None:
    if value is None or str(value) == "nan":
        return None
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%Y-%m-%d")
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def extract() -> dict[int, list[tuple[str, str, str, str | None]]]:
    """{numero_anexo: [(codigo, descricao, dt_vigencia_ini, dt_vigencia_fim)]}."""
    raw = pd.ExcelFile(XLS).parse("Anexos", header=None)
    raw = raw.dropna(how="all").dropna(axis=1, how="all")

    out: dict[int, list[tuple[str, str, str, str | None]]] = {}
    current: int | None = None

    for _, row in raw.iterrows():
        cells = row.tolist()
        first = _clean(cells[0]) if str(cells[0]) != "nan" else ""

        header = re.match(r"^Anexo\s+(\d+)\s*[:–-]", first)
        if header:
            current = int(header.group(1))
            out[current] = []
            continue

        if current is None or not first:
            continue
        # Linha de cabeçalho da tabela do anexo.
        if first.lower() in {"domínio", "dominio", "código", "codigo"}:
            continue

        descricao = _clean(cells[1]) if len(cells) > 1 and str(cells[1]) != "nan" else ""
        if not descricao:
            continue
        dt_ini = _as_date(cells[2] if len(cells) > 2 else None) or "2020-02-01"
        dt_fim = _as_date(cells[3] if len(cells) > 3 else None)
        out[current].append((first, descricao, dt_ini, dt_fim))

    return out


def _py_literal(value: str | None) -> str:
    if value is None:
        return "None"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(anexos: dict[int, list[tuple[str, str, str, str | None]]]) -> str:
    blocks: list[str] = []
    for numero, (campo, rotulo) in ANEXOS.items():
        rows = anexos.get(numero, [])
        if not rows:
            raise SystemExit(f"Anexo {numero} ({rotulo}) veio vazio do XLS — abortando.")
        lines = [
            f"# Anexo {numero} — {rotulo} ({len(rows)} domínios).",
            f"_ANEXO_{numero} = [",
        ]
        for codigo, descricao, dt_ini, dt_fim in rows:
            lines.append(
                f"    ({_py_literal(codigo)}, {_py_literal(descricao)}, "
                f"{_py_literal(dt_ini)}, {_py_literal(dt_fim)}),"
            )
        lines.append("]")
        blocks.append("\n".join(lines))

    contagens = " · ".join(
        f"Anexo {n} {ANEXOS[n][0]}: {len(anexos[n])}" for n in sorted(ANEXOS)
    )
    dados = "\n\n".join(blocks)
    mapa = "\n".join(
        f'    ({numero}, "{ANEXOS[numero][0]}", _ANEXO_{numero}),' for numero in sorted(ANEXOS)
    )

    return f'''# Databricks notebook source
# MAGIC %md
# MAGIC # Setup Reference — CADOC 2011 (DDR)
# MAGIC
# MAGIC ⚠️ **ARQUIVO GERADO — não editar à mão.** Regenere com
# MAGIC `python scripts/gen_ddr2011_reference_seed.py` quando o BCB publicar uma
# MAGIC versão nova do leiaute.
# MAGIC
# MAGIC Semeia os domínios do **Documento 2011 — DDR** (*Demonstrativo Diário de
# MAGIC Acompanhamento das Parcelas de Requerimento de Capital e dos Limites
# MAGIC Operacionais*, periodicidade **diária**) em `reference.dominios` e cria as
# MAGIC views de domínio consumidas pelos checks DQX.
# MAGIC
# MAGIC Fonte: leiaute oficial v5 (vigente a partir de 01/07/2023), aba `Anexos` de
# MAGIC `docs/ddr2011/Leiaute_DDR_2011_v5_01072023.xls` —
# MAGIC bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011
# MAGIC
# MAGIC Domínios semeados: {contagens}.
# MAGIC
# MAGIC Os anexos grandes (contas, moedas, países) existem porque os checks DQX de
# MAGIC domínio fazem `col IN (SELECT valor_codigo FROM reference.v_dom_2011_*)` — a
# MAGIC `expression` do DQX Studio não aceita literais string (o `parse_json` inline
# MAGIC os corrompe), então a lista tem de viver numa view.
# MAGIC
# MAGIC Idempotente: apaga as linhas `documento = '2011'` antes de reinserir.

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Reference Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

DOCUMENTO = "2011"
LEIAUTE_VERSAO = "{LEIAUTE_VERSAO}"

print(f"Semeando domínios do CADOC {{DOCUMENTO}} em {{CATALOG}}.{{SCHEMA}}.dominios")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Domínios oficiais (Anexos 1 a 7 do leiaute)

# COMMAND ----------

{dados}

# (numero_anexo, campo em reference.dominios, linhas)
_ANEXOS = [
{mapa}
]

# COMMAND ----------
# MAGIC %md
# MAGIC ## Carga em `reference.dominios`
# MAGIC
# MAGIC A tabela é criada por `setup_reference_tables.py` (task anterior do mesmo
# MAGIC job). Aqui só inserimos — com `CREATE TABLE IF NOT EXISTS` defensivo para o
# MAGIC caso deste notebook rodar isolado.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {{CATALOG}}.{{SCHEMA}}.dominios (
    dominio_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    documento STRING NOT NULL,
    campo STRING NOT NULL,
    valor_codigo STRING NOT NULL,
    valor_descricao STRING NOT NULL,
    anexo_referencia STRING,
    leiaute_versao STRING NOT NULL,
    dt_vigencia_ini DATE NOT NULL,
    dt_vigencia_fim DATE,
    is_current BOOLEAN NOT NULL,
    observacoes STRING
)
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# Idempotência: este notebook é dono EXCLUSIVO das linhas do documento 2011.
spark.sql(f"DELETE FROM {{CATALOG}}.{{SCHEMA}}.dominios WHERE documento = '{{DOCUMENTO}}'")

_registros = []
for _numero, _campo, _linhas in _ANEXOS:
    for _codigo, _descricao, _dt_ini, _dt_fim in _linhas:
        _registros.append(
            (
                DOCUMENTO,
                _campo,
                _codigo,
                _descricao,
                f"Anexo {{_numero}}",
                LEIAUTE_VERSAO,
                _dt_ini,
                _dt_fim,
                _dt_fim is None,   # is_current: sem data-fim = vigente
                None,
            )
        )

_df = spark.createDataFrame(
    _registros,
    "documento STRING, campo STRING, valor_codigo STRING, valor_descricao STRING, "
    "anexo_referencia STRING, leiaute_versao STRING, dt_vigencia_ini STRING, "
    "dt_vigencia_fim STRING, is_current BOOLEAN, observacoes STRING",
).selectExpr(
    "documento", "campo", "valor_codigo", "valor_descricao", "anexo_referencia",
    "leiaute_versao", "CAST(dt_vigencia_ini AS DATE) AS dt_vigencia_ini",
    "CAST(dt_vigencia_fim AS DATE) AS dt_vigencia_fim", "is_current", "observacoes",
)
_df.write.mode("append").saveAsTable(f"{{CATALOG}}.{{SCHEMA}}.dominios")

print(f"  {{len(_registros)}} domínios do CADOC {{DOCUMENTO}} inseridos.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Views de domínio para os checks DQX
# MAGIC
# MAGIC Uma view por campo, com o filtro `documento`/`campo` encapsulado — o check
# MAGIC no DQX Studio fica só com
# MAGIC `col IN (SELECT valor_codigo FROM reference.v_dom_2011_<campo>)`, sem literal
# MAGIC string. Mesma convenção das views `v_dom_3040_*`.

# COMMAND ----------

for _campo, _view in [
    ("tipoEnvio", "v_dom_2011_tipoenvio"),
    ("codigoParametro", "v_dom_2011_parametro"),
    ("codigoElemento", "v_dom_2011_elemento"),
    ("Conta", "v_dom_2011_conta"),
    ("moeda", "v_dom_2011_moeda"),
    ("posicaoPaisExterior", "v_dom_2011_posicao"),
    ("pais", "v_dom_2011_pais"),
]:
    spark.sql(f"""
        CREATE OR REPLACE VIEW {{CATALOG}}.{{SCHEMA}}.{{_view}} AS
        SELECT valor_codigo
        FROM {{CATALOG}}.{{SCHEMA}}.dominios
        WHERE documento = '{{DOCUMENTO}}' AND campo = '{{_campo}}' AND is_current
    """)
    print(f"  view {{_view}} pronta")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Datas-base válidas (dias úteis do calendário BCB)
# MAGIC
# MAGIC O DDR é o único CADOC **diário** do acelerador, então "a data-base é dia
# MAGIC útil" é um check próprio dele. A view expõe só a coluna `data` dos dias
# MAGIC úteis para o check ficar em `dt_base IN (SELECT data FROM …)`, sem literal.
# MAGIC
# MAGIC Depende de `reference.bcb_calendar`, criada pela task `setup_reference` —
# MAGIC que é predecessora desta em `setup_job.yml` e no `rc18_end_to_end`.

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE VIEW {{CATALOG}}.{{SCHEMA}}.v_dom_2011_data_base AS
    SELECT data
    FROM {{CATALOG}}.{{SCHEMA}}.bcb_calendar
    WHERE is_dia_util
""")
print("  view v_dom_2011_data_base pronta (dias úteis do calendário BCB)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Status bloqueante das críticas do DDR
# MAGIC
# MAGIC `gold.criticas_ddr_2011` materializa as duas críticas INTRA-documento do BCB
# MAGIC (4693 e 4751) com uma coluna `status`; o check DQX faz
# MAGIC `status NOT IN (SELECT valor_codigo FROM v_crit_2011_status_bloqueante)`.
# MAGIC Mesmo padrão de `v_recon_status_bloqueante` para o batimento COSIF.

# COMMAND ----------

spark.sql(f"""
INSERT INTO {{CATALOG}}.{{SCHEMA}}.dominios
    (documento, campo, valor_codigo, valor_descricao, anexo_referencia,
     leiaute_versao, dt_vigencia_ini, dt_vigencia_fim, is_current, observacoes)
VALUES
  ('{{DOCUMENTO}}', 'CriticaStatusBloqueante', 'BLOQUEADO',
   'Crítica intra-documento do DDR violada — impede a remessa',
   'Críticas de Pós-processamento 2011 V2', '{{LEIAUTE_VERSAO}}',
   DATE'2020-03-01', NULL, true, NULL)
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {{CATALOG}}.{{SCHEMA}}.v_crit_2011_status_bloqueante AS
    SELECT valor_codigo
    FROM {{CATALOG}}.{{SCHEMA}}.dominios
    WHERE documento = '{{DOCUMENTO}}' AND campo = 'CriticaStatusBloqueante' AND is_current
""")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Resumo

# COMMAND ----------

display(
    spark.sql(f"""
        SELECT campo, anexo_referencia, COUNT(*) AS dominios,
               SUM(CASE WHEN is_current THEN 1 ELSE 0 END) AS vigentes
        FROM {{CATALOG}}.{{SCHEMA}}.dominios
        WHERE documento = '{{DOCUMENTO}}'
        GROUP BY campo, anexo_referencia
        ORDER BY anexo_referencia, campo
    """)
)
print(f"Domínios do CADOC {{DOCUMENTO}} prontos em {{CATALOG}}.{{SCHEMA}}.dominios")
'''


def main() -> None:
    if not XLS.exists():
        raise SystemExit(f"leiaute oficial não encontrado: {XLS}")
    anexos = extract()
    for numero in sorted(ANEXOS):
        print(f"Anexo {numero} ({ANEXOS[numero][0]}): {len(anexos.get(numero, []))} domínios")
    OUT.write_text(render(anexos), encoding="utf-8")
    print(f"\nGerado {OUT.relative_to(REPO)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
