# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Validação automatizada com o Validador MDR do BACEN (Doc 3050)
# MAGIC
# MAGIC Submete o XML 3050 gerado em 03 ao **Validador MDR** (Módulo de Dados
# MAGIC Regulares) do BCB — aplicação Java genérica que valida múltiplos documentos
# MAGIC BACEN (3020, 3040, 3050 etc.) contra o XSD informado.
# MAGIC
# MAGIC ## Diferenças do validador usado no 3040
# MAGIC | Item           | 3040 (SCR Validador)                             | 3050 (MDR Validador)                          |
# MAGIC |----------------|--------------------------------------------------|------------------------------------------------|
# MAGIC | Main class     | `br.gov.bcb.scr2.validador.linhacomando.ValidadorIfLinhaComando` | `br.gov.bcb.mdr.validador.entrada.linhacomando.ValidadorLinhaComando` |
# MAGIC | Layout do ZIP  | Plano (`lib/`, `classes/`)                        | Aninhado (`ValidadorMDR/lib/`, `ValidadorMDR/ValidadorMdr.exe`) |
# MAGIC | Fornece XSD?   | Sim (embutido em `classes/`)                     | **Não** (XSD precisa ser passado como arg)    |
# MAGIC
# MAGIC ## Estratégia (mesmo princípio do 3040)
# MAGIC 1. **Compute classic (não serverless):** serverless não expõe JVM no driver
# MAGIC    — esta task roda num `job_cluster` classic.
# MAGIC 2. **Binário em Volume UC:** ZIP em
# MAGIC    `/Volumes/rc18_demo/ferramentas/validador/SCR3050_Validador.zip`.
# MAGIC 3. **Extração efêmera em `/tmp/validador_mdr`** (cleaned per run).
# MAGIC 4. **CLI:** `java -cp "ValidadorMDR/lib/*" <main-class> <xml> <xsd>`.
# MAGIC 5. **Relatórios:** stdout/stderr copiados para `<volume_out>/validacao/<timestamp>/`.

# COMMAND ----------

dbutils.widgets.text("dt_base",       "2026-03", "Data-base (YYYY-MM)")
dbutils.widgets.text("cnpj_if",       "99999999", "CNPJ-base da IF")
dbutils.widgets.text("volume_out",    "/Volumes/rc18_catalog/reference/scr3050_out",
                     "Dir. do XML gerado em 03")
dbutils.widgets.text("validador_zip",
                     "/Volumes/rc18_demo/ferramentas/validador/SCR3050_Validador.zip",
                     "Caminho do ZIP do validador MDR")
dbutils.widgets.text("validador_main_class",
                     "br.gov.bcb.mdr.validador.entrada.linhacomando.ValidadorLinhaComando",
                     "Entry point Java CLI do ValidadorMDR")
dbutils.widgets.text("xsd_path",
                     "/Volumes/rc18_demo/ferramentas/validador/xsd/Schema_TXB_V11.xsd",
                     "XSD do Doc 3050/TXB V11 (pré-carregado separadamente — não vem no ZIP do validador)")
dbutils.widgets.text("fail_on_error", "true", "Falhar task se validador reportar erro")

DT_BASE       = dbutils.widgets.get("dt_base")
CNPJ_IF       = dbutils.widgets.get("cnpj_if")
VOLUME_OUT    = dbutils.widgets.get("volume_out")
VALIDADOR_ZIP = dbutils.widgets.get("validador_zip")
MAIN_CLASS    = dbutils.widgets.get("validador_main_class")
XSD_PATH      = dbutils.widgets.get("xsd_path")
FAIL_ON_ERROR = dbutils.widgets.get("fail_on_error").lower() == "true"

# O notebook 03 publica XML_PATH via taskValues. Se ausente (execução manual),
# reconstruímos o caminho conforme a convenção `Doc3050_{CNPJ}_{DtBase}_R1_P1.xml`.
XML_PATH = dbutils.jobs.taskValues.get(
    taskKey="geracao_e_exportacao_xml",
    key="XML_PATH",
    default=f"{VOLUME_OUT}/Doc3050_{CNPJ_IF}_{DT_BASE}_R1_P1.xml",
)
XML_NAME = XML_PATH.rsplit("/", 1)[-1]

print(f"XML a validar: {XML_PATH}")
print(f"Binário:        {VALIDADOR_ZIP}")
print(f"Main class:     {MAIN_CLASS}")
print(f"XSD:            {XSD_PATH}")

# COMMAND ----------

import os, shutil, subprocess, zipfile, datetime, glob

assert os.path.exists(XML_PATH), f"XML não encontrado: {XML_PATH} (rode a task 03 antes)"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preparação do validador em `/tmp`

# COMMAND ----------

VAL_DIR = "/tmp/validador_mdr"
if os.path.exists(VAL_DIR):
    shutil.rmtree(VAL_DIR)
os.makedirs(VAL_DIR, exist_ok=True)

local_zip = "/tmp/SCR3050_Validador.zip"
shutil.copyfile(VALIDADOR_ZIP, local_zip)
print(f"ZIP copiado: {os.path.getsize(local_zip)/1024/1024:.1f} MB")

with zipfile.ZipFile(local_zip, "r") as zf:
    zf.extractall(VAL_DIR)

# Layout esperado: <VAL_DIR>/ValidadorMDR/lib/ValidadorMdr.jar + xercesImpl/xml-apis etc.
MDR_ROOT = os.path.join(VAL_DIR, "ValidadorMDR")
assert os.path.isdir(os.path.join(MDR_ROOT, "lib")), (
    f"Pasta ValidadorMDR/lib ausente após unzip em {VAL_DIR}. "
    "Se o ZIP tiver layout diferente, ajuste MDR_ROOT."
)
print(f"Validador MDR extraído em {MDR_ROOT}")
for entry in sorted(os.listdir(MDR_ROOT))[:20]:
    print("  -", entry)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verificação do JRE

# COMMAND ----------

java_check = subprocess.run(["java", "-version"], capture_output=True, text=True)
print((java_check.stderr or java_check.stdout).strip())
assert java_check.returncode == 0, (
    "java não disponível no PATH — esta task precisa de job_cluster classic (não serverless)."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Execução do validador MDR (modo CLI)
# MAGIC
# MAGIC Chamamos o CLI do MDR via JVM. O `ValidadorLinhaComando` do MDR aceita
# MAGIC o XML como argumento e, conforme o modo, referencia o XSD (passado por
# MAGIC variáveis de propriedade via `-D` ou como segundo argumento — ver
# MAGIC `propriedades/metadados.properties` dentro do JAR).
# MAGIC
# MAGIC ```bash
# MAGIC java -Xms512m -Xmx1024m \
# MAGIC      -cp "lib/*" \
# MAGIC      br.gov.bcb.mdr.validador.entrada.linhacomando.ValidadorLinhaComando \
# MAGIC      <xml_path> <xsd_path>
# MAGIC ```

# COMMAND ----------

# Copia o XML p/ /tmp — validador grava logs ao lado do input e /Volumes pode
# ser read-only para o processo Java.
local_xml = f"/tmp/{XML_NAME}"
shutil.copyfile(XML_PATH, local_xml)

# Copia o XSD p/ /tmp pelo mesmo motivo. Se XSD_PATH não existir, deixamos o
# validador rodar sem XSD (ele reporta erro — útil pra diagnosticar configuração).
local_xsd = None
if XSD_PATH and os.path.exists(XSD_PATH):
    local_xsd = f"/tmp/{os.path.basename(XSD_PATH)}"
    shutil.copyfile(XSD_PATH, local_xsd)
    print(f"XSD copiado: {local_xsd}")
else:
    print(f"[WARN] XSD não encontrado em {XSD_PATH} — validação prosseguirá sem schema explícito.")

# ValidadorLinhaComando do MDR exige 3 parâmetros (confirmado via exceção
# "Quantidade de parâmetros necessários: 3" + "É obrigatória a informação de
# um diretório válido para geração do arquivo pós validação"):
# args = [xml_path, xsd_path, output_dir].
local_output_dir = "/tmp/validador_mdr_out"
os.makedirs(local_output_dir, exist_ok=True)

cmd = [
    "java", "-Xms512m", "-Xmx1024m",
    "-cp", "lib/*",
    MAIN_CLASS,
    local_xml,
    local_xsd or "",
    local_output_dir,
]

print("Comando:", " ".join(cmd))
print("CWD:    ", MDR_ROOT)
print("-" * 72)

proc = subprocess.run(cmd, cwd=MDR_ROOT, capture_output=True, text=True, timeout=1800)

print("RC:", proc.returncode)
print("--- STDOUT ---")
print(proc.stdout[-8000:])
print("--- STDERR ---")
print(proc.stderr[-4000:])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Coleta de relatórios e publicação

# COMMAND ----------

ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
report_dir = os.path.join(VOLUME_OUT, "validacao", ts)
os.makedirs(report_dir, exist_ok=True)

candidatos = (
    glob.glob("/tmp/*.html")          + glob.glob("/tmp/*.txt")          + glob.glob("/tmp/*.log")
    + glob.glob(f"{MDR_ROOT}/*.html") + glob.glob(f"{MDR_ROOT}/*.txt")   + glob.glob(f"{MDR_ROOT}/*.log")
    + glob.glob(f"{local_output_dir}/*")
)
copiados = []
for src in candidatos:
    dst = os.path.join(report_dir, os.path.basename(src))
    try:
        shutil.copyfile(src, dst)
        copiados.append(dst)
    except Exception as e:
        print(f"[warn] não copiou {src}: {e}")

# Persiste stdout/stderr/exit code para auditoria
with open(os.path.join(report_dir, "stdout.log"), "w") as f:
    f.write(proc.stdout)
with open(os.path.join(report_dir, "stderr.log"), "w") as f:
    f.write(proc.stderr)
with open(os.path.join(report_dir, "exit_code.txt"), "w") as f:
    f.write(str(proc.returncode))

print(f"Relatórios em: {report_dir}")
for c in copiados:
    print(" -", c)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Avaliação final — classificação Sucesso / Reprovado

# COMMAND ----------

saida = (proc.stdout + "\n" + proc.stderr).lower()
sinais_erro = ["erro", "error", "invalid", "critica violada", "falha", "exception"]
sinais_ok   = ["validação concluída", "arquivo válido", "validated successfully",
               "sem erros", "sucesso"]

# Regra de classificação (mesma lógica do 3040 — tolerante a saídas sem código de retorno):
tem_erro = proc.returncode != 0 or (
    any(s in saida for s in sinais_erro) and not any(ok in saida for ok in sinais_ok)
)

status = "REPROVADO" if tem_erro else "SUCESSO"
print("=" * 72)
print(f"Resumo:  RC={proc.returncode} | status={status}")
print(f"Relatórios: {report_dir}")
print("=" * 72)

dbutils.jobs.taskValues.set(key="validacao_rc",         value=proc.returncode)
dbutils.jobs.taskValues.set(key="validacao_status",     value=status)
dbutils.jobs.taskValues.set(key="validacao_report_dir", value=report_dir)

if tem_erro and FAIL_ON_ERROR:
    raise RuntimeError(
        f"Validador TXB reprovou o XML do Doc 3050. RC={proc.returncode}. "
        f"Relatórios em {report_dir}."
    )
