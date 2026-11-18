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
    """Шаг 2: Обмен code на токены"""
    try:
        code = request.GET.get('code')
        returned_state = request.GET.get('state')
        saved_state = request.session.get('ozon_oauth_state')
        
        if not code:
            return HttpResponse(f"❌ Нет code. Параметры: {request.GET.dict()}", status=400)
        
        if returned_state != saved_state:
            return HttpResponse(
                f"❌ Ошибка state.<br>Получен: {returned_state}<br>Ожидался: {saved_state}", 
                status=403
            )
            
        if 'ozon_oauth_state' in request.session:
            del request.session['ozon_oauth_state']

        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.OZON_OAUTH_CLIENT_ID,
            "client_secret": settings.OZON_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.OZON_OAUTH_REDIRECT_URI
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; PBShopBot/1.0)"
        }

        response = requests.post(OZON_TOKEN_URL, data=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
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
                f"<p>Токен: {data['access_token'][:30]}...</p>"
            )
        else:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            return HttpResponse(
                f"❌ Ozon вернул ошибку:<br>"
                f"Status: {response.status_code}<br>"
                f"Body: <pre>{response.text}</pre>", 
                status=400
            )
    except Exception as e:
        # 🔥 Показываем реальную причину 500 прямо в браузере
        import traceback
        tb = traceback.format_exc()
        logger.error(f"CRITICAL ERROR in callback: {tb}")
        return HttpResponse(
            f"<h1>❌ Внутренняя ошибка</h1>"
            f"<pre>{tb}</pre>",
            status=500
        )