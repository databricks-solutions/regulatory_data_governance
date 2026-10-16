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
# databricks.yml (a linha vale para TODOS os targets do repositório);
# docker/.env com o SP do container;
# Databricks CLI, python3 e Docker.

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

if [[ "$SKIP_DEPLOY" -eq 1 ]]; then
  echo "    PULADO  --skip-deploy"
else
  databricks bundle deploy "${BUNDLE_ARGS[@]}"
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
