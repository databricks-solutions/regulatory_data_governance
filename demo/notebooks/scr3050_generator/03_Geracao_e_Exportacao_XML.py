# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Geração e Exportação do XML do Doc 3050 (TXB V11)
# MAGIC
# MAGIC Converte os agregados `f_3050_diario` e `f_3050_mensal` (produzidos em 02)
# MAGIC no arquivo XML conforme `Schema_TXB_V11.xsd`.
# MAGIC
# MAGIC ## Estrutura alvo do `<DocTXB>` (XSD real)
# MAGIC ```
# MAGIC <DocTXB cnpjInstituicao="…" dataBase="YYYY-MM-DD"
# MAGIC         indRemessa="I" nmContato="…" telContato="XX-XXXXXXXX">
# MAGIC   <referencia dataRef="YYYY-MM-DD">
# MAGIC     <diario>
# MAGIC       <crdLivre>
# MAGIC         <pesJuridica>
# MAGIC           <pre>
# MAGIC             <capGirPrzAte365 txMedJuros="…" vlrConcessoes="…" … />
# MAGIC             …
# MAGIC           </pre>
# MAGIC           <flu>…</flu>
# MAGIC         </pesJuridica>
# MAGIC         <pesFisica>…</pesFisica>
# MAGIC       </crdLivre>
# MAGIC     </diario>
# MAGIC     <mensal>
# MAGIC       <crdLivre>
# MAGIC         <pesJuridica>…</pesJuridica>
# MAGIC       </crdLivre>
# MAGIC     </mensal>
# MAGIC   </referencia>
# MAGIC </DocTXB>
# MAGIC ```
# MAGIC
# MAGIC ## Pontos-chave (vs versão anterior)
# MAGIC
# MAGIC 1. **Root é `<DocTXB>`** (não `<Doc3050>`), com atributos camelCase.
# MAGIC 2. **Hierarquia em 6 níveis** — `DocTXB → referencia → (diario|mensal) →
# MAGIC    (crdLivre|crdDirecionado) → (pesFisica|pesJuridica) → encargo →
# MAGIC    modalidade`. Cada nó só aparece se houver dados embaixo.
# MAGIC 3. **Diário e Mensal são irmãos**, não aninhados (contrário ao que fiz antes).
# MAGIC 4. **Valores monetários são inteiros** (`valorType = xs:integer` no XSD) —
# MAGIC    R$ sem decimais. Taxas mantêm duas casas decimais.
# MAGIC 5. **Só atributos definidos no modelo** (1-5 diário, 1-7 mensal) são
# MAGIC    emitidos — ordem do XSD preservada.

# COMMAND ----------

# MAGIC %run ./00_Setup_e_Equivalencia

# COMMAND ----------

from pyspark.sql import functions as F
from lxml import etree
import os
from collections import defaultdict

final_prefix = f"{CATALOG}.{SCHEMA}.f_3050_"
df_d = spark.table(final_prefix + "diario")
df_m = spark.table(final_prefix + "mensal")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Coleta dos agregados
# MAGIC Volumes pequenos (poucas dezenas de linhas por recursos×segmento×encargo×modalidade).
# MAGIC Collect ao driver mantém ordem determinística por chave.

# COMMAND ----------

rows_d = df_d.orderBy(
    "recursos_3050", "segmento_3050", "encargo_3050", "modalidade_3050"
).collect()
rows_m = {
    (r["recursos_3050"], r["segmento_3050"], r["encargo_3050"], r["modalidade_3050"]): r
    for r in df_m.collect()
}

assert len(rows_d) > 0, "Agregado diário vazio — verifique o motor de agregação (02)."

# Data de referência (único valor no MVP — produção gera uma <referencia> por semana)
DT_REFERENCIA = rows_d[0]["dt_referencia"]
print(f"XML TXB: {len(rows_d)} linhas diárias, {len(rows_m)} linhas mensais, "
      f"DtRef={DT_REFERENCIA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Índice hierárquico
# MAGIC Organiza as linhas em `{(recursos, segmento): {encargo: {modalidade: row_diaria}}}`
# MAGIC para facilitar a construção aninhada do XML preservando a ordem do XSD.

# COMMAND ----------

# tree_d[(recursos, segmento)][encargo][modalidade] = linha diária
tree_d: dict = defaultdict(lambda: defaultdict(dict))
for r in rows_d:
    tree_d[(r["recursos_3050"], r["segmento_3050"])][r["encargo_3050"]][r["modalidade_3050"]] = r

# Ordem canônica de segmentos, encargos (XSD) — garante output reprodutível
SEG_ORDER = ["pesJuridica", "pesFisica"]
# Ordem de encargos difere entre PJ (inclui vc) e PF no XSD.
# Para simplicidade usamos uma ordem única; o validador aceita ausência mas não
# elementos fora da sequência declarada do XSD. Se houver encargos fora desta
# lista, eles serão apendados no final (e possivelmente reprovarão).
ENC_ORDER_PJ = ["pre", "flu", "vc", "ind", "ipca", "igpm"]
ENC_ORDER_PF = ["pre", "flu", "ind", "ipca", "igpm"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helpers de serialização
# MAGIC Aplicam os formatadores corretos (`ATTR_FORMATTER` definido em 00) e
# MAGIC respeitam required/optional do modelo (definido em `MODELO_ATTRS_*`).

# COMMAND ----------

def _emit_modalidade_diaria(parent, mod_name: str, row, modelo_d: int):
    """Cria <modalidade> em `parent`, populando apenas os atributos do modeloN_D."""
    spec = MODELO_ATTRS_DIARIO.get(modelo_d)
    if spec is None:
        return                     # modalidade só tem mensal (carCrdComVista, outCrdLivres...)
    el = etree.SubElement(parent, mod_name)
    # Emitimos atributos na ordem required + optional (ordem não é rígida p/ atributos XML)
    for attr in spec["required"]:
        val = row[attr] if attr in row.asDict() else 0
        el.set(attr, ATTR_FORMATTER[attr](val))
    for attr in spec["optional"]:
        if attr in row.asDict() and row[attr] is not None:
            v = row[attr]
            # Só emite opcional se > 0 (padrão TXB — evita poluição de atributos zerados)
            if (isinstance(v, (int, float)) and v != 0) or isinstance(v, str):
                el.set(attr, ATTR_FORMATTER[attr](v))


def _emit_modalidade_mensal(parent, mod_name: str, row, modelo_m: int):
    spec = MODELO_ATTRS_MENSAL.get(modelo_m)
    if spec is None:
        return
    el = etree.SubElement(parent, mod_name)
    for attr in spec["required"]:
        val = row[attr] if attr in row.asDict() else 0
        el.set(attr, ATTR_FORMATTER[attr](val))
    for attr in spec["optional"]:
        if attr in row.asDict() and row[attr] is not None:
            v = row[attr]
            if (isinstance(v, (int, float)) and v != 0) or isinstance(v, str):
                el.set(attr, ATTR_FORMATTER[attr](v))


# COMMAND ----------

# MAGIC %md
# MAGIC ## Construção da árvore XML

# COMMAND ----------

# Root <DocTXB> — atributos conforme docTXBType do XSD
root = etree.Element("DocTXB")
root.set("cnpjInstituicao", CNPJ_IF)
# dataBase é dbType = YYYY-MM-DD; usamos o último DU do mês como base contábil
root.set("dataBase", fmt_data(DT_REFERENCIA))
root.set("indRemessa", IND_REMESSA)
root.set("nmContato", CONTATO["nmContato"])
root.set("telContato", CONTATO["telContato"])

# <referencia> — 1 só no MVP (produção: uma por semana no mês)
ref_el = etree.SubElement(root, "referencia")
ref_el.set("dataRef", fmt_data(DT_REFERENCIA))


def _enc_order_for(segmento: str) -> list[str]:
    return ENC_ORDER_PJ if segmento == "pesJuridica" else ENC_ORDER_PF


def _ensure_crd_container(parent_block_el, recursos: str):
    """Retorna (ou cria) <crdLivre>/<crdDirecionado> filho do <diario>/<mensal>."""
    tag = "crdLivre" if recursos == "livre" else "crdDirecionado"
    existing = parent_block_el.find(tag)
    return existing if existing is not None else etree.SubElement(parent_block_el, tag)


def _ensure_segmento_el(crd_el, segmento: str):
    existing = crd_el.find(segmento)
    return existing if existing is not None else etree.SubElement(crd_el, segmento)


def _ensure_encargo_el(seg_el, encargo: str):
    existing = seg_el.find(encargo)
    return existing if existing is not None else etree.SubElement(seg_el, encargo)


# <diario> + <mensal> — criados sob demanda (only if data present).
diario_el = etree.SubElement(ref_el, "diario")
mensal_el = etree.SubElement(ref_el, "mensal")

# Itera em ordem canônica (recursos "livre" antes de "direcionado"; PJ antes de PF;
# encargo conforme ordem do XSD). Mantém o output estável entre runs.
for recursos in ("livre", "direcionado"):
    for segmento in SEG_ORDER:
        sub = tree_d.get((recursos, segmento))
        if not sub:
            continue

        # Encargos presentes no segmento (ordenados pela ordem canônica do XSD,
        # apendando encargos desconhecidos no final — defensivo)
        enc_canonical = _enc_order_for(segmento)
        encargos_presentes = list(sub.keys())
        encargos_ordenados = (
            [e for e in enc_canonical if e in encargos_presentes]
            + [e for e in encargos_presentes if e not in enc_canonical]
        )

        for encargo in encargos_ordenados:
            modalidades = sub[encargo]
            if not modalidades:
                continue

            # ---- Diário ----
            enc_d_el = None
            for mod_name, row_d in modalidades.items():
                modelo_d, _ = MODALIDADE_CATALOGO.get(
                    (recursos, segmento, encargo, mod_name), (None, None)
                )
                if modelo_d is None:
                    continue       # modalidade só aparece em mensal
                if enc_d_el is None:
                    crd_d = _ensure_crd_container(diario_el, recursos)
                    seg_d = _ensure_segmento_el(crd_d, segmento)
                    enc_d_el = _ensure_encargo_el(seg_d, encargo)
                _emit_modalidade_diaria(enc_d_el, mod_name, row_d, modelo_d)

            # ---- Mensal ----
            enc_m_el = None
            for mod_name in modalidades:
                row_m = rows_m.get((recursos, segmento, encargo, mod_name))
                if row_m is None:
                    continue
                _, modelo_m = MODALIDADE_CATALOGO.get(
                    (recursos, segmento, encargo, mod_name), (None, None)
                )
                if modelo_m is None:
                    continue
                if enc_m_el is None:
                    crd_m = _ensure_crd_container(mensal_el, recursos)
                    seg_m = _ensure_segmento_el(crd_m, segmento)
                    enc_m_el = _ensure_encargo_el(seg_m, encargo)
                _emit_modalidade_mensal(enc_m_el, mod_name, row_m, modelo_m)

# Limpeza: remover <diario>/<mensal> vazios (XSD permite ausência mas não nó vazio sem filhos).
for block_el in (diario_el, mensal_el):
    if len(block_el) == 0:
        ref_el.remove(block_el)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Serialização e sanity checks

# COMMAND ----------

xml_bytes = etree.tostring(
    root,
    pretty_print=True,
    xml_declaration=True,
    encoding="UTF-8",
)

# Validações antecipadas (para falhar antes do Validador MDR)
assert root.get("cnpjInstituicao") and len(root.get("cnpjInstituicao")) == 8, (
    "cnpjInstituicao deve ter 8 caracteres (cnpjInstType)"
)
assert root.get("dataBase") and len(root.get("dataBase")) == 10, "dataBase YYYY-MM-DD"
assert root.get("indRemessa") in ("I", "A"), "indRemessa ∈ {I,A}"
assert root.findall("referencia"), "DocTXB exige ≥1 <referencia>"

# Conta folhas (modalidades) sob diario/mensal. lxml.ElementPath não suporta
# predicates como [not(*)], então iteramos em Python.
def _count_leaves(el):
    return 1 if len(el) == 0 else sum(_count_leaves(c) for c in el)

d_blocks = root.findall(".//referencia/diario")
m_blocks = root.findall(".//referencia/mensal")
n_mod_d = sum(_count_leaves(b) for b in d_blocks)
n_mod_m = sum(_count_leaves(b) for b in m_blocks)
print(f"XML gerado: {len(xml_bytes)/1024:.1f} KB | "
      f"{n_mod_d} modalidades diárias | {n_mod_m} modalidades mensais")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Escrita no Volume (UC)

# COMMAND ----------

os.makedirs(VOLUME_OUT, exist_ok=True)
remessa, parte = 1, 1
fname = f"Doc3050_{CNPJ_IF}_{DT_BASE}_R{remessa}_P{parte}.xml"
fpath = os.path.join(VOLUME_OUT, fname)

with open(fpath, "wb") as f:
    f.write(xml_bytes)

print(f"Arquivo gravado: {fpath} ({os.path.getsize(fpath)/1024:.1f} KB)")
dbutils.jobs.taskValues.set(key="XML_PATH", value=fpath)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview (primeiros 3 KB)

# COMMAND ----------

print(xml_bytes[:3072].decode("utf-8"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Próximos passos
# MAGIC 1. Submeter ao **Validador MDR** (notebook 04) com o XSD
# MAGIC    `Schema_TXB_V11.xsd` (pré-carregado em `/Volumes/rc18_demo/ferramentas/validador/xsd/`).
# MAGIC 2. Iterar sobre críticas reprovadas (`docs/scr3050/Criticas_TXB_V11.xlsx`)
# MAGIC    ajustando regras no motor de agregação (02) ou no catálogo de
# MAGIC    modalidades/DE-PARA (00).
