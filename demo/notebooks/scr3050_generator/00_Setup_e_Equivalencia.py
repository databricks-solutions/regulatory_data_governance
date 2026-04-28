# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Setup e Equivalência (SCR Doc 3050 / TXB V11)
# MAGIC
# MAGIC Configuração global do gerador sintético do Documento 3050 (BACEN — Estatísticas
# MAGIC Agregadas de Crédito e Arrendamento Mercantil, formato **TXB V11**). Define:
# MAGIC
# MAGIC 1. Parâmetros da remessa (DtBase, CNPJ, contato, Volume de saída, XSD).
# MAGIC 2. Dicionário **DE/PARA** `3040 → 3050` com codificação TXB real
# MAGIC    (`Schema_TXB_V11.xsd` — root `<DocTXB>`).
# MAGIC 3. Tabela de **modelos de atributos** por (segmento, encargo, modalidade) —
# MAGIC    extraída do XSD. Cada elemento-folha tem um "modelo" (1-5 diário, 1-7
# MAGIC    mensal) que define quais atributos são obrigatórios/opcionais.
# MAGIC 4. Helpers para cálculo de datas, formatação e derivação de encargo.
# MAGIC
# MAGIC **Princípio:** este gerador *consome* as tabelas produzidas pelo
# MAGIC `SCR_Doc3040_Generator` (`f_3040_clientes`, `f_3040_operacoes`, `f_3040_vencimentos`).
# MAGIC Nunca gera novos microdados — assim garantimos consistência matemática
# MAGIC entre o 3040 individual e o 3050 agregado (Regra de Ouro #1).
# MAGIC
# MAGIC > Referências: `docs/scr3050/Instrucoes_de_preenchimento_Documento_3050.pdf`,
# MAGIC > `Schema_TXB_V11.xsd` (no Volume `/Volumes/rc18_demo/ferramentas/validador/xsd/`).

# COMMAND ----------

dbutils.widgets.text("dt_base", "2026-03", "Data-base (YYYY-MM)")
dbutils.widgets.text("cnpj_if", "99999999", "CNPJ-base da IF (8 dígitos)")
dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Schema das tabelas staging/finais")
dbutils.widgets.text("volume_out", "/Volumes/rc18_catalog/reference/scr3050_out", "Volume de saída do XML")
dbutils.widgets.text("src_prefix_3040", "rc18_catalog.reference.f_3040_",
                     "Prefixo das tabelas finais do 3040 geradas pelo SCR_Doc3040_Generator")
dbutils.widgets.text("leiaute_versao", "V11", "Versão do leiaute TXB")

DT_BASE = dbutils.widgets.get("dt_base")                # YYYY-MM
CNPJ_IF = dbutils.widgets.get("cnpj_if")                # 8 dígitos
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_OUT = dbutils.widgets.get("volume_out")
SRC_PREFIX_3040 = dbutils.widgets.get("src_prefix_3040")
LEIAUTE_VERSAO = dbutils.widgets.get("leiaute_versao")

# Contato (XSD: nmContato, telContato com pattern "XX-XXXXXXXX")
CONTATO = {
    "nmContato":  "Equipe Governança SCR",
    "telContato": "11-33000000",
}

# Indicador de remessa — "I" (Inclusão) ou "A" (Alteração) conforme XSD indRemessaType
IND_REMESSA = "I"

print(f"DtBase={DT_BASE} CNPJ={CNPJ_IF} Leiaute=TXB {LEIAUTE_VERSAO}")
print(f"Fonte 3040: {SRC_PREFIX_3040}* (clientes/operacoes/vencimentos)")
print(f"Destino XML: {VOLUME_OUT}")

# NOTA: lxml é instalado pelo ambiente serverless do job. Se rodar manualmente:
#   %pip install lxml -q
# Nunca usar restartPython aqui — apagaria os globais compartilhados via %run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Modelos de atributos (extraídos do XSD)
# MAGIC
# MAGIC Cada elemento-folha do TXB usa um "modelo" que define seus atributos. Os
# MAGIC modelos diários (1-5) contêm taxas + concessões + saldo; os mensais (1-7)
# MAGIC variam entre só-atraso (modelo_1_M) e taxa+atraso (modelo_2_M/modelo_5_M).

# COMMAND ----------

# Atributos por modelo DIÁRIO (XSD: attributeGroup modeloN_D_GrpAtrib)
# Todos os valores monetários são tipoValor = xs:integer (sem decimais!).
# Taxas são xs:decimal com 2 fraction digits. Prazos são xs:integer.
MODELO_ATTRS_DIARIO = {
    # Modelo 1 — mais comum (duplicatas, cap. giro, aquisições)
    1: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 2 — sem przDecMedConcessoes (conta garantida, cartão rotativo)
    2: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "sldCarAtiva"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 3 — sem taxas nem encargos (ind PF)
    3: {"required": ["vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 4 — mínimo (ind PF chqEspecial)
    4: {"required": ["vlrConcessoes", "sldCarAtiva"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 5 — cheque especial PF com taxa ajustada
    5: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "sldCarAtiva"],
        "optional": ["txMedJurosAjustada", "sldCedido", "sldAdquirido"]},
}

# Atributos por modelo MENSAL
MODELO_ATTRS_MENSAL = {
    # Modelo 1 — só atraso + prazo carteira (usado na maioria)
    1: {"required": ["sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": []},
    # Modelo 2 — taxa + atraso (conta garantida mensal)
    2: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva",
                     "sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 3 — ultra-mínimo (carCrdComVista)
    3: {"required": ["vlrConcessoes", "sldCarAtiva"],
        "optional": []},
    # Modelo 4 — outros créditos livres / ind modalidades
    4: {"required": ["vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva",
                     "sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 5 — completo (cheque especial mensal)
    5: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva",
                     "sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": ["sldCedido", "sldAdquirido"]},
    # Modelo 6 — só atraso (variante direcionado)
    6: {"required": ["sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": []},
    # Modelo 7 — rural (taxas com decimais extras — taxaTypeRural)
    7: {"required": ["txMedJuros", "txMedEncFiscais", "txMedEncOperacionais",
                     "vlrConcessoes", "przDecMedConcessoes", "sldCarAtiva",
                     "sldBaiPrejuizo", "sldCarAte14", "sldCarAte60",
                     "sldCarAte90", "sldCarMaior90", "przMedCarteira"],
        "optional": ["sldCedido", "sldAdquirido"]},
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Catálogo de modalidades TXB V11 — por (recursos, segmento, encargo)
# MAGIC
# MAGIC Tabela completa extraída de `Schema_TXB_V11.xsd`. Para cada chave
# MAGIC `(recursos, segmento, encargo, modalidade)` registramos o modelo
# MAGIC (diário e mensal) — o motor de agregação (02) e o gerador XML (03)
# MAGIC usam este catálogo para saber quais atributos emitir.
# MAGIC
# MAGIC > No MVP o gerador 3040 produz apenas Mod=0101 (PJ/pre/capGirPrzAte365),
# MAGIC > então a maior parte deste catálogo fica inativo. Ele existe para
# MAGIC > habilitar extensões futuras sem tocar em 02/03.

# COMMAND ----------

# Subset relevante para o MVP (Mod=0101 do 3040 → PJ/pre/capGirPrzAte365).
# Schema real no XSD: prePJDiarioType (modelo_1_D) + prePJMensalType (modelo_1_M).
# Chave: (recursos, segmento, encargo, modalidade) → (modelo_D, modelo_M).
MODALIDADE_CATALOGO = {
    # — PJ livre / pre —
    ("livre", "pesJuridica", "pre", "desDuplicatas"):      (1, 1),
    ("livre", "pesJuridica", "pre", "desCheques"):         (1, 1),
    ("livre", "pesJuridica", "pre", "antFatCarCredito"):   (1, 1),
    ("livre", "pesJuridica", "pre", "capGirPrzAte365"):    (1, 1),
    ("livre", "pesJuridica", "pre", "capGirPrzSup365"):    (1, 1),
    ("livre", "pesJuridica", "pre", "capGirTetRotativo"):  (1, 1),
    ("livre", "pesJuridica", "pre", "conGarantida"):       (2, 1),
    ("livre", "pesJuridica", "pre", "chqEspecial"):        (5, 1),
    ("livre", "pesJuridica", "pre", "aquVeiculos"):        (1, 1),
    ("livre", "pesJuridica", "pre", "aquOutBens"):         (1, 1),
    ("livre", "pesJuridica", "pre", "arrMerVeiculos"):     (1, 1),
    ("livre", "pesJuridica", "pre", "arrMerOutBens"):      (1, 1),
    ("livre", "pesJuridica", "pre", "vendor"):             (1, 1),
    ("livre", "pesJuridica", "pre", "compror"):            (1, 1),
    ("livre", "pesJuridica", "pre", "carCrdRotativo"):     (2, 1),
    ("livre", "pesJuridica", "pre", "carCrdParcelado"):    (1, 1),
    ("livre", "pesJuridica", "pre", "finExportacoes"):     (1, 1),
    ("livre", "pesJuridica", "pre", "carCrdComVista"):     (None, 3),   # só mensal
    ("livre", "pesJuridica", "pre", "outCrdLivres"):       (None, 4),   # só mensal — catch-all
    # — PF livre / pre —
    ("livre", "pesFisica", "pre", "chqEspecial"):             (5, 5),
    ("livre", "pesFisica", "pre", "crdPesNaoConsignado"):     (1, 1),
    ("livre", "pesFisica", "pre", "crdPesNaoConsignadoCG"):   (1, 1),
    ("livre", "pesFisica", "pre", "crdPesNaoConsignadoSG"):   (1, 1),
    ("livre", "pesFisica", "pre", "crdPesNaoConVinComposicao"): (1, 1),
    ("livre", "pesFisica", "pre", "crdPesConTraSetPublico"):  (1, 1),
    ("livre", "pesFisica", "pre", "crdPesConTraSetPrivado"):  (1, 1),
    ("livre", "pesFisica", "pre", "crdPesConApoINSS"):        (1, 1),
    ("livre", "pesFisica", "pre", "aquVeiculos"):             (1, 1),
    ("livre", "pesFisica", "pre", "aquOutBens"):              (1, 1),
    ("livre", "pesFisica", "pre", "carCrdRotativo"):          (2, 1),
    ("livre", "pesFisica", "pre", "carCrdParcelado"):         (1, 1),
    ("livre", "pesFisica", "pre", "arrMerVeiculos"):          (1, 1),
    ("livre", "pesFisica", "pre", "arrMerOutBens"):           (1, 1),
    ("livre", "pesFisica", "pre", "desCheques"):              (1, 1),
    # (demais encargos pre-fluxo-ipca-igpm e direcionados ficam de fora do MVP —
    #  adicionar aqui quando o 3040 gen ampliar sua cobertura de modalidades.)
}

ALL_TXB_MODALIDADES = sorted({k[3] for k in MODALIDADE_CATALOGO})
print(f"Catálogo MVP: {len(MODALIDADE_CATALOGO)} combinações, "
      f"{len(ALL_TXB_MODALIDADES)} modalidades TXB únicas.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Dicionário DE/PARA — 3040 `Mod` → 3050 TXB
# MAGIC
# MAGIC Mapeia Mod do 3040 em `(recursos, segmento_default, encargo_default, modalidade)`.
# MAGIC Segmento real sai de `cli.tp` (Anexo 11); encargo real sai de `op.indx` (Anexo 5).
# MAGIC Os "default" aqui são usados quando não há informação no microdado (fallback).

# COMMAND ----------

DE_PARA_3040_3050 = {
    # 0101 — Empréstimo/Adiantamento a depositantes (MVP do 3040 usa só este)
    # Melhor encaixe TXB: capital de giro curto prazo PJ pré-fixado.
    "0101": {"recursos": "livre", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "capGirPrzAte365"},
    # 02xx — Empréstimos
    "0201": {"recursos": "livre", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "capGirPrzAte365"},
    "0202": {"recursos": "livre", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "capGirPrzSup365"},
    "0204": {"recursos": "livre", "segmento_default": "pesFisica",
             "encargo_default": "pre", "modalidade": "crdPesNaoConsignado"},
    # 03xx — Títulos descontados
    "0301": {"recursos": "livre", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "desDuplicatas"},
    # 04xx — Financiamento imobiliário (direcionado TR)
    "0401": {"recursos": "direcionado", "segmento_default": "pesFisica",
             "encargo_default": "tr", "modalidade": "finImobTaxasRegu"},
    "0402": {"recursos": "direcionado", "segmento_default": "pesFisica",
             "encargo_default": "flu", "modalidade": "finImobTaxasMerc"},
    # 08xx — Crédito rural (direcionado)
    "0801": {"recursos": "direcionado", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "crdRurReguladas"},
    "0802": {"recursos": "direcionado", "segmento_default": "pesJuridica",
             "encargo_default": "pre", "modalidade": "crdRurMercado"},
}

# Fallback para Mods não mapeados — cai em outCrdLivres (mensal apenas, modelo_4_M)
DE_PARA_FALLBACK = {
    "recursos": "livre", "segmento_default": "pesJuridica",
    "encargo_default": "pre", "modalidade": "outCrdLivres",
}

# Segmento derivado de Cli/@Tp (Anexo 11 do 3040): 1,3,5 = PF ; 2,4,6 = PJ
SEG_DE_PARA = {
    "1": "pesFisica",  "3": "pesFisica",  "5": "pesFisica",
    "2": "pesJuridica","4": "pesJuridica","6": "pesJuridica",
}

# Encargo derivado de Op/@Indx (Anexo 5 do 3040) — §4 das Instruções:
#   11=Prefixado; 21/22/23=Cambial; 31=CDI/32=Selic (flu); 41=IPCA; 43=IGP-M;
#   51=TR; 52=TJLP; 53=TLP; resto → ind (outros indexadores)
INDX_TO_ENCARGO_LIVRE = {
    "11": "pre",
    "21": "vc", "22": "vc", "23": "vc",
    "31": "flu", "32": "flu",
    "41": "ipca",
    "43": "igpm",
}
INDX_TO_ENCARGO_DIRECIONADO = {
    **INDX_TO_ENCARGO_LIVRE,
    "51": "tr", "52": "tjlp", "53": "tlp",
}

print(f"DE/PARA: {len(DE_PARA_3040_3050)} Mods mapeados + fallback '{DE_PARA_FALLBACK['modalidade']}'.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helpers — datas, conversão m→aa, formatadores TXB

# COMMAND ----------

from datetime import date, timedelta


def derive_encargo(indx: str | None, recursos: str) -> str:
    """Mapeia o indexador do 3040 para encargo 3050 conforme §4 das Instruções."""
    if indx is None:
        return "pre"
    table = INDX_TO_ENCARGO_DIRECIONADO if recursos == "direcionado" else INDX_TO_ENCARGO_LIVRE
    return table.get(indx, "ind")


def last_business_day_of_month(yyyy_mm: str) -> date:
    """Último dia útil do mês (simplificado — em produção usar bcb_calendar)."""
    y, m = int(yyyy_mm[:4]), int(yyyy_mm[5:7])
    if m == 12:
        d = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(y, m + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def dt_base_semanal(d: date) -> date:
    """Data-base semanal = sexta-feira da semana BCB (§5 Instruções)."""
    shift = (d.weekday() - 4) % 7
    return d - timedelta(days=shift)


# Formatadores conforme restrições do XSD TXB V11:
def fmt_valor(v) -> str:
    """valorType = xs:integer (0..999999999999). TXB expressa valores em R$ inteiros."""
    return str(int(round(float(v or 0))))


def fmt_taxa(v) -> str:
    """taxaType = xs:decimal totalDigits=8 fractionDigits=2 (0.00..999999.99)."""
    x = max(0.0, min(999999.99, float(v or 0)))
    return f"{x:.2f}"


def fmt_qtd(v) -> str:
    """qtdType = xs:integer 0..999999999 (prazo em dias)."""
    return str(max(0, int(round(float(v or 0)))))


def fmt_tmp(v) -> str:
    """tmpType = xs:integer 0..99999 (prazo em dias, variante compacta)."""
    return str(max(0, min(99999, int(round(float(v or 0))))))


def fmt_data(d: date) -> str:
    """dbType = YYYY-MM-DD (pattern do XSD)."""
    return d.isoformat()


# Mapa atributo → formatter (usado pelo gerador XML em 03)
ATTR_FORMATTER = {
    "txMedJuros":           fmt_taxa,
    "txMedJurosAjustada":   fmt_taxa,
    "txMedEncFiscais":      fmt_taxa,
    "txMedEncOperacionais": fmt_taxa,
    "vlrConcessoes":        fmt_valor,
    "sldCarAtiva":          fmt_valor,
    "sldCedido":            fmt_valor,
    "sldAdquirido":         fmt_valor,
    "sldBaiPrejuizo":       fmt_valor,
    "sldCarAte14":          fmt_valor,
    "sldCarAte60":          fmt_valor,
    "sldCarAte90":          fmt_valor,
    "sldCarMaior90":        fmt_valor,
    "przDecMedConcessoes":  fmt_qtd,   # diário modelo_1/3 é qtdType; mensal é tmpType (ambos int)
    "przMedCarteira":       fmt_tmp,
}

print("Helpers e formatadores carregados.")

# COMMAND ----------

# Persiste parâmetros para notebooks seguintes (mesmo padrão do 3040).
dbutils.jobs.taskValues.set(key="DT_BASE",        value=DT_BASE)
dbutils.jobs.taskValues.set(key="CNPJ_IF",        value=CNPJ_IF)
dbutils.jobs.taskValues.set(key="CATALOG",        value=CATALOG)
dbutils.jobs.taskValues.set(key="SCHEMA",         value=SCHEMA)
dbutils.jobs.taskValues.set(key="VOLUME_OUT",     value=VOLUME_OUT)
dbutils.jobs.taskValues.set(key="SRC_PREFIX_3040",value=SRC_PREFIX_3040)
dbutils.jobs.taskValues.set(key="LEIAUTE_VERSAO", value=LEIAUTE_VERSAO)

print("Setup concluído. Próximo: 01_Ingestao_Dados_3040.")
