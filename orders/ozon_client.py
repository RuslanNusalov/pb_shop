import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .models import OzonAuth

logger = logging.getLogger(__name__)


class OzonDeliveryClient:
    def __init__(self):
        # Для справочных методов (point/list, point/info) — Api-Key
        self.client_id = str(getattr(settings, 'OZON_CLIENT_ID', '')).strip()
        self.api_key = str(getattr(settings, 'OZON_API_KEY', '')).strip()
        # Для методов доставки (map, checkout, create) — OAuth
        self.oauth_client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
        self.oauth_client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
        self.base_url = "https://api-seller.ozon.ru"

    def _headers_api_key(self):
        """Заголовки для методов с Api-Key авторизацией"""
        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _headers_oauth(self):
        """Заголовки для методов с OAuth Bearer токеном"""
        return {
            "Authorization": f"Bearer {self._get_active_token()}",
            "Content-Type": "application/json",
        }

    def _get_active_token(self):
        """Получает активный OAuth токен, обновляет если истекает"""
        auth_record = OzonAuth.objects.filter(is_active=True).first()
        if not auth_record:
            raise RuntimeError("Ozon OAuth не выполнен. Пройдите /orders/ozon/oauth/login/")
        if auth_record.expires_at < timezone.now() + timedelta(minutes=5):
            self._refresh_token(auth_record)
            auth_record = OzonAuth.objects.filter(is_active=True).first()
        return auth_record.access_token

    def _refresh_token(self, auth_record):
        """Обновляет OAuth токен через refresh_token"""
        url = "https://xapi.ozon.ru/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; PBShopBot/1.0)",
        }
        payload = {
            "client_id": self.oauth_client_id,
            "client_secret": self.oauth_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": auth_record.refresh_token,
        }
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            auth_record.access_token = data['access_token']
            auth_record.refresh_token = data.get('refresh_token', auth_record.refresh_token)
            auth_record.expires_at = timezone.now() + timedelta(seconds=int(data.get('expires_in', 3600)))
            auth_record.save()
        else:
            raise RuntimeError(f"Не удалось обновить токен Ozon: {response.text}")

    def _make_request(self, path, payload, auth='oauth'):
        headers = self._headers_oauth() if auth == 'oauth' else self._headers_api_key()
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # ← ГЛАВНОЕ: читаем тело ошибки, которое Ozon теперь возвращает подробно
            try:
                body = e.response.text[:500]
            except Exception:
                body = ""
            logger.error(f"Ozon API {path} -> HTTP {e.response.status_code}: {body}")
            return {"error": f"HTTP {e.response.status_code}. Ozon: {body}"}
        except Exception as e:
            logger.error(f"Ozon API {path} -> {e}")
            return {"error": str(e)}

    @staticmethod
    def _normalize_phone(phone):
        """Нормализует телефон к формату +7XXXXXXXXXX"""
        digits = ''.join(c for c in str(phone) if c.isdigit())
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        if not digits.startswith('7') and len(digits) == 10:
            digits = '7' + digits
        if len(digits) >= 11 and digits.startswith('7'):
            return '+' + digits
        return "+7" + digits

    # ==========================================
    # МЕТОДЫ ДЛЯ РАБОТЫ С ПВЗ
    # ==========================================

    def get_pvz_clusters(self, viewport, zoom=10):
            """
            Получает кластеры точек самовывоза по viewport карты.
            Авторизация: OAuth Bearer токен
            """
            return self._make_request(
                '/v1/delivery/map',
                {"viewport": viewport, "zoom": zoom},
                auth='oauth'
            )
    
    def get_pvz_info(self, map_point_ids):
        return self._make_request(
            '/v1/delivery/point/info',
            {"map_point_ids": [str(pid) for pid in map_point_ids]},
            auth='oauth'  # ← ДОЛЖНО БЫТЬ oauth, НЕ api_key
        )

    def get_all_pvz_points(self):
        return self._make_request('/v1/delivery/point/list', {}, auth='oauth')


    # ==========================================
    # МЕТОДЫ ДЛЯ РАСЧЁТА ДОСТАВКИ
    # ==========================================

    def check_delivery(self, phone):
        """
        Проверяет доступность доставки по телефону.
        Авторизация: OAuth
        """
        return self._make_request(
            '/v1/delivery/check',
            {"phone": self._normalize_phone(phone)},
            auth='oauth'
        )

    def calculate_checkout(self, items, map_point_id, phone, warehouse_id, delivery_schema="MIX"):
        """
        Рассчитывает стоимость доставки через Ozon.
        """
        payload = {
            "items": items,
            "warehouse_id": int(warehouse_id),
            "delivery_schema": delivery_schema,
            "delivery_type": 3,  # ✅ число (3 = ПВЗ/Постамат),  # ← ДОБАВИТЬ: тип доставки (PVZ = пункт выдачи)
            "customer": {
                "phone": str(phone)
            },
            "map_point_id": int(map_point_id)
        }
        
        logger.info(f"📤 Ozon checkout payload: {payload}")
        return self._make_request('/v2/delivery/checkout', payload, auth='oauth')

    # ==========================================
    # МЕТОДЫ ДЛЯ СОЗДАНИЯ ЗАКАЗА
    # ==========================================

    def create_order(self, order_data):
        """
        Создаёт заказ в Ozon.
        Авторизация: OAuth
        """
        return self._make_request('/v2/order/create', order_data, auth='oauth')