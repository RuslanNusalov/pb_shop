FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.1.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Зависимости Python
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --no-ansi --only main

# Код проекта
COPY . .

# Сборка статики (Amvera смонтирует volume поверх, но collectstatic нужен)
RUN python manage.py collectstatic --noinput

# Права доступа
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck для Amvera
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/admin/')" || exit 1

COPY fix_admin_user.py /app/
RUN python fix_admin_user.py


# Запуск через Gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn pb_shop.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 120 --access-logfile - --error-logfile -"]
