#!/usr/bin/env sh
set -eu

backup_file="${1:-}"
target_url="${RESTORE_DATABASE_URL:-${DATABASE_URL:-}}"

if [ -z "$backup_file" ] || [ ! -f "$backup_file" ]; then
  echo "Usage: RESTORE_DATABASE_URL=postgresql://... scripts/restore-postgres.sh <backup.dump>" >&2
  exit 2
fi

if [ -z "$target_url" ]; then
  echo "RESTORE_DATABASE_URL or DATABASE_URL is required" >&2
  exit 2
fi

pg_restore --clean --if-exists --no-owner --no-acl --dbname "$target_url" "$backup_file"
