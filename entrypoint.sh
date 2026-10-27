#!/bin/bash
set -e

echo "========================================"
echo "📁 1. ПОДГОТОВКА MEDIA"
echo "========================================"
mkdir -p /app/media
echo "✅ Папка media готова"

echo "========================================"
echo "🔄 2. MIGRATIONS"
echo "========================================"
python manage.py migrate --noinput

echo "========================================"
echo "📦 3. COLLECTSTATIC"
echo "========================================"
python manage.py collectstatic --noinput --clear --verbosity 2

echo "========================================"
echo "✅ 4. STARTING GUNICORN"
echo "========================================"
exec gunicorn pb_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -