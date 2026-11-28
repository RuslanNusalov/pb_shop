import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class ApiShipClient:
    def __init__(self):
        self.token = getattr(settings, 'APISHIP_TOKEN', '')
        self.base_url = "https://api.apiship.ru/v1"
        
        # Подробная диагностика
        if self.token:
            logger.info(f"✅ ApiShip токен найден: {self.token[:10]}... (длина: {len(self.token)})")
        else:
            logger.error(f"❌ APISHIP_TOKEN пуст! settings.APISHIP_TOKEN = '{getattr(settings, 'APISHIP_TOKEN', 'НЕ НАЙДЕНО')}'")
            # Попробуем прочитать напрямую из os.environ
            import os
            env_token = os.environ.get('APISHIP_TOKEN', '')
            logger.error(f"❌ os.environ APISHIP_TOKEN = '{env_token[:10] if env_token else 'ПУСТО'}...'")

    def _get_headers(self):
        return {
            "Authorization": self.token,  # БЕЗ "Bearer" — согласно документации!
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def get_pvz_list(self, city, service="ozonlog", limit=500, offset=0):
        url = f"{self.base_url}/lists/points"
        filter_str = f"city={city};providerKey={service};availableOperation=[2,3]"
        params = {"limit": limit, "offset": offset, "filter": filter_str}
        try:
            logger.info(f"📤 ApiShip ПВЗ: city={city}, offset={offset}")
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ ApiShip HTTP {e.response.status_code}: {e.response.text[:300]}")
            return {"error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"❌ ApiShip ошибка: {e}")
            return {"error": str(e)}

    def calculate_delivery(self, service, sender_city, receiver_city, receiver_point_id, items):
        url = f"{self.base_url}/calculator"

        # Собираем places и общий вес (в граммах)
        places = []
        total_weight = 0
        for item in items:
            try:
                weight_g = max(int(float(item.get("weight", 0.5)) * 1000), 1)
                qty = max(int(item.get("quantity", 1)), 1)
                length = max(int(item.get("length", 20)), 1)
                width = max(int(item.get("width", 15)), 1)
                height = max(int(item.get("height", 10)), 1)
            except (ValueError, TypeError):
                weight_g, qty, length, width, height = 500, 1, 20, 15, 10
            for _ in range(qty):
                places.append({"length": length, "width": width, "height": height, "weight": weight_g})
                total_weight += weight_g

        if not places:
            places = [{"length": 20, "width": 15, "height": 10, "weight": 500}]
            total_weight = 500

        payload = {
            "providerKey": service,
            "from": {"city": sender_city},
            "to": {"city": receiver_city, "pointId": int(receiver_point_id)},
            "weight": total_weight,
            "places": places,
        }

        try:
            logger.info(f"📤 ApiShip запрос расчёта: {payload}")
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=15)
            logger.info(f"📥 ApiShip ответ расчёта: {response.text[:1000]}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ ApiShip HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            logger.error(f"❌ ApiShip ошибка: {e}")
            return {"error": str(e)}

    def get_all_pvz(self, city, service="ozonlog", max_points=3000):
        """Тянет все ПВЗ города постранично (для локального поиска по улице)."""
        all_rows = []
        offset = 0
        page = 500

        while offset < max_points:
            data = self.get_pvz_list(city=city, service=service, limit=page, offset=offset)
            if 'error' in data:
                return data if not all_rows else {'rows': all_rows, 'meta': {'total': len(all_rows)}}

            rows = data.get('rows', [])
            all_rows.extend(rows)

            total = (data.get('meta') or {}).get('total', 0)
            offset += len(rows)
            if not rows or offset >= total:
                break

        return {'rows': all_rows, 'meta': {'total': len(all_rows)}}