#!/usr/bin/env bash
# Desfaz o ./docker/setup.sh de um target em modo container — o equivalente ao
# `databricks bundle destroy` do fluxo com o Databricks App.
#
#   1. confere o target: exige -t e app_hosting=container (nunca derruba um target
#      com Databricks App)
#   2. docker compose down
#   3. (--revoke-grants) revoga o que o grant_sp.sh deu fora do bundle: os grants
#      na DQX Studio (Delta)
#   4. databricks bundle destroy -t <target> — catálogo (COM OS DADOS), warehouse,
#      jobs, dashboards e o que mais estiver no estado deste target
#   5. apaga o docker/.env.bundle
#
# Uso (da raiz do repo ou de docker/):
#   ./docker/destroy.sh -t <target>                   # pede confirmação no destroy
#   ./docker/destroy.sh -t <target> --revoke-grants   # + revoga grants fora do bundle
#   ./docker/destroy.sh -t <target> --yes             # sem confirmação
#
# --revoke-grants só se o SP do container não servir a outro deployment: os grants
# na DQX são por SP, não por target. Fica de fora: a linhagem
# externa (metastore-scoped, compartilhada entre deployments) — ver README.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER_DIR="$REPO/docker"
ENV_FILE="$DOCKER_DIR/.env"
BUNDLE_ENV="$DOCKER_DIR/.env.bundle"
TARGET_ARG=""
REVOKE=0
YES=0

usage() {
  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--target)     TARGET_ARG="$2"; shift 2 ;;
    --revoke-grants) REVOKE=1; shift ;;
    --yes)           YES=1; shift ;;
    -h|--help)       usage 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

die() { echo "ERRO: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

for bin in databricks python3 docker; do
  command -v "$bin" >/dev/null || die "$bin não encontrado."
done
# Sem default: destruir o target errado não tem volta.
[[ -n "$TARGET_ARG" ]] || die "informe o target com -t <target>."
cd "$REPO"

env_get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

# ── 1. Pré-condições ────────────────────────────────────────────────────────
step "[1/5] Conferindo o target"
VALIDATE="$(databricks bundle validate -t "$TARGET_ARG" -o json)" || die "bundle validate falhou."
read -r TARGET PROFILE HOSTING HAS_APP DQX_CATALOG DQX_SCHEMA <<<"$(printf '%s' "$VALIDATE" | python3 -c '
import json, sys
d = json.load(sys.stdin)
v = lambda k: (d.get("variables", {}).get(k) or {}).get("value", "-")
print(d["bundle"].get("target") or "-", d["workspace"].get("profile") or "-",
      v("app_hosting"), "sim" if d.get("resources", {}).get("apps") else "nao",
      v("dqx_catalog"), v("dqx_schema"))')"

[[ "$PROFILE" != "-" ]] || die "workspace.profile não definido no target ${TARGET}."
[[ "$HOSTING" == "container" ]] || die "target ${TARGET}: app_hosting=${HOSTING}. Este script só desfaz targets em modo container — para os demais, databricks bundle destroy."
[[ "$HAS_APP" == "nao" ]] || die "o Databricks App está no bundle (resources/app/*.yml no include:). Este script não derruba App."
echo "    target: ${TARGET} | perfil: ${PROFILE} | app_hosting: container"

# ── 2. Container ────────────────────────────────────────────────────────────
step "[2/5] docker compose down"
if [[ -f "$ENV_FILE" && -f "$BUNDLE_ENV" ]]; then
  docker compose -f "$DOCKER_DIR/compose.yaml" down
else
  # O compose exige os dois env files; sem eles, derruba pelo nome do projeto.
  docker compose -p rc18 down
fi

# ── 3. Grants fora do bundle ────────────────────────────────────────────────
step "[3/5] Grants do SP do container"
if [[ "$REVOKE" -eq 0 ]]; then
  echo "    PULADO  use --revoke-grants (só se o SP não servir a outro deployment)"
else
  SP="$(env_get DATABRICKS_CLIENT_ID)"
  [[ "$SP" =~ ^[0-9a-f-]{36}$ ]] || die "DATABRICKS_CLIENT_ID do docker/.env não é um application id (UUID)."
  WH_ID="$(printf '%s' "$VALIDATE" | python3 -c '
import json, sys
print((json.load(sys.stdin)["variables"].get("warehouse_id") or {}).get("value", ""))')"
  if [[ "$WH_ID" == '${'* ]]; then
    WH_ID="$(databricks bundle summary -t "$TARGET" -o json | python3 -c '
import json, sys
print(json.load(sys.stdin)["resources"]["sql_warehouses"]["rc18_warehouse"].get("id", ""))')"
  fi
  run_sql() {
    local out
    out="$(databricks api post /api/2.0/sql/statements -p "$PROFILE" --json "$(python3 -c '
import json, sys
print(json.dumps({"statement": sys.argv[1], "warehouse_id": sys.argv[2], "wait_timeout": "50s"}))
' "$1" "$WH_ID")" 2>&1)" || true
    if printf '%s' "$out" | grep -q '"SUCCEEDED"'; then echo "    OK      $1"; else echo "    FALHOU  $1"; fi
  }
  # Os grants no catálogo e no warehouse do bundle somem com o destroy; só os da DQX ficam.
  for t in dq_validation_runs dq_metrics dq_quarantine_records; do
    run_sql "REVOKE SELECT ON TABLE \`${DQX_CATALOG}\`.\`${DQX_SCHEMA}\`.\`${t}\` FROM \`${SP}\`"
  done
  run_sql "REVOKE USE SCHEMA ON SCHEMA \`${DQX_CATALOG}\`.\`${DQX_SCHEMA}\` FROM \`${SP}\`"
  run_sql "REVOKE USE CATALOG ON CATALOG \`${DQX_CATALOG}\` FROM \`${SP}\`"

fi

# ── 4. Bundle ───────────────────────────────────────────────────────────────
step "[4/5] databricks bundle destroy -t ${TARGET}"
DESTROY_ARGS=(-t "$TARGET")
[[ "$YES" -eq 0 ]] || DESTROY_ARGS+=(--auto-approve)
databricks bundle destroy "${DESTROY_ARGS[@]}"

# ── 5. Configuração gerada ──────────────────────────────────────────────────
step "[5/5] Removendo docker/.env.bundle"
rm -f "$BUNDLE_ENV"
echo "    OK"
echo
echo "==> Target ${TARGET} desfeito. O docker/.env (SP do container) foi mantido."
