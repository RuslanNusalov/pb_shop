# #!/bin/bash
# set -e

# echo "🔄 Ожидание базы данных..."

# # Ждём подключения к PostgreSQL
# for i in {1..30}; do
#     if pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-postgres}" >/dev/null 2>&1; then
#         echo "✅ База данных готова!"
#         break
#     fi
#     echo "⏳ Попытка $i/30... Ждём БД..."
#     sleep 2
# done

# echo "🚀 Запуск миграций..."
# python manage.py migrate --noinput

# echo "📂 ПРОВЕРКА ИСХОДНОЙ СТАТИКИ:"
# ls -la /app/static/
# ls -la /app/static/img/ || echo "️ Папка img не найдена!"

# echo "📦 Сборка статики..."
# python manage.py collectstatic --noinput --clear --verbosity 2

# echo "🔥 Запуск Gunicorn..."
# exec gunicorn pb_shop.wsgi:application \
#     --bind 0.0.0.0:8000 \
#     --workers 3 \
#     --threads 2 \
#     --timeout 120 \
#     --access-logfile - \
#     --error-logfile -






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