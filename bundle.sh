#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$PROJECT_ROOT"
export DATABRICKS_BUNDLE_ENGINE="${DATABRICKS_BUNDLE_ENGINE:-direct}"
exec databricks bundle "$@"
