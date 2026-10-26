#!/usr/bin/env bash
# LineageLens launcher for macOS / Linux.
# First run: creates .venv and installs pinned dependencies. Later runs start straight away.
# Usage: ./start.sh                      (bundled sample project)
#        ./start.sh -c lineagelens.yml   (your own config; any `lineagelens serve` option works)
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is required. macOS: 'brew install python@3.12' or https://www.python.org/downloads/" >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment with $PY ..."
  "$PY" -m venv .venv
fi
STAMP=.venv/.lineagelens-installed
if [ ! -f "$STAMP" ] || [ pyproject.toml -nt "$STAMP" ]; then
  echo "Installing LineageLens (one-time, about a minute) ..."
  .venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
  .venv/bin/python -m pip install --disable-pip-version-check -q --require-hashes -r requirements.lock
  .venv/bin/python -m pip install --disable-pip-version-check -q --no-deps .
  touch "$STAMP"
fi

exec .venv/bin/lineagelens serve "$@"
