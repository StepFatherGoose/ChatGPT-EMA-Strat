#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill in your credentials, then rerun."
  exit 0
fi

python scanner.py --check-config
python scanner.py --dry-run --max-symbols 200

echo
echo "Dry-run complete. If results look good, run:"
echo "  source .venv/bin/activate && python scanner.py"
