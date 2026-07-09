#!/usr/bin/env sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

output="${1:-backups/transcriber-$(date -u +%Y%m%dT%H%M%SZ).dump}"
mkdir -p "$(dirname "$output")"

pg_dump --format=custom --no-owner --no-acl --file "$output" "$DATABASE_URL"
echo "$output"
