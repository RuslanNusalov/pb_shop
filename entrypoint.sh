#!/bin/bash
set -e

echo "🔄 Applying migrations..."
python manage.py migrate --noinput

echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --clear

# Временное создание суперпользователя (УДАЛИТЬ ПОСЛЕ СОЗДАНИЯ!)
export DJANGO_SUPERUSER_USERNAME=admin
export DJANGO_SUPERUSER_EMAIL=spbpb@bk.ru
export DJANGO_SUPERUSER_PASSWORD=zipjyk-nudju6-cUffot
python manage.py createsuperuser --noinput || true

echo "🚀 Starting Gunicorn..."
exec gunicorn pb_shop.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -