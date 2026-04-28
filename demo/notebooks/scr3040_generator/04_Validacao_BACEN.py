# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Validação com o Aplicativo Validador do BACEN
# MAGIC
# MAGIC Submete o XML gerado em 03 ao **Validador Oficial do BACEN** (SCR3040).
# MAGIC
# MAGIC ## Adaptações para rodar em job Databricks
# MAGIC 1. **Compute classic (não serverless):** o validador é uma aplicação Java
# MAGIC    e exige `java` no PATH do driver. Serverless (Python Connect) não expõe
# MAGIC    a JVM do lado do cliente — por isso esta task roda em `job_cluster`.
# MAGIC 2. **Binário em Volume UC:** o ZIP oficial (`SCR3040_Validador.zip`) está
# MAGIC    hospedado em `/Volumes/rc18_demo/ferramentas/validador/` (pré-carregado)
# MAGIC    por exceder o limite de 10 MB de Workspace Files.
# MAGIC 3. **Extração em `/tmp`:** o conteúdo do ZIP é extraído em `/tmp/validador`
# MAGIC    (não-persistente, efêmero por run).
# MAGIC 4. **Modo CLI:** invocamos `br.gov.bcb.scr2.validador.linhacomando.ValidadorIfLinhaComando`
# MAGIC    — mesma entrypoint do `validador_linha_comando.bat` (Windows), traduzida
# MAGIC    para shell POSIX.
# MAGIC 5. **Relatório:** o validador cria arquivos de log no diretório do XML.
# MAGIC    Copiamos tudo para `<volume_out>/validacao/<timestamp>/` para auditoria.

# COMMAND ----------

dbutils.widgets.text("dt_base",     "2026-03", "Data-base (YYYY-MM)")
dbutils.widgets.text("cnpj_if",     "99999999", "CNPJ-base da IF")
dbutils.widgets.text("volume_out",  "/Workspace/Users/<user>@databricks.com/SCR_Doc3040_Generator/output",
                     "Dir. do XML gerado em 03 (substitua <user>)")
dbutils.widgets.text("validador_zip",
                     "/Volumes/rc18_demo/ferramentas/validador/SCR3040_Validador.zip",
                     "Caminho do ZIP do validador")
dbutils.widgets.text("fail_on_error", "true", "Falhar task se validador reportar erro")

DT_BASE        = dbutils.widgets.get("dt_base")
CNPJ_IF        = dbutils.widgets.get("cnpj_if")
VOLUME_OUT     = dbutils.widgets.get("volume_out")
VALIDADOR_ZIP  = dbutils.widgets.get("validador_zip")
FAIL_ON_ERROR  = dbutils.widgets.get("fail_on_error").lower() == "true"

XML_NAME = f"Doc3040_{CNPJ_IF}_{DT_BASE}_R1_P1.xml"
XML_PATH = f"{VOLUME_OUT}/{XML_NAME}"

print(f"XML a validar: {XML_PATH}")
print(f"Binário:        {VALIDADOR_ZIP}")

# COMMAND ----------

import os, shutil, subprocess, zipfile, datetime, glob

# Sanity: XML precisa existir
assert os.path.exists(XML_PATH), f"XML não encontrado: {XML_PATH} (rode a task 03 antes)"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preparação do validador em `/tmp`

# COMMAND ----------

VAL_DIR = "/tmp/validador"
if os.path.exists(VAL_DIR):
    shutil.rmtree(VAL_DIR)
os.makedirs(VAL_DIR, exist_ok=True)

# Copia ZIP do Volume UC (leitura via FUSE) para /tmp
local_zip = "/tmp/SCR3040_Validador.zip"
shutil.copyfile(VALIDADOR_ZIP, local_zip)
print(f"ZIP copiado: {os.path.getsize(local_zip)/1024/1024:.1f} MB")

with zipfile.ZipFile(local_zip, "r") as zf:
    zf.extractall(VAL_DIR)

# Verificação: o jar principal e a pasta classes devem existir
assert os.path.isdir(f"{VAL_DIR}/lib"), "pasta lib/ ausente após unzip"
assert os.path.isdir(f"{VAL_DIR}/classes"), "pasta classes/ ausente após unzip"
print(f"Validador extraído em {VAL_DIR}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verificação do JRE

# COMMAND ----------

java_check = subprocess.run(["java", "-version"], capture_output=True, text=True)
print((java_check.stderr or java_check.stdout).strip())
assert java_check.returncode == 0, "java não disponível no PATH — use job_cluster classic"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Execução do validador (modo CLI)
# MAGIC
# MAGIC Tradução do `bin/run_validador_linha_comando.bat` para POSIX:
# MAGIC
# MAGIC ```bash
# MAGIC java -Xms512m -Xmx1024m \
# MAGIC      -cp "lib/*:classes" \
# MAGIC      br.gov.bcb.scr2.validador.linhacomando.ValidadorIfLinhaComando \
# MAGIC      <xml_path> no_warn
# MAGIC ```

# COMMAND ----------

# Copia o XML para /tmp antes de validar — o validador escreve relatórios
# ao lado do arquivo de entrada, e /Workspace pode ser read-only para o processo Java.
local_xml = f"/tmp/{XML_NAME}"
shutil.copyfile(XML_PATH, local_xml)

cmd = [
    "java", "-Xms512m", "-Xmx1024m",
    "-cp", "lib/*:classes",
    "br.gov.bcb.scr2.validador.linhacomando.ValidadorIfLinhaComando",
    local_xml,
    "no_warn",
]
print("Comando:", " ".join(cmd))
print("CWD:    ", VAL_DIR)
print("-" * 72)

proc = subprocess.run(cmd, cwd=VAL_DIR, capture_output=True, text=True, timeout=1800)

print("RC:", proc.returncode)
print("--- STDOUT ---")
print(proc.stdout[-8000:])   # trunca para não estourar o output da task
print("--- STDERR ---")
print(proc.stderr[-4000:])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Coleta de relatórios e publicação

# COMMAND ----------

ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
report_dir = os.path.join(VOLUME_OUT, "validacao", ts)
os.makedirs(report_dir, exist_ok=True)

# Relatórios típicos produzidos pelo validador (HTML/TXT) ficam no dir do XML ou em /tmp/validador
candidatos = (
    glob.glob(f"/tmp/*.html") + glob.glob(f"/tmp/*.txt") + glob.glob(f"/tmp/*.log")
    + glob.glob(f"{VAL_DIR}/*.html") + glob.glob(f"{VAL_DIR}/*.txt") + glob.glob(f"{VAL_DIR}/*.log")
)
copiados = []
for src in candidatos:
    dst = os.path.join(report_dir, os.path.basename(src))
    try:
        shutil.copyfile(src, dst)
        copiados.append(dst)
    except Exception as e:
        print(f"[warn] não copiou {src}: {e}")

# Persiste também stdout/stderr do processo
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
# MAGIC ## Avaliação final

# COMMAND ----------

# Heurísticas conservadoras: considerar reprovado se RC != 0 OU texto indicando erro fatal
saida = (proc.stdout + "\n" + proc.stderr).lower()
sinais_erro = ["erro", "error", "invalid", "critica violada", "falha"]
sinais_ok = ["validação concluída", "arquivo válido", "validated successfully", "sem erros"]

tem_erro = proc.returncode != 0 or any(s in saida for s in sinais_erro) and not any(
    ok in saida for ok in sinais_ok
)

print(f"Resumo: RC={proc.returncode} | reprovado={tem_erro}")

dbutils.jobs.taskValues.set(key="validacao_rc", value=proc.returncode)
dbutils.jobs.taskValues.set(key="validacao_report_dir", value=report_dir)

if tem_erro and FAIL_ON_ERROR:
    raise RuntimeError(
        f"Validador BACEN reprovou o XML. RC={proc.returncode}. "
        f"Relatórios em {report_dir}."
    )
