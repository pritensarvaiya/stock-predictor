#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add GEMINI_API_KEY there if you want Gemini summaries."
fi

cd frontend
npm install
echo
echo "Setup finished. Start the app with ./scripts/dev.sh"
echo "The shipped model is ready. The first Nifty 200 watchlist scan downloads prices and can take a few minutes."
