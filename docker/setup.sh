#!/usr/bin/env bash
# Setup do RC18 com o app em container: o mesmo `bundle deploy` do fluxo com o
# Databricks App, menos o App, mais a configuração e os grants do container.
#
#   1. confere o modo container (app_hosting + include) e o docker/.env
#   2. databricks bundle deploy           — catálogo, warehouse, jobs, dashboards
#   3. gera docker/.env.bundle (config do app) a partir do bundle
#   4. docker/grant_sp.sh                 — grants do SP do container
#   5. docker compose up + diagnóstico
#
# NÃO roda o rc18_end_to_end: só cria os recursos. Rode o job depois e então
# ./docker/grant_sp.sh -p <perfil> para os grants das tabelas que ele cria.
#
# Uso (da raiz do repo ou de docker/):
#   ./docker/setup.sh -t <target>     # tudo; sem -t, o target default do target.yml
#   ./docker/setup.sh -t <target> --skip-deploy   # só .env.bundle, grants e sobe
#   ./docker/setup.sh -t <target> --byol          # + linhagem gravável (admin do metastore)
#   ./docker/setup.sh -t <target> --no-up         # não sobe o container
#
# O perfil do CLI vem do `workspace.profile` do target. Pré-requisitos: o target
# com `app_hosting: container` e a linha `resources/app/*.yml` comentada no
# databricks.yml — a linha vale para TODOS os targets, então use um worktree só
# para o container (docker/README.md); docker/.env com o SP do container;
# Databricks CLI, python3, psql e Docker.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER_DIR="$REPO/docker"
ENV_FILE="$DOCKER_DIR/.env"
BUNDLE_ENV="$DOCKER_DIR/.env.bundle"
SKIP_DEPLOY=0
NO_UP=0
GRANT_ARGS=()
BUNDLE_ARGS=()

usage() {
  sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--target)   BUNDLE_ARGS=(-t "$2"); shift 2 ;;
    --skip-deploy) SKIP_DEPLOY=1; shift ;;
    --no-up)       NO_UP=1; shift ;;
    --byol)        GRANT_ARGS+=(--byol); shift ;;
    -h|--help)     usage 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage 1 ;;
  esac
done

die() { echo "ERRO: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

for bin in databricks python3 docker curl; do
  command -v "$bin" >/dev/null || die "$bin não encontrado."
done
cd "$REPO"

env_get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

# ── 1. Pré-condições ────────────────────────────────────────────────────────
step "[1/5] Conferindo configuração"
[[ -f "$ENV_FILE" ]] || die "docker/.env não existe: cp docker/.env.example docker/.env e preencha o SP."
[[ "$(env_get DATABRICKS_CLIENT_ID)" =~ ^[0-9a-f-]{36}$ ]] || die "DATABRICKS_CLIENT_ID do docker/.env não é um application id (UUID)."
SECRET="$(env_get DATABRICKS_CLIENT_SECRET)"
[[ -n "$SECRET" && "$SECRET" != "<"* ]] || die "DATABRICKS_CLIENT_SECRET do docker/.env não preenchido."

VALIDATE="$(databricks bundle validate "${BUNDLE_ARGS[@]+"${BUNDLE_ARGS[@]}"}" -o json)" || die "bundle validate falhou (target.yml existe?)."
read -r TARGET PROFILE HOSTING HAS_APP <<<"$(printf '%s' "$VALIDATE" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["bundle"].get("target") or "-",
      d["workspace"].get("profile") or "-",
      (d.get("variables", {}).get("app_hosting") or {}).get("value", "-"),
      "sim" if d.get("resources", {}).get("apps") else "nao")')"

[[ "$PROFILE" != "-" ]] || die "workspace.profile não definido no target.yml."
[[ "$HOSTING" == "container" ]] || die "target ${TARGET}: app_hosting=${HOSTING}. Use -t <target> com \`app_hosting: container\` no target.yml."
# Include e variável têm de andar juntos: com o App no include, o task de grants falha.
[[ "$HAS_APP" == "nao" ]] || die "o Databricks App ainda está no bundle. Comente \`- resources/app/*.yml\` no include: do databricks.yml (num deployment existente, o próximo deploy APAGA o App)."
# Daqui em diante, sempre o target resolvido — nunca o default implícito.
BUNDLE_ARGS=(-t "$TARGET")
echo "    target: ${TARGET} | perfil: ${PROFILE} | app_hosting: container"

# ── 2. Deploy ───────────────────────────────────────────────────────────────
step "[2/5] databricks bundle deploy"

# Um database Lakebase aceita UM catálogo UC: se outro deployment já o espelha, o
# registro deste target falharia ("already registered") — então o recurso fica de
# fora deste deploy. Se o espelho já está no estado deste target, ele é daqui e fica.
PG_FILE="$REPO/resources/postgres_catalogs.yml"
PG_STASH=""
restore_pg() { [[ -z "$PG_STASH" ]] || { mv "$PG_STASH/postgres_catalogs.yml" "$PG_FILE"; rmdir "$PG_STASH"; PG_STASH=""; }; }

existing_pg_mirror() {
  local want own c
  want="$(printf '%s' "$VALIDATE" | python3 -c '
import json, sys
pc = (json.load(sys.stdin)["resources"].get("postgres_catalogs") or {}).get("dqx_lakebase")
print(pc["branch"], pc["postgres_database"]) if pc else print("")')"
  [[ -n "$want" ]] || return 0
  own="$(databricks bundle summary "${BUNDLE_ARGS[@]}" -o json | python3 -c '
import json, sys
pc = (json.load(sys.stdin)["resources"].get("postgres_catalogs") or {}).get("dqx_lakebase") or {}
print("sim" if pc.get("id") else "")')"
  [[ -z "$own" ]] || return 0
  for c in $(databricks catalogs list -p "$PROFILE" -o json | python3 -c '
import json, sys
print(" ".join(c["name"] for c in json.load(sys.stdin) if c.get("catalog_type") == "MANAGED_ONLINE_CATALOG"))'); do
    [[ "$(databricks postgres get-catalog "catalogs/$c" -p "$PROFILE" -o json | python3 -c '
import json, sys
s = json.load(sys.stdin).get("status", {})
print(s.get("branch", ""), s.get("postgres_database", ""))')" == "$want" ]] && { echo "$c"; return 0; }
  done
}

if [[ "$SKIP_DEPLOY" -eq 1 ]]; then
  echo "    PULADO  --skip-deploy"
else
  MIRROR="$(existing_pg_mirror)"
  if [[ -n "$MIRROR" ]]; then
    echo "    espelho do Lakebase já existe (${MIRROR}) — pulando resources/postgres_catalogs.yml"
    PG_STASH="$(mktemp -d)"
    trap restore_pg EXIT
    mv "$PG_FILE" "$PG_STASH/"
  fi
  databricks bundle deploy "${BUNDLE_ARGS[@]}"
  restore_pg
  trap - EXIT
fi

# ── 3. Configuração do app ──────────────────────────────────────────────────
step "[3/5] Gerando docker/.env.bundle"
SUMMARY="$(mktemp)"
trap 'rm -f "$SUMMARY"' EXIT
databricks bundle summary "${BUNDLE_ARGS[@]}" -o json >"$SUMMARY"
HOST="$(databricks auth describe -p "$PROFILE" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["details"]["host"])')"
python3 "$DOCKER_DIR/render_env.py" --summary "$SUMMARY" --host "$HOST" --out "$BUNDLE_ENV"
echo "    $(grep -vc '^#' "$BUNDLE_ENV") variáveis em docker/.env.bundle"

# O .env.bundle vence no compose: config do app esquecida no .env é ignorada.
STALE="$(grep -vE '^\s*(#|$)' "$ENV_FILE" | cut -d= -f1 | while read -r k; do
  grep -q "^${k}=" "$BUNDLE_ENV" && printf '%s ' "$k"; done || true)"
[[ -z "$STALE" ]] || echo "    AVISO  ignoradas no docker/.env (o target.yml manda): ${STALE}"

# ── 4. Grants ───────────────────────────────────────────────────────────────
step "[4/5] Grants do SP do container"
"$DOCKER_DIR/grant_sp.sh" -p "$PROFILE" "${GRANT_ARGS[@]+"${GRANT_ARGS[@]}"}"

# ── 5. Container ────────────────────────────────────────────────────────────
step "[5/5] docker compose up"
if [[ "$NO_UP" -eq 1 ]]; then echo "    PULADO  --no-up"; exit 0; fi
docker compose -f "$DOCKER_DIR/compose.yaml" up -d --build --force-recreate

PORT="${RC18_PORT:-$(env_get RC18_PORT)}"
URL="http://localhost:${PORT:-8000}"
for _ in $(seq 1 60); do curl -sf -o /dev/null "$URL/" && break; sleep 2; done
curl -sf -o /dev/null "$URL/" || die "o app não respondeu em ${URL} (docker compose -f docker/compose.yaml logs)."

curl -s --max-time 120 "$URL/api/v1/diagnostics/prereqs" >"$SUMMARY"
python3 - "$SUMMARY" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for c in d["checks"]:
    fix = f"  → {c['remediation']}" if c.get("remediation") else ""
    print(f"    {c['state']:16} {c['id']}{fix}")
print(f"    diagnóstico: {d['state']}")
EOF
echo
echo "==> App em ${URL}"
