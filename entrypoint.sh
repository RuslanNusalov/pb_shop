#!/bin/bash
set -e

echo "========================================"
echo "📂 1. ПРОВЕРКА КОРНЯ (/app)"
echo "========================================"
# Выводим ВСЕ файлы в корне, чтобы увидеть, есть ли static
ls -la /app

echo "========================================"
echo "📂 2. ПРОВЕРКА STATIC"
echo "========================================"
# || true означает "даже если ошибка, продолжать скрипт"
ls -la /app/static || echo "️ Папка /app/static не найдена!"

echo "========================================"
echo " 3. MIGRATIONS"
echo "========================================"
python manage.py migrate --noinput

echo "========================================"
echo "📦 4. COLLECTSTATIC"
echo "========================================"
python manage.py collectstatic --noinput --clear --verbosity 2

echo "========================================"
echo "✅ 5. STARTING GUNICORN"
echo "========================================"
exec gunicorn pb_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -