#!/bin/bash
set -e

echo "========================================"
echo "📂 1. ПРОВЕРКА КОРНЯ (/app)"
echo "========================================"
ls -la /app

echo "========================================"
echo "📂 2. ПРОВЕРКА STATIC"
echo "========================================"
ls -la /app/static || echo "⚠️ Папка /app/static не найдена!"

echo "========================================"
echo "📁 3. ПОДГОТОВКА MEDIA (КРИТИЧНО!)"
echo "========================================"
# Создаем папку media, если её нет, и даем права пользователю appuser
mkdir -p /app/media
chown -R appuser:appuser /app/media
chmod -R 755 /app/media
echo "✅ Папка /app/media готова к записи"

echo "========================================"
echo "🔄 4. MIGRATIONS"
echo "========================================"
python manage.py migrate --noinput

echo "========================================"
echo "📦 5. COLLECTSTATIC"
echo "========================================"
python manage.py collectstatic --noinput --clear --verbosity 2

echo "========================================"
echo "✅ 6. STARTING GUNICORN"
echo "========================================"
exec gunicorn pb_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -