# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Exportação XML: Documentos 4010 e 4016
# MAGIC
# MAGIC Materializa os saldos sintéticos de `f_4010_saldos` (notebook 02) nos dois
# MAGIC arquivos contábeis COSIF, no **leiaute XML oficial**:
# MAGIC
# MAGIC | Documento | Nome oficial | Periodicidade | Data-base gerada | Código STA |
# MAGIC |---|---|---|---|---|
# MAGIC | **4010** | Balancete Patrimonial Analítico | mensal | `DT_BASE` | `ACOS010` |
# MAGIC | **4016** | Balanço Patrimonial Analítico | semestral | último jun/dez ≤ `DT_BASE` | `ACOS016` |
# MAGIC
# MAGIC Fonte do leiaute: *Balancete e Balanço Patrimonial Analítico — Documentos
# MAGIC 4010/4016, Instruções de Preenchimento* (Desig/BCB),
# MAGIC `bcb.gov.br/content/estabilidadefinanceira/cosif_leiautes/Leiaute_4010_xmlV1.pdf`.
# MAGIC O XML passou a ser obrigatório na data-base jan/2025 (**IN BCB 469/2024**),
# MAGIC substituindo o arquivo posicional.
# MAGIC
# MAGIC ```xml
# MAGIC <documento codigoDocumento="4010" cnpj="99999999" dataBase="2026-03" tipoRemessa="I">
# MAGIC   <contas>
# MAGIC     <conta codigoConta="0031000000" saldo="321460997.24" />
# MAGIC   </contas>
# MAGIC </documento>
# MAGIC ```
# MAGIC
# MAGIC ## Diferença de conteúdo entre os dois documentos
# MAGIC O 4016 representa a posição contábil **após a apuração do resultado do
# MAGIC exercício**, então NÃO traz contas dos grupos 7 (Receitas) e 8 (Despesas)
# MAGIC — §3.2.2.a das Instruções. É essa a regra que o check DQX
# MAGIC `sem_contas_de_resultado_grupos_7_8` valida em `silver.scr4016_saldos`.
# MAGIC
# MAGIC ## ⚠️ Sem validador oficial
# MAGIC Não existe binário validador do 4010/4016 no repo (o BCB oferece o
# MAGIC bcValidador + XSD publicados na mesma página do leiaute). Aqui validamos o
# MAGIC que é verificável localmente: formato/DV de cada conta, domínio de
# MAGIC `tipoRemessa`, padrão `AAAA-MM` da data-base e boa-formação do XML.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Plano_Contas

# COMMAND ----------

import os
import re
from decimal import Decimal
from xml.etree import ElementTree as ET

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## Monta o elenco de contas de cada documento
# MAGIC As rubricas de batimento vêm de `f_4010_saldos` (já com as divergências
# MAGIC injetadas). As contas de contexto são derivadas do total de créditos (T01)
# MAGIC para o balancete não ficar só com a carteira de crédito.

# COMMAND ----------

fqn_saldos = f"{CATALOG}.{SCHEMA}.f_4010_saldos"
saldos = spark.table(fqn_saldos).filter(F.col("dt_base") == F.lit(DT_BASE))

rubricas = [
    (conta_arquivo(r["cosif_conta"]), Decimal(r["saldo_cosif"]))
    for r in saldos.select("cosif_conta", "saldo_cosif").collect()
]
if not rubricas:
    raise ValueError(f"{fqn_saldos} sem linhas para dt_base={DT_BASE} — rode o notebook 02 antes.")

# Total de créditos (T01) como base das contas de contexto.
_t01 = conta_arquivo(next(r[2] for r in PLANO_CONTAS_COSIF if r[1] == "T01"))
total_creditos = next((v for c, v in rubricas if c == _t01), Decimal(0))


def contas_do_documento(documento):
    """Elenco (conta, saldo) do documento — o 4016 exclui os grupos 7 e 8."""
    contas = list(rubricas)
    for conta, _desc, fracao, so_no_4010 in CONTAS_CONTEXTO:
        if so_no_4010 and documento != "4010":
            continue
        contas.append((conta, (total_creditos * Decimal(str(fracao))).quantize(Decimal("0.01"))))
    return sorted(contas)


# COMMAND ----------

# MAGIC %md
# MAGIC ## Data-base do 4016 (semestral)
# MAGIC §2.1.4: "o documento 4016 tem periodicidade semestral, sendo esperado para
# MAGIC os meses de junho e dezembro". Geramos o último semestre FECHADO até a
# MAGIC data-base corrente — o Balanço de 30/06 ou 31/12 anterior.

# COMMAND ----------

_ano, _mes = (int(x) for x in DT_BASE.split("-"))
if _mes >= 12:
    DT_BASE_4016 = f"{_ano}-12"
elif _mes >= 6:
    DT_BASE_4016 = f"{_ano}-06"
else:
    DT_BASE_4016 = f"{_ano - 1}-12"

print(f"Data-base 4010 (mensal):    {DT_BASE}")
print(f"Data-base 4016 (semestral): {DT_BASE_4016}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Geração do XML + validações locais

# COMMAND ----------

_RE_DATA_BASE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")     # §3.1.2.d — AAAA-MM
_RE_SALDO = re.compile(r"^\d{1,16}\.\d{2}$")               # §3.2.2.b — até 18 pos, 2 decimais
_TIPO_REMESSA = {"I", "S"}                                 # §3.1.2.e


def gera_xml(documento, cnpj, data_base, contas, tipo_remessa="I"):
    """Serializa o documento no leiaute oficial, validando campo por campo."""
    if documento not in {"4010", "4016"}:
        raise ValueError(f"codigoDocumento deve ser 4010 ou 4016, veio {documento!r}")
    if not (len(cnpj) == 8 and cnpj.isalnum()):
        raise ValueError(f"cnpj deve ter 8 caracteres alfanuméricos, veio {cnpj!r}")
    if not _RE_DATA_BASE.match(data_base):
        raise ValueError(f"dataBase deve seguir AAAA-MM, veio {data_base!r}")
    if tipo_remessa not in _TIPO_REMESSA:
        raise ValueError(f"tipoRemessa deve ser I ou S, veio {tipo_remessa!r}")

    raiz = ET.Element("documento", {
        "codigoDocumento": documento,
        "cnpj": cnpj,
        "dataBase": data_base,
        "tipoRemessa": tipo_remessa,
    })
    bloco = ET.SubElement(raiz, "contas")
    for conta, saldo in contas:
        valida_conta(conta)                                # formato + DV
        # O leiaute não tem campo de sinal: informa-se o saldo de fechamento.
        texto = f"{abs(Decimal(saldo)):.2f}"
        if not _RE_SALDO.match(texto):
            raise ValueError(f"saldo {texto!r} fora do formato do leiaute (conta {conta})")
        ET.SubElement(bloco, "conta", {"codigoConta": conta, "saldo": texto})

    ET.indent(raiz, space="    ")
    corpo = ET.tostring(raiz, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{corpo}\n'.encode("utf-8")


# COMMAND ----------

# MAGIC %md
# MAGIC ## Escrita no Volume (UC)
# MAGIC `os.makedirs` não cria o volume raiz em UC (Errno 95) — garantimos schema +
# MAGIC volume via SQL antes, igual aos geradores 3040/3050.

# COMMAND ----------

_parts = VOLUME_OUT.strip("/").split("/")
if len(_parts) >= 4 and _parts[0] == "Volumes":
    _vol_cat, _vol_sch, _vol_name = _parts[1], _parts[2], _parts[3]
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{_vol_cat}`.`{_vol_sch}`")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS `{_vol_cat}`.`{_vol_sch}`.`{_vol_name}`")

os.makedirs(VOLUME_OUT, exist_ok=True)

gerados = []
for documento, data_base in (("4010", DT_BASE), ("4016", DT_BASE_4016)):
    contas = contas_do_documento(documento)
    xml_bytes = gera_xml(documento, CNPJ_IF, data_base, contas)

    # Sanidade: o arquivo tem de ser XML bem-formado e reabrir com o mesmo elenco.
    reparsed = ET.fromstring(xml_bytes)
    assert reparsed.get("codigoDocumento") == documento
    assert len(reparsed.findall("./contas/conta")) == len(contas)
    if documento == "4016":
        # Grupo = 1º dígito SIGNIFICATIVO (as contas vêm zero-preenchidas até 10).
        grupos = {
            str(int(c.get("codigoConta")))[0]
            for c in reparsed.findall("./contas/conta")
        }
        assert not (grupos & {"7", "8"}), f"4016 não pode ter contas dos grupos 7/8: {grupos}"

    fname = f"Doc{documento}_{CNPJ_IF}_{data_base}.xml"
    fpath = os.path.join(VOLUME_OUT, fname)
    with open(fpath, "wb") as fh:
        fh.write(xml_bytes)
    gerados.append((documento, data_base, fname, len(contas), os.path.getsize(fpath)))
    print(f"✓ {fname}: {len(contas)} contas, {os.path.getsize(fpath):,} bytes → {fpath}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumo
# MAGIC Para ingerir estes arquivos no core, copie-os para a landing do bundle
# MAGIC principal (`{catalog}.landing.scr_xml/4010/` e `/4016/`) e rode
# MAGIC `databricks bundle run bronze` — as tasks `raw_4010`/`raw_4016` leem cada
# MAGIC uma a sua pasta.

# COMMAND ----------

for documento, data_base, fname, n_contas, tamanho in gerados:
    print(f"{documento} | data-base {data_base} | {n_contas:>2} contas | {tamanho:>6,} bytes | {fname}")
