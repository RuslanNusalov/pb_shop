import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.token = getattr(settings, 'APISHIP_API_KEY', '')
        self.base_url = "https://api.apiship.ru/v1"
        
        if not self.token:
            logger.error("❌ APISHIP_TOKEN не настроен!")
        else:
            logger.info(f"✅ ApiShip токен найден: {self.token[:10]}...")

    def _get_headers(self):
        return {
            "Authorization": self.token,  # БЕЗ "Bearer" — согласно документации!
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_pvz_list(self, city, service="ozonlog"):
        url = f"{self.base_url}/lists/points"
        filter_str = f"city={city};providerKey={service};availableOperation=[2,3]"
        
        params = {
            "limit": 100,
            "offset": 0,
            "filter": filter_str
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
        url = f"{self.base_url}/calculator"
        
        formatted_items = []
        for item in items:
            try:
                weight_kg = float(item.get("weight", 0.5))
                formatted_items.append({
                    "length": int(item.get("length", 20)),
                    "width": int(item.get("width", 15)),
                    "height": int(item.get("height", 10)),
                    "weight": int(weight_kg * 1000),
                    "quantity": int(item.get("quantity", 1))
                })
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка парсинга item: {e}")
                continue
        
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