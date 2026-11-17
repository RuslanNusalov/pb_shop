import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .models import OzonAuth

logger = logging.getLogger(__name__)

class OzonDeliveryClient:
    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self):
        self.client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
        self.redirect_uri = getattr(settings, 'OZON_OAUTH_REDIRECT_URI', '')

    def _get_active_token(self):
        """Получает валидный access_token, при необходимости обновляя его"""
        auth_record = OzonAuth.objects.filter(is_active=True).first()
        
        if not auth_record:
            raise Exception("Ozon OAuth не выполнен. Перейдите в админку или по ссылке /ozon/oauth/login/")
        
        # Если токен истекает менее чем через 5 минут, обновляем его
        if auth_record.expires_at < timezone.now() + timedelta(minutes=5):
            self._refresh_token(auth_record)
            # Перечитываем запись после обновления
            auth_record = OzonAuth.objects.filter(is_active=True).first()
            
        return auth_record.access_token

    def _refresh_token(self, auth_record):
        """Обновляет access_token с помощью refresh_token"""
        url = f"{self.BASE_URL}/v1/auth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": auth_record.refresh_token
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            auth_record.access_token = data['access_token']
            auth_record.refresh_token = data.get('refresh_token', auth_record.refresh_token)
            auth_record.expires_at = timezone.now() + timedelta(seconds=data['expires_in'])
            auth_record.save()
        else:
            logger.error(f"Ошибка обновления токена Ozon: {response.text}")
            raise Exception("Не удалось обновить токен Ozon. Требуется повторная авторизация.")

    def _get_headers(self):
        """Возвращает заголовки с Bearer токеном"""
        token = self._get_active_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _make_request(self, endpoint: str, payload: dict):
        url = f"{self.BASE_URL}{endpoint}"
        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"🚨 Ошибка запроса к Ozon API ({endpoint}): {e}")
            return {"error": str(e), "result": False}
        except ValueError:
            return {"error": "Invalid JSON response", "result": False}

    # =========================================================================
    # 🟢 МЕТОДЫ OZON DELIVERY (теперь работают через OAuth!)
    # =========================================================================

    def check_delivery(self, phone: str):
        clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        return self._make_request('/v1/delivery/check', {"phone": clean_phone})

    def get_pvz_list(self, city_code: str):
        return self._make_request('/v1/delivery/point/list', {"city_code": city_code})

    def calculate_checkout(self, items: list, delivery_method: dict, phone: str, city_code: str):
        payload = {
            "items": items,
            "delivery_method": delivery_method,
            "customer": {
                "phone": phone.replace('+', '').replace(' ', '').replace('-', ''),
                "city_code": city_code
            }
        }
        return self._make_request('/v2/delivery/checkout', payload)

    def create_order(self, order_data: dict):
        return self._make_request('/v2/order/create', order_data)