#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "migrate-only" ]; then
  shift
  exec python manage.py migrate "$@"
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
