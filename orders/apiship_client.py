import logging
from datetime import datetime, timedelta

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.login = getattr(settings, 'APISHIP_LOGIN', '')
        self.password = getattr(settings, 'APISHIP_PASSWORD', '')
        self.base_url = "https://api.apiship.ru/v1"
        self.token = None
        self.token_expires = None
        
        # Диагностика
        if self.login and self.password:
            logger.info(f"✅ ApiShip логин найден: {self.login}")
        else:
            logger.error("❌ APISHIP_LOGIN или APISHIP_PASSWORD не найдены!")

    def _get_token(self):
        """Получает токен через авторизацию"""
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token
        
        try:
            response = requests.post(
                f"{self.base_url}/users/login",
                json={
                    "login": self.login,
                    "password": self.password
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            self.token = data.get('token')
            # Токен живёт 24 часа, обновляем за час до истечения
            self.token_expires = datetime.now() + timedelta(hours=23)
            
            logger.info(f"✅ Токен ApiShip получен")
            return self.token
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения токена: {e}")
            return None

    def _get_headers(self):
        token = self._get_token()
        if not token:
            raise Exception("Не удалось получить токен ApiShip")
        
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_pvz_list(self, city, service="ozonlog"):
        """Получает список ПВЗ"""
        url = f"{self.base_url}/lists/points"
        filter_str = f"city={city};providerKey={service};availableOperation=[2,3]"
        
        params = {
            "limit": 100,
            "offset": 0,
            "filter": filter_str
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
        """Рассчитывает стоимость доставки через /calculator"""
        url = f"{self.base_url}/calculator"
        
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