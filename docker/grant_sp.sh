#!/usr/bin/env bash
# Concede ao service principal do container (DATABRICKS_CLIENT_ID do docker/.env)
# o que o bundle concede ao SP do Databricks App — o bundle só cuida daquele SP.
#
#   1. CAN_USE no warehouse (DATABRICKS_WAREHOUSE_ID)
#   2. Unity Catalog: leitura em bronze/silver/gold/reference, leitura+escrita nas
#      tabelas de governance que o app grava, leitura das execuções da DQX Studio
#   3. Lakebase: role Postgres do SP + GRANT de leitura em dq_resolved_rules
#   4. (--byol) Linhagem gravável: CREATE EXTERNAL METADATA + MODIFY em bronze/gold
#
# Idempotente: pode ser reexecutado. O SP vem do docker/.env; warehouse, catálogos
# e Lakebase, do docker/.env.bundle (gerado pelo setup.sh — que já chama este script).
#
# Uso:
#   ./docker/grant_sp.sh -p <perfil>
#   ./docker/grant_sp.sh -p <perfil> --byol          # + linhagem gravável
#   ./docker/grant_sp.sh -p <perfil> --skip-lakebase # só warehouse + UC
#
# Quem roda: owner do warehouse, com MANAGE nos catálogos do RC18 e da DQX;
# `DATABRICKS_SUPERUSER` no branch Lakebase da Studio (passo 3); admin do
# metastore (--byol). Requer Databricks CLI, python3 e psql.

set -euo pipefail

PROFILE=""
DOCKER_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DOCKER_DIR/.env"
BUNDLE_ENV="$DOCKER_DIR/.env.bundle"
BYOL=0
SKIP_LAKEBASE=0

usage() {
  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile)    PROFILE="$2"; shift 2 ;;
    --byol)          BYOL=1; shift ;;
    --skip-lakebase) SKIP_LAKEBASE=1; shift ;;
    -h|--help)       usage 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

# Sem default de perfil: rodar no workspace errado concederia acesso ao SP errado.
[[ -n "$PROFILE" ]] || { echo "ERRO: informe o perfil do CLI com -p <perfil>." >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "ERRO: $ENV_FILE não existe (cp docker/.env.example docker/.env)." >&2; exit 1; }
[[ -f "$BUNDLE_ENV" ]] || { echo "ERRO: $BUNDLE_ENV não existe — rode ./docker/setup.sh." >&2; exit 1; }
for bin in databricks python3; do
  command -v "$bin" >/dev/null || { echo "ERRO: $bin não encontrado." >&2; exit 1; }
done

# Lê KEY=valor literal, como o `--env-file` do Docker (sem `source`: o .env não é shell).
env_get() {
  local v
  v="$(grep -E "^$1=" "$2" | tail -n1 | cut -d= -f2-)" || true
  printf '%s' "$v"
}
bundle_get() { env_get "$1" "$BUNDLE_ENV"; }

SP="$(env_get DATABRICKS_CLIENT_ID "$ENV_FILE")"
WH_ID="$(bundle_get DATABRICKS_WAREHOUSE_ID)"
CATALOG="$(bundle_get DATABRICKS_CATALOG)"
SCHEMA_BRONZE="$(bundle_get SCHEMA_BRONZE)"
SCHEMA_SILVER="$(bundle_get SCHEMA_SILVER)"
SCHEMA_GOLD="$(bundle_get SCHEMA_GOLD)"
SCHEMA_REFERENCE="$(bundle_get SCHEMA_REFERENCE)"
DQX_CATALOG="$(bundle_get DQX_CATALOG)"
DQX_SCHEMA="$(bundle_get DQX_SCHEMA)"
LB_ENDPOINT="$(bundle_get DQX_LAKEBASE_ENDPOINT)"
LB_DATABASE="$(bundle_get DQX_LAKEBASE_DATABASE)"
LB_SCHEMA="$(bundle_get DQX_LAKEBASE_SCHEMA)"
RULES_TABLE="$(bundle_get DQX_RULES_TABLE)"

[[ "$SP" =~ ^[0-9a-f-]{36}$ ]] || { echo "ERRO: DATABRICKS_CLIENT_ID ausente ou não é um application id (UUID)." >&2; exit 1; }
[[ -n "$WH_ID" && "$WH_ID" != "<"* ]] || { echo "ERRO: DATABRICKS_WAREHOUSE_ID ausente no .env.bundle — rode ./docker/setup.sh." >&2; exit 1; }

FAILED=0
ok()   { echo "    OK      $*"; }
fail() { echo "    FALHOU  $*"; FAILED=$((FAILED + 1)); }

echo "==> Perfil: ${PROFILE} | SP: ${SP} | catálogo: ${CATALOG} | warehouse: ${WH_ID}"

# O SP precisa existir NESTE workspace — client id de outro workspace dá invalid_client no app.
SP_NAME="$(databricks service-principals list -p "$PROFILE" -o json \
  --filter "applicationId eq \"${SP}\"" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d[0].get("displayName", "") if d else "")')"
[[ -n "$SP_NAME" ]] || { echo "ERRO: SP ${SP} não existe no workspace do perfil ${PROFILE}." >&2; exit 1; }
echo "==> Service principal: ${SP_NAME}"

# Warehouse recriado (destroy + deploy) muda de id; a Permissions API ainda aceita
# a ACL do id antigo, então só o `get` pega o .env desatualizado.
databricks warehouses get "$WH_ID" -p "$PROFILE" -o json >/dev/null 2>&1 || {
  echo "ERRO: warehouse ${WH_ID} não existe. Atualize DATABRICKS_WAREHOUSE_ID (databricks warehouses list -p ${PROFILE})." >&2
  exit 1
}

# ---------------------------------------------------------------------------
# 1. Warehouse. update-permissions (PATCH) acrescenta à ACL, não a substitui.
# ---------------------------------------------------------------------------
echo "==> [1/4] Warehouse"
if databricks warehouses update-permissions "$WH_ID" -p "$PROFILE" -o json \
     --json "{\"access_control_list\": [{\"service_principal_name\": \"${SP}\", \"permission_level\": \"CAN_USE\"}]}" \
     >/dev/null; then
  ok "CAN_USE no warehouse ${WH_ID}"
else
  fail "CAN_USE no warehouse ${WH_ID}"
fi

# ---------------------------------------------------------------------------
# 2. Unity Catalog, executado no próprio warehouse do container.
# ---------------------------------------------------------------------------
run_sql() {
  local out state
  # 2>&1: em erro de API a CLI escreve texto (não JSON) no stderr — o fallback o exibe.
  out="$(databricks api post /api/2.0/sql/statements -p "$PROFILE" --json "$(python3 -c '
import json, sys
print(json.dumps({"statement": sys.argv[1], "warehouse_id": sys.argv[2], "wait_timeout": "50s"}))
' "$1" "$WH_ID")" 2>&1)" || true
  state="$(printf '%s' "$out" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
    st = d.get("status", {})
    print(st.get("state", "UNKNOWN"), (st.get("error", {}).get("message") or d.get("message", ""))[:300])
except Exception:
    print("ERRO", raw.strip()[:300])')"
  if [[ "$state" == SUCCEEDED* ]]; then ok "$1"; else fail "$1"; echo "            ${state}"; fi
}

echo "==> [2/4] Unity Catalog"
UC=(
  # Execuções da DQX Studio (Delta) — leitura.
  "GRANT USE CATALOG ON CATALOG \`${DQX_CATALOG}\` TO \`${SP}\`"
  "GRANT USE SCHEMA ON SCHEMA \`${DQX_CATALOG}\`.\`${DQX_SCHEMA}\` TO \`${SP}\`"
)
for t in dq_validation_runs dq_metrics dq_quarantine_records; do
  UC+=("GRANT SELECT ON TABLE \`${DQX_CATALOG}\`.\`${DQX_SCHEMA}\`.\`${t}\` TO \`${SP}\`")
done
UC+=("GRANT USE CATALOG ON CATALOG \`${CATALOG}\` TO \`${SP}\`")
for s in "$SCHEMA_BRONZE" "$SCHEMA_SILVER" "$SCHEMA_GOLD" "$SCHEMA_REFERENCE"; do
  UC+=("GRANT USE SCHEMA, SELECT ON SCHEMA \`${CATALOG}\`.\`${s}\` TO \`${SP}\`")
done
# governance: MODIFY por TABELA, só nas que o app grava — nunca no schema inteiro.
UC+=("GRANT USE SCHEMA ON SCHEMA \`${CATALOG}\`.\`governance\` TO \`${SP}\`")
for s in "${UC[@]}"; do run_sql "$s"; done

# Essas tabelas nascem no rc18_end_to_end, não no deploy: ausente = pendente, não falha.
PENDING=()
for t in incidents cadoc_documentos cadoc_tabelas regra_vinculos; do
  fqn="${CATALOG}.governance.${t}"
  if [[ "$(databricks tables exists "$fqn" -p "$PROFILE" -o json 2>/dev/null \
          | python3 -c 'import json,sys; print(json.load(sys.stdin).get("table_exists", False))' 2>/dev/null)" == "True" ]]; then
    run_sql "GRANT SELECT, MODIFY ON TABLE \`${CATALOG}\`.\`governance\`.\`${t}\` TO \`${SP}\`"
  else
    PENDING+=("$fqn")
    echo "    PENDENTE ${fqn} ainda não existe"
  fi
done

# ---------------------------------------------------------------------------
# 3. Lakebase. Role dá LOGIN; o GRANT de objeto roda dentro do Postgres. Este role
#    não é recriado por `bundle deploy` (é do SP do container), então o GRANT fica.
# ---------------------------------------------------------------------------
echo "==> [3/4] Lakebase (regras da DQX Studio)"
if [[ "$SKIP_LAKEBASE" -eq 1 ]]; then
  echo "    PULADO  --skip-lakebase"
elif [[ -z "$LB_ENDPOINT" || "$LB_ENDPOINT" == "__unset__" ]]; then
  echo "    PULADO  DQX_LAKEBASE_ENDPOINT não definido"
elif ! command -v psql >/dev/null; then
  fail "psql não encontrado (brew install libpq) — necessário para o GRANT"
else
  BRANCH="${LB_ENDPOINT%/endpoints/*}"   # projects/<p>/branches/<b>
  HAS_ROLE="$(databricks postgres list-roles "$BRANCH" -p "$PROFILE" -o json | python3 -c '
import json, sys
d = json.load(sys.stdin)
roles = d.get("roles", d) if isinstance(d, dict) else d
print(any(((r.get("status") or {}).get("postgres_role") or (r.get("spec") or {}).get("postgres_role")) == sys.argv[1]
          for r in roles))' "$SP")"
  if [[ "$HAS_ROLE" == "True" ]]; then
    ok "role ${SP} já existe em ${BRANCH}"
  elif databricks postgres create-role "$BRANCH" -p "$PROFILE" -o json --role-id "sp-${SP}" \
         --json "{\"spec\": {\"identity_type\": \"SERVICE_PRINCIPAL\", \"postgres_role\": \"${SP}\", \"auth_method\": \"LAKEBASE_OAUTH_V1\"}}" \
         >/dev/null; then
    ok "role ${SP} criado em ${BRANCH}"
  else
    fail "criar role ${SP} em ${BRANCH}"
  fi

  # Aspas duplas obrigatórias: o nome do role é um UUID.
  PG_SQL="GRANT USAGE ON SCHEMA \"${LB_SCHEMA}\" TO \"${SP}\"; GRANT SELECT ON TABLE \"${LB_SCHEMA}\".\"${RULES_TABLE}\" TO \"${SP}\";"
  if databricks psql "$LB_ENDPOINT" -p "$PROFILE" -- -d "$LB_DATABASE" -v ON_ERROR_STOP=1 -q -c "$PG_SQL"; then
    ok "USAGE em ${LB_SCHEMA} + SELECT em ${LB_SCHEMA}.${RULES_TABLE}"
  else
    fail "GRANT no Postgres — exige DATABRICKS_SUPERUSER no branch (quem deployou a Studio)"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Linhagem gravável (opcional). CREATE EXTERNAL METADATA é de metastore.
# ---------------------------------------------------------------------------
echo "==> [4/4] Linhagem gravável (BYOL)"
if [[ "$BYOL" -eq 1 ]]; then
  run_sql "GRANT CREATE EXTERNAL METADATA ON METASTORE TO \`${SP}\`"
  for s in "$SCHEMA_BRONZE" "$SCHEMA_GOLD"; do
    run_sql "GRANT MODIFY ON SCHEMA \`${CATALOG}\`.\`${s}\` TO \`${SP}\`"
  done
else
  echo "    PULADO  use --byol para habilitar criar/editar na tela Linhagem"
fi

if [[ "$FAILED" -gt 0 ]]; then
  echo "==> Concluído com ${FAILED} falha(s)."
  exit 1
fi
if [[ "${#PENDING[@]}" -gt 0 ]]; then
  echo "==> ${#PENDING[@]} grant(s) pendente(s): rode o rc18_end_to_end e depois ./docker/grant_sp.sh -p ${PROFILE} de novo."
fi
echo "==> Pronto. Confira em http://localhost:<RC18_PORT>/api/v1/diagnostics/prereqs (\"Re-verificar\" no app)."
