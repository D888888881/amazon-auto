#!/usr/bin/env bash
set -euo pipefail

# Django 读 DB_*；.env 里写的是 MYSQL_*（与官方 MySQL 镜像一致）。不在 compose 里做 ${MYSQL_PASSWORD} 替换，以免宿主机 export 覆盖 .env。
export DB_NAME="${DB_NAME:-${MYSQL_DATABASE:-auto_amazon}}"
export DB_USER="${DB_USER:-${MYSQL_USER:-auto_amazon}}"
export DB_PASSWORD="${DB_PASSWORD:-${MYSQL_PASSWORD:-}}"
export DB_HOST="${DB_HOST:-db}"
export DB_PORT="${DB_PORT:-3306}"

if ! python -c "import os; (os.environ.get('DB_PASSWORD') or '').encode('latin-1')" >/dev/null 2>&1; then
  echo "错误: DB_PASSWORD / MYSQL_PASSWORD 含非 ASCII 字符，PyMySQL 无法用 latin-1 编码。" >&2
  echo "请把 .env 里数据库密码改为纯英文数字符号；并检查宿主机是否 export 过 MYSQL_PASSWORD。" >&2
  exit 1
fi

if [ "${1:-}" = "migrate-only" ]; then
  shift
  exec python manage.py migrate "$@"
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
