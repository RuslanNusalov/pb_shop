"""
Django settings for pb_shop project.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# 🔐 Безопасность
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me')
if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY environment variable is required')

DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
    if host.strip()
]

# 📦 Приложения
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main',
    'cart',
    'users',
    'orders',
    'payment',
    'wishlist',
]

# 🔄 Middleware (Whitenoise только один раз!)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ← Один раз, в нужном месте
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'cart.middleware.CartMiddleware',
]

ROOT_URLCONF = 'pb_shop.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.csrf',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cart.context_processors.cart_processor',
                'main.context_processors.global_wishlist_count',
                'main.context_processors.global_categories',
            ],
        },
    },
]

WSGI_APPLICATION = 'pb_shop.wsgi.application'

# 🗄️ База данных (ЕДИНЫЙ блок с поддержкой Amvera и локалки)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        
        # Amvera переменные (PG*) с фоллбэком на локальные (POSTGRES_*)
        'NAME': os.getenv('PGDATABASE', os.getenv('POSTGRES_DB', 'pb_shop')),
        'USER': os.getenv('PGUSER', os.getenv('POSTGRES_USER', 'pb_shop')),
        'PASSWORD': os.getenv('PGPASSWORD', os.getenv('POSTGRES_PASSWORD', 'pb_shop')),
        'HOST': os.getenv('PGHOST', os.getenv('POSTGRES_HOST', 'localhost')),
        'PORT': os.getenv('PGPORT', os.getenv('POSTGRES_PORT', '5432')),
        
        # Оптимизация для продакшена
        'ATOMIC_REQUESTS': True,
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }
}

# 🔐 Валидация паролей
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 🌍 Интернационализация
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
DATE_FORMAT = 'd.m.Y'
DATETIME_FORMAT = 'd.m.Y H:i'

# 📁 Статика и медиа
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # Для Amvera: смонтируй /app/media в Storage

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 🍪 Сессии и авторизация
SESSION_COOKIE_AGE = 86400  # 1 день
SESSION_SAVE_EVERY_REQUEST = True
AUTH_USER_MODEL = 'users.CustomUser'
LOGIN_URL = '/users/login/'
LOGIN_REDIRECT_URL = 'users:profile'
LOGOUT_REDIRECT_URL = 'main:index'

# 🛡️ CSRF и безопасность
CSRF_TRUSTED_ORIGINS = [
    'https://spbpb.ru',
    'https://www.spbpb.ru',
    'https://*.amvera.cloud',
]

# ⚡ Продакшен-настройки (только если DEBUG=False)
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'