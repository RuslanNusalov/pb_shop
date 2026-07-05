#!/bin/bash
set -e

if [ -z "${POSTGRES_HOST}" ]; then
  echo "POSTGRES_HOST is not set"
  exit 1
fi

echo "Ожидание PostgreSQL (${POSTGRES_HOST}:${POSTGRES_PORT:-5432})..."
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER}" > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL готов."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
