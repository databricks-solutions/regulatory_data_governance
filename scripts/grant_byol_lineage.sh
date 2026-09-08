#!/usr/bin/env bash
# Concede ao service principal do app RC18 os privilégios necessários para
# GRAVAR metadados e relacionamentos de linhagem externa (BYOL).
#
# Por que existe: a página Linhagem do app é read/write sobre as APIs
# external-metadata / external-lineage do Unity Catalog. As escritas rodam como
# o SP do app, que precisa de CREATE EXTERNAL METADATA no metastore — privilégio
# que nenhum job do bundle concede, porque exige ser admin do metastore.
#
# Sintoma sem estes grants: criar objeto externo ou relacionamento pela UI do app
# retorna 403 com "User does not have CREATE EXTERNAL METADATA on Metastore".
#
# Idempotente: GRANT é idempotente e o script pode ser reexecutado à vontade.
#
# Uso:
#   ./scripts/grant_byol_lineage.sh                    # perfil e app padrão
#   ./scripts/grant_byol_lineage.sh -p aws -t dev
#
# Requisitos: Databricks CLI autenticado com uma identidade que seja
# **admin do metastore** (o SP do app não pode conceder isso a si mesmo).

set -euo pipefail

PROFILE="aws"
TARGET="dev"
CATALOG="rc18_catalog"
APP_NAME=""

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile)  PROFILE="$2"; shift 2 ;;
    -t|--target)   TARGET="$2"; shift 2 ;;
    -c|--catalog)  CATALOG="$2"; shift 2 ;;
    -a|--app)      APP_NAME="$2"; shift 2 ;;
    -h|--help)     usage 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

: "${APP_NAME:=rc18-starter-kit-${TARGET}}"

command -v databricks >/dev/null || { echo "ERRO: Databricks CLI não encontrado." >&2; exit 1; }
command -v python3    >/dev/null || { echo "ERRO: python3 não encontrado." >&2; exit 1; }

echo "==> Perfil: ${PROFILE} | target: ${TARGET} | catálogo: ${CATALOG}"

# ---------------------------------------------------------------------------
# 1. Descobre o SP do app.
#
# IMPORTANTE: o GRANT exige o `service_principal_client_id` (UUID). O
# `service_principal_name` (ex.: "app-2i923x rc18-starter-kit-dev") é rejeitado
# com PRINCIPAL_DOES_NOT_EXIST, apesar de ser o campo que aparece na UI e o
# que a documentação sugere copiar.
# ---------------------------------------------------------------------------
APPS_JSON="$(databricks apps list -p "$PROFILE" --output json 2>/dev/null)"

read -r APP_SP APP_SP_LABEL <<<"$(printf '%s' "$APPS_JSON" | python3 -c '
import json, sys
want = sys.argv[1]
apps = json.load(sys.stdin)

def emit(a):
    # client_id é o identificador aceito pelo GRANT; o name serve só para log.
    cid = a.get("service_principal_client_id") or ""
    if cid:
        print(cid, a.get("service_principal_name") or a.get("name") or "")
    sys.exit()

for a in apps:
    if a.get("name") == want:
        emit(a)
# Fallback: único app do bundle RC18 (ignora a DQX Studio).
cands = [a for a in apps
         if "dqx" not in (a.get("name") or "")
         and (a.get("service_principal_client_id") or "")]
if len(cands) == 1:
    emit(cands[0])
' "$APP_NAME")"

if [[ -z "${APP_SP:-}" ]]; then
  echo "ERRO: não foi possível resolver o service principal do app '${APP_NAME}'." >&2
  echo "Apps disponíveis neste workspace:" >&2
  printf '%s' "$APPS_JSON" | python3 -c '
import json, sys
for a in json.load(sys.stdin):
    print("  -", a.get("name"), "| client_id:", a.get("service_principal_client_id"))
' >&2
  echo "Informe explicitamente com: --app <nome-do-app>" >&2
  exit 1
fi

echo "==> App: ${APP_NAME}"
echo "==> Service principal: ${APP_SP}  (${APP_SP_LABEL})"

# ---------------------------------------------------------------------------
# 2. Warehouse para executar o SQL.
# ---------------------------------------------------------------------------
WH_ID="$(databricks warehouses list -p "$PROFILE" --output json 2>/dev/null | python3 -c '
import json, sys
whs = json.load(sys.stdin)
# Prefere um warehouse já rodando; senão o primeiro disponível.
running = [w for w in whs if w.get("state") == "RUNNING"]
pick = (running or whs)
print(pick[0]["id"] if pick else "")
')"

[[ -n "$WH_ID" ]] || { echo "ERRO: nenhum SQL warehouse disponível." >&2; exit 1; }
echo "==> Warehouse: ${WH_ID}"

# ---------------------------------------------------------------------------
# 3. Os grants.
#
# CREATE EXTERNAL METADATA é privilégio de METASTORE (não tem FQN).
# MODIFY nos schemas é necessário para relacionamentos UPSTREAM (fonte externa
# → tabela UC); SELECT, que o SP já tem, cobre os DOWNSTREAM.
# ---------------------------------------------------------------------------
STATEMENTS=(
  "GRANT CREATE EXTERNAL METADATA ON METASTORE TO \`${APP_SP}\`"
  "GRANT USE CATALOG ON CATALOG ${CATALOG} TO \`${APP_SP}\`"
  "GRANT USE SCHEMA ON SCHEMA ${CATALOG}.bronze TO \`${APP_SP}\`"
  "GRANT MODIFY ON SCHEMA ${CATALOG}.bronze TO \`${APP_SP}\`"
  "GRANT USE SCHEMA ON SCHEMA ${CATALOG}.gold TO \`${APP_SP}\`"
  "GRANT MODIFY ON SCHEMA ${CATALOG}.gold TO \`${APP_SP}\`"
)

echo "==> Aplicando ${#STATEMENTS[@]} grants..."
FAILED=0
for s in "${STATEMENTS[@]}"; do
  OUT="$(databricks api post /api/2.0/sql/statements \
          --profile "$PROFILE" \
          --json "$(python3 -c '
import json, sys
print(json.dumps({"statement": sys.argv[1], "warehouse_id": sys.argv[2], "wait_timeout": "50s"}))
' "$s" "$WH_ID")" 2>&1)" || true

  STATE="$(printf '%s' "$OUT" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("status", {}).get("state", "UNKNOWN"))
except Exception:
    print("PARSE_ERROR")
' 2>/dev/null)"

  if [[ "$STATE" == "SUCCEEDED" ]]; then
    echo "    OK   ${s}"
  else
    FAILED=$((FAILED + 1))
    echo "    FALHOU (${STATE}) ${s}"
    printf '%s' "$OUT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    msg = d.get("status", {}).get("error", {}).get("message") or d.get("message", "")
    print("         ", msg[:300])
except Exception:
    pass
' 2>/dev/null
  fi
done

# ---------------------------------------------------------------------------
# 4. Verificação — confirma pela API, não pela saída dos GRANTs.
# ---------------------------------------------------------------------------
echo "==> Verificando privilégios no metastore..."
METASTORE_ID="$(databricks metastores current -p "$PROFILE" --output json 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["metastore_id"])')"

databricks grants get METASTORE "$METASTORE_ID" -p "$PROFILE" --output json 2>/dev/null \
  | python3 -c '
import json, sys
sp = sys.argv[1]
d = json.load(sys.stdin)
for pa in d.get("privilege_assignments", []):
    if pa.get("principal") == sp:
        privs = pa.get("privileges", [])
        ok = "CREATE_EXTERNAL_METADATA" in privs
        print(f"    privilégios: {privs}")
        print("    CREATE EXTERNAL METADATA:", "OK" if ok else "AUSENTE")
        sys.exit(0 if ok else 1)
print(f"    {sp}: nenhum privilégio de metastore encontrado")
sys.exit(1)
' "$APP_SP" || FAILED=$((FAILED + 1))

if [[ "$FAILED" -gt 0 ]]; then
  echo "==> Concluído com ${FAILED} problema(s). Verifique se sua identidade é admin do metastore."
  exit 1
fi

echo "==> Pronto. O app já pode criar metadados e relacionamentos de linhagem externa."
echo "    Reinicie o app se ele estiver rodando: databricks apps stop/start ${APP_NAME} -p ${PROFILE}"
