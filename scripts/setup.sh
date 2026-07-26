#!/usr/bin/env bash
# One-shot setup for a bare-metal install: virtualenv, dependencies,
# appsettings.json with generated tokens, and the database schema.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"

echo "==> creating $VENV"
[ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e ".[dev]"

if [ ! -f appsettings.json ]; then
  echo "==> writing appsettings.json"
  cp appsettings.example.json appsettings.json
  if command -v openssl >/dev/null 2>&1; then
    dashboard=$(openssl rand -hex 32)
    admin=$(openssl rand -hex 32)
    "$VENV/bin/python" - "$dashboard" "$admin" <<'PY'
import json
import sys

with open("appsettings.json", encoding="utf-8") as f:
    settings = json.load(f)
settings["DashboardToken"] = sys.argv[1]
settings["AdminToken"] = sys.argv[2]
with open("appsettings.json", "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY
    echo "    generated a dashboard token and an admin token"
  fi
  echo "    edit PostgresConnectionString before starting the server"
else
  echo "==> appsettings.json already exists, leaving it alone"
fi

if [ -n "${DATABASE_URL:-}" ]; then
  echo "==> applying the schema to \$DATABASE_URL"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f Database/schema.sql
  for migration in Database/migrations/*.sql; do
    [ -e "$migration" ] || continue
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$migration"
  done
else
  echo "==> set DATABASE_URL and rerun, or apply Database/schema.sql yourself"
fi

cat <<'EOF'

Done. Next:
  1. put the game tables in Resources/ (see docs/configuration.md)
  2. .venv/bin/python -m wwps
EOF
