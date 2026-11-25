import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.api_key = getattr(settings, 'APISHIP_API_KEY', '')
        self.account_id = getattr(settings, 'APISHIP_ACCOUNT_ID', '')
        self.base_url = "https://api.apiship.ru/v1"

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_pvz_list(self, city, service="ozonlog"):
        """Получает список ПВЗ для указанного города"""
        url = f"{self.base_url}/points"
        params = {
            "service": service,
            "city": city,
            "account_id": self.account_id
        }
        try:
            logger.info(f"📤 ApiShip запрос ПВЗ: city={city}, service={service}")
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ ApiShip HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"❌ ApiShip ошибка: {e}")
            return {"error": str(e)}

    def calculate_delivery(self, service, sender_city, receiver_city, receiver_point_id, items):
        """Рассчитывает стоимость доставки"""
        url = f"{self.base_url}/calculator"
        payload = {
            "service": service,
            "sender_city": sender_city,
            "receiver_city": receiver_city,
            "receiver_point_id": str(receiver_point_id),
            "items": items  # [{"length": 20, "width": 15, "height": 5, "weight": 0.5, "quantity": 1}]
        }
        try:
            logger.info(f"📤 ApiShip запрос расчёта: {payload}")
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ ApiShip HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"❌ ApiShip ошибка: {e}")
            return {"error": str(e)}