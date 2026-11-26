import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.api_key = getattr(settings, 'APISHIP_API_KEY', '')
        self.account_id = getattr(settings, 'APISHIP_ACCOUNT_ID', '')
        self.base_url = "https://api.apiship.ru/v1"
        
        # Диагностика
        if self.api_key:
            logger.info(f"✅ ApiShip ключ найден: {self.api_key[:20]}...")
        else:
            logger.error("❌ APISHIP_API_KEY не найден!")
        
        if self.account_id:
            logger.info(f"✅ ApiShip Account ID: {self.account_id}")
        else:
            logger.warning("⚠️ APISHIP_ACCOUNT_ID не найден")

    def _get_headers(self):
        return {
            "Authorization": self.api_key,  # ← Убрали "Bearer " (попробуйте оба варианта)
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
            # accountId убран для GET-запроса
        }
        
        try:
            logger.info(f"📤 ApiShip запрос ПВЗ: {url}")
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
        url = f"{self.base_url}/price"
        
        formatted_items = []
        for item in items:
            try:
                weight_kg = float(item.get("weight", 0.5))
                formatted_items.append({
                    "length": int(item.get("length", 20)),
                    "width": int(item.get("width", 15)),
                    "height": int(item.get("height", 10)),
                    "weight": int(weight_kg * 1000),  # кг → граммы
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
            "accountId": int(self.account_id) if self.account_id else None,
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