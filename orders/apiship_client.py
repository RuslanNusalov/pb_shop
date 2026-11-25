import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.api_key = getattr(settings, 'APISHIP_API_KEY', '')
        self.base_url = "https://api.apiship.ru/v1"

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_pvz_list(self, city, service="ozonlog"):
        """Получает список ПВЗ для указанного города"""
        url = f"{self.base_url}/lists/points"
        # Фильтр: город, провайдер ozonlog, операции 2 (выдача) и 3 (прием и выдача)
        filter_str = f"city={city};providerKey={service};availableOperation=[2,3]"
        
        params = {
            "limit": 100,
            "offset": 0,
            "filter": filter_str
        }
        
        try:
            logger.info(f"📤 ApiShip запрос ПВЗ: {url} с фильтром {filter_str}")
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
        url = f"{self.base_url}/price"
        
        # ApiShip ожидает вес в граммах!
        formatted_items = []
        for item in items:
            formatted_items.append({
                "length": item.get("length", 20),
                "width": item.get("width", 15),
                "height": item.get("height", 10),
                "weight": int(item.get("weight", 500) * 1000), # переводим кг в граммы
                "quantity": item.get("quantity", 1)
            })
        
        payload = {
            "providerKey": service,
            "senderCity": sender_city,
            "receiverCity": receiver_city,
            "receiverPointId": str(receiver_point_id),
            "items": formatted_items
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