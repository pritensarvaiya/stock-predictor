#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "No virtualenv yet. Run ./scripts/setup.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACK_PID=$!
FRONT_PID=""

cleanup() {
  kill "$BACK_PID" 2>/dev/null || true
  if [[ -n "${FRONT_PID}" ]]; then
    kill "$FRONT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONT_PID=$!
wait
