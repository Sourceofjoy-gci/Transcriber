#!/usr/bin/env sh
set -eu

source_url="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/transcriber_restore_source}"
target_url="${RESTORE_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/transcriber_restore_target}"
backup_file="$(mktemp "${TMPDIR:-/tmp}/transcriber-restore-smoke.XXXXXX.dump")"

cleanup() {
  rm -f "$backup_file"
  dropdb --if-exists "$source_url" >/dev/null 2>&1 || true
  dropdb --if-exists "$target_url" >/dev/null 2>&1 || true
}
trap cleanup EXIT

dropdb --if-exists "$source_url" >/dev/null 2>&1 || true
dropdb --if-exists "$target_url" >/dev/null 2>&1 || true
createdb "$source_url"
createdb "$target_url"

psql "$source_url" -v ON_ERROR_STOP=1 -c "CREATE TABLE restore_smoke (id integer PRIMARY KEY, value text NOT NULL);"
psql "$source_url" -v ON_ERROR_STOP=1 -c "INSERT INTO restore_smoke VALUES (1, 'ok');"

DATABASE_URL="$source_url" sh scripts/backup-postgres.sh "$backup_file" >/dev/null
RESTORE_DATABASE_URL="$target_url" sh scripts/restore-postgres.sh "$backup_file"

value="$(psql "$target_url" -tAc "SELECT value FROM restore_smoke WHERE id = 1;")"
if [ "$value" != "ok" ]; then
  echo "Restore smoke test failed" >&2
  exit 1
fi

echo "Restore smoke test passed"
