# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Geração e Exportação do XML do Doc 3040
# MAGIC
# MAGIC Converte as tabelas finais produzidas em 02 em um único arquivo XML no
# MAGIC formato esperado pelo **Aplicativo Validador do BACEN** (vide
# MAGIC `docs/scr3040/exemploDocPadraoInfosBasicas.xml` — arquivo de referência).
# MAGIC
# MAGIC Fluxo:
# MAGIC 1. Ler `f_3040_*` (clientes, operações, vencimentos, garantias).
# MAGIC 2. Coletar para o driver em lotes por cliente (hierarquia `<Cli>`→`<Op>`→…).
# MAGIC 3. Construir árvore via `lxml.etree` (encoding UTF-8, sem namespaces).
# MAGIC 4. Escrever em Volume UC (`VOLUME_OUT`) com nome padronizado:
# MAGIC    `Doc3040_{CNPJ_IF}_{DtBase}_R{Remessa}_P{Parte}.xml`.
# MAGIC
# MAGIC > O bloco `<Agreg>` (operações < R$200) é preenchido com uma amostra
# MAGIC > agregada simples — regra de produção deve agregar a partir das próprias
# MAGIC > operações menores (fora do escopo deste MVP sintético).

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Dominios

# COMMAND ----------

from pyspark.sql import functions as F
from lxml import etree
import os

final_prefix = f"{CATALOG}.{SCHEMA}.f_3040_"
df_cli = spark.table(final_prefix + "clientes")
df_ops = spark.table(final_prefix + "operacoes")
df_venc = spark.table(final_prefix + "vencimentos")
df_gar = spark.table(final_prefix + "garantias")

remessa = 1
parte = 1
tp_arq = "F"   # F = Full (arquivo completo); P = Parcial

# COMMAND ----------

# MAGIC %md
# MAGIC ## Materialização hierárquica
# MAGIC Coletamos para o driver: em um cenário de alta cardinalidade (milhões de
# MAGIC clientes), particionar por bloco de clientes e gerar múltiplos arquivos
# MAGIC (atributo `Parte` do `<Doc3040>`). Para volumes de dev/demo, um único
# MAGIC arquivo é suficiente.

# COMMAND ----------

# Ordem determinística para reprodutibilidade
clis = df_cli.orderBy("cli_cd").collect()
ops  = df_ops.orderBy("cli_cd", "op_id").collect()
vens = {r["op_id"]: r for r in df_venc.collect()}
gars_by_op: dict[str, list] = {}
for g in df_gar.collect():
    gars_by_op.setdefault(g["op_id"], []).append(g)

# Índice operações por cliente
ops_by_cli: dict[str, list] = {}
for op in ops:
    ops_by_cli.setdefault(op["cli_cd"], []).append(op)

total_cli = len(clis)
print(f"Preparando XML: {total_cli} clientes, {len(ops)} operações, {len(vens)} venc, "
      f"{sum(len(v) for v in gars_by_op.values())} garantias.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Construção do XML (lxml)
# MAGIC `SubElement` preserva a ordem de inserção, essencial para passar na
# MAGIC validação estrutural do XSD `SCR3045.xsd` / `SCR3040`.

# COMMAND ----------

def _set_attr(el, key, val, *, formatter=str):
    """Adiciona atributo só quando o valor não for None — atributos ausentes são opcionais no leiaute."""
    if val is None or (isinstance(val, float) and val != val):   # NaN-safe
        return
    el.set(key, formatter(val))


def _fmt_date(d) -> str:
    return d.isoformat() if d else ""


def _fmt_money(v) -> str:
    return f"{float(v):.2f}"


def _fmt_int(v) -> str:
    return str(int(v))


# Root <Doc3040>
root = etree.Element("Doc3040")
_set_attr(root, "DtBase", DT_BASE)
_set_attr(root, "CNPJ", CNPJ_IF)
_set_attr(root, "Remessa", remessa, formatter=_fmt_int)
_set_attr(root, "Parte", parte, formatter=_fmt_int)
_set_attr(root, "TpArq", tp_arq)
_set_attr(root, "NomeResp", RESP["NomeResp"])
_set_attr(root, "EmailResp", RESP["EmailResp"])
_set_attr(root, "TelResp", RESP["TelResp"])
_set_attr(root, "TotalCli", total_cli, formatter=_fmt_int)
# C69: MetodApPE + MetodDifTJE obrigatórios quando TpFundo = vazio (não é fundo)
_set_attr(root, "MetodApPE", "C")      # C = Conglomerado (ou S = Individual)
_set_attr(root, "MetodDifTJE", "N")    # N = Não aplica diferenciação

for cli in clis:
    cli_el = etree.SubElement(root, "Cli")
    # Atributos conforme XSD 202601 (tipoCliente). ClassCli foi REMOVIDO em 2026.
    _set_attr(cli_el, "Tp",           cli["tp"])
    _set_attr(cli_el, "Cd",           cli["cli_cd"])
    _set_attr(cli_el, "Autorzc",      cli["autorzc"])
    _set_attr(cli_el, "PorteCli",     cli["porte_cli"])
    _set_attr(cli_el, "TpCtrl",       cli["tp_ctrl"])
    _set_attr(cli_el, "IniRelactCli", cli["ini_relact_cli"], formatter=_fmt_date)
    # CongEcon: Instruções dizem "Caso o cliente não pertença a conglomerado algum,
    # o campo não deve ser informado." — omitimos no MVP sintético.
    _set_attr(cli_el, "FatAnual",     cli["fat_anual"], formatter=_fmt_money)  # C31

    for op in ops_by_cli.get(cli["cli_cd"], []):
        op_el = etree.SubElement(cli_el, "Op")
        # Atributos conforme XSD 202601 (tipoOperacao). ClassOp e Cosif foram REMOVIDOS em 2026.
        _set_attr(op_el, "DetCli",        op["det_cli"])
        _set_attr(op_el, "Contrt",        op["contrt"])
        _set_attr(op_el, "NatuOp",        op["natu_op"])
        _set_attr(op_el, "Mod",           op["mod"])
        _set_attr(op_el, "OrigemRec",     op["origem_rec"])
        _set_attr(op_el, "Indx",          op["indx"])
        _set_attr(op_el, "PercIndx",      op["perc_indx"], formatter=_fmt_money)  # C32
        _set_attr(op_el, "VarCamb",       op["var_camb"])
        _set_attr(op_el, "DtVencOp",      op["dt_venc_op"], formatter=_fmt_date)
        _set_attr(op_el, "CEP",           op["cep"])
        _set_attr(op_el, "TaxEft",        op["tax_eft"], formatter=_fmt_money)
        _set_attr(op_el, "DtContr",       op["dt_contr"], formatter=_fmt_date)
        _set_attr(op_el, "ProvConsttd",   op["prov_consttd"], formatter=_fmt_money)
        _set_attr(op_el, "CaracEspecial", op["carac_especial"])
        _set_attr(op_el, "DiaAtraso",     0, formatter=_fmt_int)                 # S28
        _set_attr(op_el, "IPOC",          op["ipoc"])

        # <Venc> — apenas buckets com valor > 0
        venc = vens.get(op["op_id"])
        if venc is not None:
            venc_el = etree.SubElement(op_el, "Venc")
            for bucket in VENC_BUCKETS:
                val = venc[bucket]
                if val and val > 0:
                    _set_attr(venc_el, bucket, val, formatter=_fmt_money)

        # <Gar> — 0..N elementos
        for g in gars_by_op.get(op["op_id"], []):
            g_el = etree.SubElement(op_el, "Gar")
            _set_attr(g_el, "Tp",      g["tp"])
            _set_attr(g_el, "Ident",   g["ident"])
            _set_attr(g_el, "PercGar", g["perc_gar"], formatter=_fmt_money)
            _set_attr(g_el, "VlrOrig", g["vlr_orig"], formatter=_fmt_money)
            _set_attr(g_el, "VlrData", g["vlr_data"], formatter=_fmt_money)
            _set_attr(g_el, "DtReav",  g["dt_reav"],  formatter=_fmt_date)

        # <ContInstFinRes4966> — C70/C74/C79/C85 exigem ClasAtFin, CartProvMin,
        # VlrContBr, RendMes para Mod 1-14/18 + Natu 1,2,3,11,13,14,15,32 quando
        # TpFundo=vazio. MVP preenche com valores coerentes.
        cif_el = etree.SubElement(op_el, "ContInstFinRes4966")
        # <Estagio> filho é obrigatório quando EstInstFin está preenchido (regra C83).
        # Motivo: pattern 1(01|02|03)|2(01|02)|3(01-11). 101 = alocação inicial em Estágio 1.
        # DtAlocacao: formato YYYY-MM (tipoDataMesAnoDataAlocacao).
        etree.SubElement(cif_el, "Estagio", Motivo="101", DtAlocacao=DT_BASE)
        _set_attr(cif_el, "ClasAtFin",   1)                                    # C70
        _set_attr(cif_el, "EstInstFin",  1)                                    # C71 (MetodApPE=C)
        _set_attr(cif_el, "CartProvMin", "C1")                                 # C74
        _set_attr(cif_el, "VlrContBr",   op["vlr_op"], formatter=_fmt_money)   # C79
        _set_attr(cif_el, "TJE",         op["tax_eft"], formatter=_fmt_money)  # C73 (MetodDifTJE=N)
        _set_attr(cif_el, "RendMes",     0.0,          formatter=_fmt_money)   # C85

# <Agreg> é minOccurs=0 no XSD — omitido no MVP (produção deve agregar operações
# com responsabilidade < R$200 respeitando tipoOrigemRecAgreg=0100|0200 e
# atributos válidos do layout 202601).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validação rápida e serialização

# COMMAND ----------

xml_bytes = etree.tostring(
    root,
    pretty_print=True,
    xml_declaration=True,
    encoding="UTF-8",
)

# Sanity checks mínimos antes de gravar — reprodução das críticas mais comuns
assert root.get("CNPJ") and len(root.get("CNPJ")) == 8, "CNPJ da IF deve ter 8 dígitos"
assert root.get("TotalCli") and int(root.get("TotalCli")) == total_cli, "TotalCli divergente"
n_cli_xml = len(root.findall("Cli"))
assert n_cli_xml == total_cli, f"Contagem de <Cli> no XML ({n_cli_xml}) ≠ TotalCli ({total_cli})"
print(f"XML gerado: {len(xml_bytes)/1024:.1f} KB, {n_cli_xml} clientes, "
      f"{len(root.findall('.//Op'))} operações.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Escrita no Volume (UC)
# MAGIC Padrão do validador: um arquivo por remessa/parte.

# COMMAND ----------

os.makedirs(VOLUME_OUT, exist_ok=True)
fname = f"Doc3040_{CNPJ_IF}_{DT_BASE}_R{remessa}_P{parte}.xml"
fpath = os.path.join(VOLUME_OUT, fname)

with open(fpath, "wb") as f:
    f.write(xml_bytes)

size_kb = os.path.getsize(fpath) / 1024
print(f"Arquivo gravado: {fpath} ({size_kb:.1f} KB)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview dos primeiros 2 KB (inspeção visual)

# COMMAND ----------

print(xml_bytes[:2048].decode("utf-8"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Próximos passos
# MAGIC 1. Submeter `Doc3040_*.xml` ao **Aplicativo Validador do BACEN**
# MAGIC    (`docs/scr3040/SCR3040_Validador.zip`) para confirmar conformidade
# MAGIC    sintática e de críticas.
# MAGIC 2. Ingerir o XML via pipeline Bronze (`pipelines/bronze/transformations/raw_3040.py`)
# MAGIC    para fechar o ciclo end-to-end.
# MAGIC 3. Iterar sobre críticas reprovadas (planilha `SCR3040_Criticas.xls`)
# MAGIC    ajustando as regras no notebook 02.
