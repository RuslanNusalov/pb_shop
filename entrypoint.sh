#!/bin/bash
set -e

echo "🔄 Ожидание базы данных..."

# Ждём подключения к PostgreSQL
for i in {1..30}; do
    if pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-postgres}" >/dev/null 2>&1; then
        echo "✅ База данных готова!"
        break
    fi
    echo "⏳ Попытка $i/30... Ждём БД..."
    sleep 2
done

echo "🚀 Запуск миграций..."
python manage.py migrate --noinput

echo "📦 Сборка статики..."
python manage.py collectstatic --noinput --clear || true

echo "🔥 Запуск Gunicorn..."
exec gunicorn pb_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -