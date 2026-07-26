#!/usr/bin/env bash
# Waits for PostgreSQL, applies the schema and any migrations, then starts the
# server. Every statement is idempotent, so this is safe on each boot.
set -euo pipefail

DSN="${WWPS_POSTGRES_CONNECTION_STRING:-}"
SCHEMA_DIR="${WWPS_SCHEMA_DIR:-/app/Database}"
WAIT_SECONDS="${WWPS_DB_WAIT_SECONDS:-60}"

if [ -z "$DSN" ]; then
  echo "WWPS_POSTGRES_CONNECTION_STRING is not set" >&2
  exit 1
fi

echo "waiting for the database (up to ${WAIT_SECONDS}s)"
deadline=$(( $(date +%s) + WAIT_SECONDS ))
until psql "$DSN" -c 'SELECT 1' >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "the database did not become reachable in ${WAIT_SECONDS}s" >&2
    exit 1
  fi
  sleep 1
done

if [ "${WWPS_APPLY_SCHEMA:-1}" = "1" ]; then
  echo "applying the schema"
  psql "$DSN" -v ON_ERROR_STOP=1 -q -f "$SCHEMA_DIR/schema.sql"
  if [ -d "$SCHEMA_DIR/migrations" ]; then
    for migration in "$SCHEMA_DIR"/migrations/*.sql; do
      [ -e "$migration" ] || continue
      echo "applying $(basename "$migration")"
      psql "$DSN" -v ON_ERROR_STOP=1 -q -f "$migration"
    done
  fi
fi

exec "$@"
