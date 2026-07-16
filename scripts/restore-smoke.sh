#!/usr/bin/env sh
set -eu

source_url="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/transcriber_restore_source}"
target_url="${RESTORE_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/transcriber_restore_target}"
source_admin_url="${source_url%/*}/postgres"
target_admin_url="${target_url%/*}/postgres"
source_db="${source_url##*/}"
target_db="${target_url##*/}"
backup_file="$(mktemp "${TMPDIR:-/tmp}/transcriber-restore-smoke.dump.XXXXXX")"

validate_database_name() {
  case "$1" in
    ""|*[!A-Za-z0-9_]* )
      echo "Invalid restore smoke database name" >&2
      exit 1
      ;;
  esac
}

drop_database() {
  psql "$1" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$2\";"
}

create_database() {
  psql "$1" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$2\";"
}

validate_database_name "$source_db"
validate_database_name "$target_db"

cleanup() {
  rm -f "$backup_file"
  drop_database "$source_admin_url" "$source_db" >/dev/null 2>&1 || true
  drop_database "$target_admin_url" "$target_db" >/dev/null 2>&1 || true
}
trap cleanup EXIT

drop_database "$source_admin_url" "$source_db" >/dev/null 2>&1 || true
drop_database "$target_admin_url" "$target_db" >/dev/null 2>&1 || true
create_database "$source_admin_url" "$source_db"
create_database "$target_admin_url" "$target_db"

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
