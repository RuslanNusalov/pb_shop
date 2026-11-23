import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

import requests
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from .models import OzonAuth

logger = logging.getLogger(__name__)

# ✅ ЕДИНСТВЕННЫЙ РАБОЧИЙ URL ДЛЯ ПОЛУЧЕНИЯ ТОКЕНА
OZON_AUTHORIZE_URL = "https://seller.ozon.ru/app/appstore/oauth/authorize"
OZON_TOKEN_URL = "https://xapi.ozon.ru/oauth/token"

def ozon_oauth_login(request):
    """Шаг 1: Формируем ссылку авторизации"""
    client_id = settings.OZON_OAUTH_CLIENT_ID
    redirect_uri = settings.OZON_OAUTH_REDIRECT_URI
    
    state = secrets.token_urlsafe(16)
    request.session['ozon_oauth_state'] = state
    
    scope = "seller-api.ozon-logistics seller-api.posting-fbs seller-api.product seller-api.returns seller-api.report seller-api.posting-fbo"
    
    encoded_redirect_uri = quote(redirect_uri, safe='')
    encoded_scope = quote(scope, safe='')
    
    auth_url = (
        f"{OZON_AUTHORIZE_URL}?"
        f"response_type=code&"
        f"access_type=offline&"
        f"client_id={client_id}&"
        f"redirect_uri={encoded_redirect_uri}&"
        f"scope={encoded_scope}&"
        f"state={state}&"
        f"prompt=consent"  # ← КЛЮЧЕВОЕ: принудительно показать страницу согласия
    )
    
    logger.warning(f"OAuth redirect to: {auth_url}")
    return redirect(auth_url)


def ozon_oauth_callback(request):
    code = request.GET.get('code')
    if not code:
        return HttpResponse("Ошибка: нет кода авторизации")
    
    client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
    client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
    redirect_uri = getattr(settings, 'OZON_OAUTH_REDIRECT_URI', '')
    
    try:
        response = requests.post(
            "https://api-seller.ozon.ru/appstore-api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"Ошибка получения токена: {response.status_code} {response.text}")
            return HttpResponse(f"Ошибка получения токена: {response.status_code}")
        
        data = response.json()
        
        # Деактивируем старые токены
        OzonAuth.objects.update(is_active=False)
        
        # Создаём новую запись с access_token И refresh_token
        OzonAuth.objects.create(
            access_token=data['access_token'],
            refresh_token=data.get('refresh_token', ''),  # ← СОХРАНЯЕМ refresh_token
            expires_at=timezone.now() + timedelta(hours=1),
            is_active=True
        )
        
        logger.info("✅ OAuth-токен успешно получен и сохранён")
        return HttpResponse("✅ Авторизация Ozon Delivery прошла успешно! Токен сохранён.")
        
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        return HttpResponse(f"Ошибка: {e}")
