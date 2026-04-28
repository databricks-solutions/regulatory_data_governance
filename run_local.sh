#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
BACKEND_DIR="$PROJECT_ROOT/app/backend"
FRONTEND_DIR="$PROJECT_ROOT/app/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=5173

cleanup() {
  echo ""
  echo "Shutting down..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# --- Python venv setup ---
echo "==> Setting up Python virtualenv..."
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  echo "    Created virtualenv at .venv/"
fi
source "$VENV_DIR/bin/activate"

# Install deps only if not already satisfied
if ! pip show fastapi &>/dev/null; then
  echo "==> Installing Python dependencies..."
  pip install -q -r "$BACKEND_DIR/requirements.txt"
else
  echo "    Dependencies already installed, skipping pip install."
fi

echo "==> Starting backend on port $BACKEND_PORT..."
USE_MOCK_BACKEND=true uvicorn main:app --reload --port "$BACKEND_PORT" --app-dir "$BACKEND_DIR" &
BACKEND_PID=$!

# --- Frontend setup ---
echo "==> Setting up frontend (SvelteKit)..."
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  (cd "$FRONTEND_DIR" && npm install)
fi

echo "==> Starting frontend on port $FRONTEND_PORT..."
(cd "$FRONTEND_DIR" && npm run dev -- --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Press Ctrl+C to stop both servers"
echo "========================================="
echo ""

wait
