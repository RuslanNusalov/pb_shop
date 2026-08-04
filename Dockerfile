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

# Копируем entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Права доступа
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Создаём папку для медиа
RUN mkdir -p /app/media && chown appuser:appuser /app/media

EXPOSE 8000

# Healthcheck: проверяем корень сайта
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Запускаем entrypoint
CMD ["/app/entrypoint.sh"]