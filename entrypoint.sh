#!/bin/bash
set -e

# 🔍 ПОЛНЫЙ СПИСОК ФАЙЛОВ В /app (для отладки)
echo "🔍 FULL /app CONTENTS:" >&2
find /app -maxdepth 3 -type f -name "*.ico" -o -name "*.svg" -o -name "test_static.txt" 2>/dev/null | head -20 >&2
echo "🔍 STATIC FOLDER CHECK:" >&2
ls -laR /app/static 2>&1 | head -30 >&2 || echo "❌ /app/static NOT FOUND" >&2
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