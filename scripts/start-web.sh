#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  echo 'Installez les dépendances Python et frontend selon README-web.md.' >&2
  exit 1
fi
backend_pid=''
frontend_pid=''
cleanup() {
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
.venv/bin/python -m uvicorn web.app:app --app-dir src --host 127.0.0.1 --port 8000 &
backend_pid=$!
node frontend/node_modules/vite/bin/vite.js frontend --config frontend/vite.config.ts &
frontend_pid=$!
echo 'Application : http://127.0.0.1:5173 — Ctrl+C pour arrêter les deux serveurs.'
wait -n "$backend_pid" "$frontend_pid"
