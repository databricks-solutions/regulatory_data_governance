#!/usr/bin/env bash
# Deploy the rc18-starter-kit accelerator bundle to a Databricks workspace.
#
#   1. Loads variables from `.env` at the repo root (host, warehouse, dashboards, …)
#   2. Runs `databricks bundle deploy`, passing warehouse_id from $DATABRICKS_WAREHOUSE_ID
#   3. Generates a runtime app.yaml with values from .env (the source-tree app.yaml
#      stays empty so secrets/IDs never leak into git) and uploads it over the
#      bundle's app.yaml in the workspace
#   4. Calls `databricks apps deploy` so the running container picks up the env
#
# Usage:
#   ./scripts/deploy.sh             # uses target=dev, profile from .env or DEFAULT
#   ./scripts/deploy.sh prod        # custom target
#   TARGET=dev PROFILE=ssa-latam ./scripts/deploy.sh
#
# Requirements: databricks CLI authenticated, .env populated (see .env.example).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

TARGET="${1:-${TARGET:-dev}}"
APP_NAME="${APP_NAME:-rc18-starter-kit}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example to .env and fill in values." >&2
  exit 1
fi

# Load .env into current shell
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Profile precedence: explicit PROFILE env var > DATABRICKS_PROFILE from .env
PROFILE="${PROFILE:-${DATABRICKS_PROFILE:-}}"

: "${PROFILE:?Set DATABRICKS_PROFILE in .env (or export PROFILE=<name>) to pick a databrickscfg profile}"
: "${DATABRICKS_WAREHOUSE_ID:?DATABRICKS_WAREHOUSE_ID must be set in .env}"

echo "==> Target: $TARGET   Profile: $PROFILE   App: $APP_NAME"
echo "==> Warehouse: $DATABRICKS_WAREHOUSE_ID"

# 1. Bundle deploy (uploads sources + creates/updates resources)
echo "==> databricks bundle deploy ..."
databricks bundle deploy \
  -t "$TARGET" \
  -p "$PROFILE" \
  --var "warehouse_id=$DATABRICKS_WAREHOUSE_ID" \
  || echo "WARNING: bundle deploy returned non-zero (likely partial — pipelines may fail; continuing to deploy the app)."

# 2. Generate runtime app.yaml from .env (NOT committed)
RUNTIME_YAML="$(mktemp -t app_runtime.XXXXXX.yaml)"
trap 'rm -f "$RUNTIME_YAML"' EXIT

cat > "$RUNTIME_YAML" <<EOF
command:
  - "uvicorn"
  - "main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"
  - "--workers"
  - "2"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    value: "${DATABRICKS_WAREHOUSE_ID}"
  - name: GENIE_SPACE_ID
    value: "${GENIE_SPACE_ID:-}"
  - name: USE_MOCK_BACKEND
    value: "${USE_MOCK_BACKEND:-true}"
  - name: DATABRICKS_CATALOG
    value: "${DATABRICKS_CATALOG:-rc18_catalog}"
  - name: SCHEMA_GOLD
    value: "${SCHEMA_GOLD:-gold}"
  - name: SCHEMA_SILVER
    value: "${SCHEMA_SILVER:-silver}"
  - name: SCHEMA_QUALITY
    value: "${SCHEMA_QUALITY:-quality}"
  - name: SCHEMA_REFERENCE
    value: "${SCHEMA_REFERENCE:-reference}"
  - name: DASHBOARD_ID_CONFORMIDADE
    value: "${DASHBOARD_ID_CONFORMIDADE:-}"
  - name: DASHBOARD_ID_CRITICAS
    value: "${DASHBOARD_ID_CRITICAS:-}"
EOF

# 3. Upload runtime app.yaml on top of the bundle's empty app.yaml
WORKSPACE_USER="$(databricks current-user me -p "$PROFILE" --output json | python3 -c 'import sys,json;print(json.load(sys.stdin)["userName"])')"
BUNDLE_APP_YAML="/Workspace/Users/${WORKSPACE_USER}/.bundle/${APP_NAME}/${TARGET}/files/app/backend/app.yaml"

echo "==> Overlaying runtime app.yaml at $BUNDLE_APP_YAML"
databricks workspace import "$BUNDLE_APP_YAML" \
  --file "$RUNTIME_YAML" \
  --format AUTO \
  --overwrite \
  -p "$PROFILE"

# 4. Deploy the app pointing at the bundle source path
SOURCE_PATH="/Workspace/Users/${WORKSPACE_USER}/.bundle/${APP_NAME}/${TARGET}/files/app/backend"
echo "==> databricks apps deploy $APP_NAME"
databricks apps deploy "$APP_NAME" \
  --source-code-path "$SOURCE_PATH" \
  -p "$PROFILE"

echo ""
echo "==> Done. App status:"
databricks apps get "$APP_NAME" -p "$PROFILE" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("    URL:   " + d["url"])
print("    State: " + d["app_status"]["state"])
'
