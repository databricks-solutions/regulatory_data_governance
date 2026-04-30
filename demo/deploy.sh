#!/usr/bin/env bash
# Deploy the rc18-demo bundle end-to-end:
#   1. databricks bundle deploy        — uploads sources + creates the app shell, jobs, catalog, schemas
#   2. databricks bundle run <app key> — triggers `databricks apps deploy` so the running container
#                                        picks up the freshly uploaded code (otherwise the app stays
#                                        in "App Not Available")
#
# Usage:
#   ./demo/deploy.sh                       # default target: dev-azure
#   ./demo/deploy.sh dev-aws               # custom target (dev-azure | dev-aws | dev-gcp | prod-*)
#   PROFILE=ssa-latam ./demo/deploy.sh
#   TARGET=prod-azure PROFILE=ssa ./demo/deploy.sh
#
# Requirements: databricks CLI authenticated; run from any directory (script cd's into demo/).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TARGET="${1:-${TARGET:-dev-azure}}"

# Profile precedence: explicit PROFILE env var > DATABRICKS_PROFILE > CLI default
PROFILE="${PROFILE:-${DATABRICKS_PROFILE:-}}"
PROFILE_ARG=()
if [[ -n "$PROFILE" ]]; then
  PROFILE_ARG=(-p "$PROFILE")
fi

echo "==> Target: $TARGET   Profile: ${PROFILE:-<CLI default>}"

# 1. Bundle deploy — uploads files and creates/updates resources.
echo "==> databricks bundle deploy -t $TARGET"
databricks bundle deploy -t "$TARGET" "${PROFILE_ARG[@]}"

# 2. Push the uploaded source into the running Databricks App.
#    `bundle run <app_key>` calls `apps deploy` under the hood and waits for the
#    deployment to reach a terminal state.
echo "==> databricks bundle run r18_compliance_app -t $TARGET"
databricks bundle run r18_compliance_app -t "$TARGET" "${PROFILE_ARG[@]}"

echo ""
echo "==> Demo deployed. App URL is shown above."
echo "    Run a synthetic data job with:"
echo "      databricks bundle run synthetic_data_loader -t $TARGET"
echo "      databricks bundle run scr3040_generator -t $TARGET"
echo "      databricks bundle run scr3050_generator -t $TARGET"
