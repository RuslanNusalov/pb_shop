from datetime import timedelta

import requests
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from .models import OzonAuth


def ozon_oauth_login(request):
    """Шаг 1: Редирект пользователя на страницу согласия Ozon"""
    client_id = settings.OZON_OAUTH_CLIENT_ID
    redirect_uri = settings.OZON_OAUTH_REDIRECT_URI
    
    # Формируем URL для авторизации
    auth_url = (
        f"https://api-seller.ozon.ru/v1/auth/authorize?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code"
    )
    return redirect(auth_url)

def ozon_oauth_callback(request):
    """Шаг 2: Ozon возвращает нас сюда с code, мы меняем его на токены"""
    code = request.GET.get('code')
    if not code:
        return HttpResponse("Ошибка: не получен код авторизации", status=400)

    # Обмениваем code на токены
    url = "https://api-seller.ozon.ru/v1/auth/token"
    payload = {
        "client_id": settings.OZON_OAUTH_CLIENT_ID,
        "client_secret": settings.OZON_OAUTH_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.OZON_OAUTH_REDIRECT_URI
    }

    response = requests.post(url, json=payload, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        
        # Сохраняем или обновляем запись в БД
        auth_record, created = OzonAuth.objects.update_or_create(
            is_active=True,
            defaults={
                'access_token': data['access_token'],
                'refresh_token': data.get('refresh_token', ''),
                'expires_at': timezone.now() + timedelta(seconds=data['expires_in'])
            }
        )
        return HttpResponse("✅ Авторизация Ozon Delivery прошла успешно! Теперь API будет работать.")
    else:
        return HttpResponse(f"❌ Ошибка получения токена: {response.text}", status=400)