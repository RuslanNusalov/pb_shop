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

# Точные URL из официальной документации Ozon
OZON_AUTHORIZE_URL = "https://seller.ozon.ru/app/appstore/oauth/authorize"
OZON_TOKEN_URL = "https://api-seller.ozon.ru/v1/oauth/token"

def ozon_oauth_login(request):
    """Шаг 1: Формируем ссылку авторизации строго по документации Ozon"""
    client_id = settings.OZON_OAUTH_CLIENT_ID
    redirect_uri = settings.OZON_OAUTH_REDIRECT_URI
    
    # 1. Генерируем уникальный state для защиты от CSRF-атак
    state = secrets.token_urlsafe(16)
    request.session['ozon_oauth_state'] = state
    
    # 2. Формируем scope (разделены пробелом, как в доке)
    # Убедитесь, что эти скоупы выданы приложению в кабинете Ozon!
    scope = "seller-api.ozon-logistics seller-api.posting-fbs seller-api.product seller-api.returns seller-api.report"
    
    # 3. Кодируем redirect_uri для безопасной передачи в URL
    encoded_redirect_uri = quote(redirect_uri, safe='')
    encoded_scope = quote(scope, safe='')
    
    # 4. Собираем URL строго по шаблону из документации
    auth_url = (
        f"{OZON_AUTHORIZE_URL}?"
        f"response_type=code&"
        f"access_type=offline&"
        f"client_id={client_id}&"
        f"redirect_uri={encoded_redirect_uri}&"
        f"scope={encoded_scope}&"
        f"state={state}&"
        f"prompt=select_company"
    )
    
    logger.info(f"OAuth redirect to: {auth_url}")
    return redirect(auth_url)


def ozon_oauth_callback(request):
    """Шаг 2: Ozon возвращает code и state, меняем code на токены"""
    code = request.GET.get('code')
    returned_state = request.GET.get('state')
    saved_state = request.session.get('ozon_oauth_state')
    
    # Проверка наличия кода
    if not code:
        return HttpResponse(f"❌ Нет code. Параметры: {request.GET.dict()}", status=400)
    
    # Проверка state (защита от CSRF)
    if returned_state != saved_state:
        return HttpResponse("❌ Ошибка безопасности: несовпадение state", status=403)
        
    # Очищаем state из сессии после использования
    if 'ozon_oauth_state' in request.session:
        del request.session['ozon_oauth_state']

    # Обмен code на токены
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.OZON_OAUTH_CLIENT_ID,
        "client_secret": settings.OZON_OAUTH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.OZON_OAUTH_REDIRECT_URI
    }

    response = requests.post(OZON_TOKEN_URL, json=payload, timeout=15)
    
    if response.status_code == 200:
        data = response.json()
        
        # Сохраняем или обновляем токены в БД
        OzonAuth.objects.update_or_create(
            is_active=True,
            defaults={
                'access_token': data['access_token'],
                'refresh_token': data.get('refresh_token', ''),
                'expires_at': timezone.now() + timedelta(seconds=data.get('expires_in', 3600))
            }
        )
        return HttpResponse(
            "<h1>✅ Авторизация Ozon Delivery прошла успешно!</h1>"
            "<p>Токены сохранены. Можно тестировать методы доставки.</p>"
        )
    else:
        logger.error(f"Token exchange failed: {response.text}")
        return HttpResponse(
            f"❌ Ошибка получения токена:<br><pre>{response.text}</pre>", 
            status=400
        )