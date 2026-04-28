# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Setup e Domínios (SCR Doc 3040)
# MAGIC
# MAGIC Configuração global do gerador sintético do Documento 3040 (BACEN/SCR).
# MAGIC Define:
# MAGIC
# MAGIC 1. Parâmetros da remessa (DtBase, CNPJ da IF, responsável, volumes).
# MAGIC 2. Tabelas de domínio dos **Anexos** do leiaute oficial (`SCR3040_Leiaute.xls`).
# MAGIC 3. Funções utilitárias reutilizadas pelos notebooks 01–03:
# MAGIC    - Geração de CPF/CNPJ válidos (módulo 11 — exigido pelo Validador BACEN).
# MAGIC    - Composição do IPOC (chave única da operação).
# MAGIC    - Formatação de datas e numéricos no padrão do leiaute.
# MAGIC
# MAGIC > Referências locais: `docs/scr3040/SCR3040_Leiaute.xls`,
# MAGIC > `docs/scr3040/SCR_InstrucoesDePreenchimento_Doc3040.pdf`,
# MAGIC > `docs/scr3040/exemploDocPadraoInfosBasicas.xml`.

# COMMAND ----------

dbutils.widgets.text("dt_base", "2026-03", "Data-base (YYYY-MM)")
dbutils.widgets.text("cnpj_if", "99999999", "CNPJ-base da IF (8 dígitos)")
dbutils.widgets.text("n_clientes", "500", "Qtd. clientes a gerar")
dbutils.widgets.text("n_ops_por_cli", "3", "Média de operações por cliente")
dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Schema p/ tabelas staging do gerador")
dbutils.widgets.text("volume_out", "/Volumes/rc18_catalog/reference/scr3040_out", "Volume de saída do XML")

DT_BASE = dbutils.widgets.get("dt_base")                # Atributo DtBase do <Doc3040>
CNPJ_IF = dbutils.widgets.get("cnpj_if")                # Atributo CNPJ do <Doc3040>
N_CLIENTES = int(dbutils.widgets.get("n_clientes"))
N_OPS_POR_CLI = int(dbutils.widgets.get("n_ops_por_cli"))
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_OUT = dbutils.widgets.get("volume_out")

# Responsável (atributos NomeResp/EmailResp/TelResp do <Doc3040>)
RESP = {
    "NomeResp":  "Equipe Governança SCR",
    "EmailResp": "scr.governanca@exemplo.com.br",
    "TelResp":   "1133000000",
}

print(f"DtBase={DT_BASE} CNPJ_IF={CNPJ_IF} Clientes={N_CLIENTES} Ops/Cli~{N_OPS_POR_CLI}")
print(f"Destino XML: {VOLUME_OUT}")

# NOTA: faker e lxml são instalados pelo ambiente serverless do job
# (ver resources/jobs_scr3040_generator.yml → environments.dependencies).
# Se rodar manualmente em outro cluster, instalar com:
#   %pip install faker lxml -q
#   dbutils.library.restartPython()
# Mas NUNCA use restartPython dentro deste notebook quando chamado via %run,
# porque reinicia o kernel e apaga todas as variáveis globais (DT_BASE, helpers, domínios).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Domínios oficiais do Doc 3040
# MAGIC Listas extraídas dos Anexos do leiaute. Para um gerador de produção, carregar
# MAGIC diretamente de `rc18_catalog.reference.scr3040_dominios` (populada pelo notebook
# MAGIC `setup_reference_tables.py`). Aqui usamos cópias enxutas para
# MAGIC auto-contenção do gerador.

# COMMAND ----------

# Domínios conforme scr3040.202601.xsd (validador BACEN — Jan/2026).
# Valores foram filtrados contra os patterns/enums do XSD — edições aqui
# exigem re-checagem do schema para não quebrar o <Op>/<Cli>/<Agreg>.

# Anexo 11 — Tipo de Cliente (Cli/@Tp). MVP gera apenas PJ pois Op/@DetCli
# é tipoCNPJ14 obrigatório (14 dígitos) — PF exigiria mapeamento especial.
TP_CLI = {"2": "PJ"}

# Anexo 10 — Tipo de Controle (Cli/@TpCtrl) — pattern 0?[1-4]
TP_CTRL = ["01", "02", "03", "04"]

# Anexo 13 — Porte do Cliente (Cli/@PorteCli) — pattern [0-8],
# mas regra C07 restringe a 0–4 para Tp=2,4,6.
PORTES_PJ = ["0", "1", "2", "3", "4"]

# NOTA: @ClassCli (no <Cli>) e @ClassOp/@Cosif (no <Op>) foram REMOVIDOS no
# layout 202601. Mantemos CLASSES apenas se necessário para outros usos internos,
# mas não vai para o XML.

# Anexo 2 — Natureza da Operação (Op/@NatuOp) — MVP usa apenas "01" (Individual simples)
# para evitar regras S09/S26/S27/S30/S31/S54/S55 que exigem <Inf> específicos.
NATU_OP = ["01"]

# Anexo 3 — Modalidade de Operação (Op/@Mod) — MVP usa apenas "0101" pois é exceção
# na regra C28 (não exige VlrContr) e não dispara S100 (0202), S48 (0401), etc.
MOD_OP = ["0101"]

# Anexo 4 — Origem de Recursos (Op/@OrigemRec) — pattern 0?10[1-2]|0?199|0?20[1-9]|0?21[0-3]|0?299
ORIGEM_REC = ["0101", "0102", "0199", "0201", "0299"]

# Origem de Recursos AGREGADA (Agreg/@OrigemRec) — pattern 0?100|0?200 (diferente do individual)
ORIGEM_REC_AGREG = ["0100", "0200"]

# Anexo 5 — Indexador (Op/@Indx) — enum fechado tipoIndexador
INDX = ["11", "21", "22", "23", "24", "25", "29", "31", "32", "39",
        "41", "42", "43", "49", "51", "52", "53", "54", "91", "99"]
VAR_CAMB = ["790"]                                       # 790 = BRL

# Anexo 8 — Característica Especial (Op/@CaracEspecial) — concatenáveis com ";"
CARAC_ESPECIAL = ["01", "02", "03", "04", "05", "06", "07"]

# Anexo 12 — Tipo/Subtipo de Garantia (Gar/@Tp) — filtrado pelo pattern tipoDeGarantia
# do XSD 202601. 09xx = fidejussória (Ident+PercGar). Demais são reais.
GAR_TIPOS_REAIS = ["0101", "0102", "0201", "0205", "0321", "0424"]
GAR_TIPOS_FIDEJ = ["0901", "0902"]                       # 0901=PF, 0902=PJ

# Anexo 28 — Desempenho da operação (Agreg/@DesempOp)
DESEMP_OP = ["01", "02", "03"]

# Buckets de vencimento A VENCER (tag <Venc>) conforme Instruções de Preenchimento:
#   v110=0-30d, v120=31-60d, v130=61-90d, v140=91-180d, v150=181-360d,
#   v160=361-720d, v165=721-1080d, v170=1081-1440d, v175=1441-1800d,
#   v180=1801-5400d, v190=>5400d, v199=indeterminado.
# NÃO incluímos v2xx/v3xx porque são buckets de ATRASO/PREJUÍZO — exigem
# DiaAtraso > 0 (regra S28) e disparam S103 (demais vértices = 0).
VENC_BUCKETS = ["v110", "v120", "v130", "v140", "v150", "v160", "v165", "v170", "v175", "v180"]

print("Domínios carregados.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helpers — validação fiscal, IPOC, formatação

# COMMAND ----------

import random
from datetime import date, timedelta


def _dv_mod11(digits: str, weights: list[int]) -> int:
    """Dígito verificador módulo 11 (regra BACEN/Receita)."""
    s = sum(int(d) * w for d, w in zip(digits, weights))
    r = s % 11
    return 0 if r < 2 else 11 - r


def gerar_cpf(rng: random.Random | None = None) -> str:
    """Gera CPF com dígitos verificadores válidos (11 dígitos, sem máscara)."""
    rng = rng or random
    base = "".join(str(rng.randint(0, 9)) for _ in range(9))
    d1 = _dv_mod11(base, list(range(10, 1, -1)))
    d2 = _dv_mod11(base + str(d1), list(range(11, 1, -1)))
    return f"{base}{d1}{d2}"


def gerar_cnpj(rng: random.Random | None = None, base8: str | None = None,
               filial: str | None = None) -> str:
    """Gera CNPJ válido. Se `base8` é fornecido, respeita a raiz (útil para DetCli de PJ)."""
    rng = rng or random
    base = base8 if base8 else "".join(str(rng.randint(0, 9)) for _ in range(8))
    fil = filial if filial else f"{rng.randint(1, 9999):04d}"
    partial = base + fil
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _dv_mod11(partial, w1)
    d2 = _dv_mod11(partial + str(d1), w2)
    return f"{partial}{d1}{d2}"


def montar_ipoc(cnpj_if8: str, mod: str, tp_cli: str, cli_cd: str, contrt: str) -> str:
    """IPOC = CNPJ(8) + Mod(4) + TpCli(1) + Cli.Cd(8) + Contrt — vide exemploDocPadraoInfosBasicas.xml."""
    if len(cnpj_if8) != 8 or len(mod) != 4 or len(tp_cli) != 1 or len(cli_cd) != 8:
        raise ValueError("Formatos inválidos p/ IPOC")
    return f"{cnpj_if8}{mod}{tp_cli}{cli_cd}{contrt}"


def fmt_valor(v) -> str:
    """Numérico com vírgula decimal convertida para ponto e 2 casas (padrão atributo XML)."""
    return f"{float(v):.2f}"


def add_dias(d: date, n: int) -> date:
    return d + timedelta(days=n)


# COMMAND ----------

# Persiste parâmetros para notebooks seguintes via dbutils.jobs taskValues
dbutils.jobs.taskValues.set(key="DT_BASE", value=DT_BASE)
dbutils.jobs.taskValues.set(key="CNPJ_IF", value=CNPJ_IF)
dbutils.jobs.taskValues.set(key="N_CLIENTES", value=N_CLIENTES)
dbutils.jobs.taskValues.set(key="N_OPS_POR_CLI", value=N_OPS_POR_CLI)
dbutils.jobs.taskValues.set(key="VOLUME_OUT", value=VOLUME_OUT)

print("Setup concluído. Próximo: 01_Geracao_Dados_Sinteticos.")
