# import json
# import logging
# from datetime import timedelta

# import requests
# from django.conf import settings
# from django.utils import timezone

# from .models import OzonAuth

# logger = logging.getLogger(__name__)


# class OzonDeliveryClient:
#     def __init__(self):
#         self.client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
#         self.client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
#         self.base_url = "https://api-seller.ozon.ru"
#         self.token_url = "https://api-seller.ozon.ru/appstore-api/oauth/token"
    
#     def _get_active_token(self):
#         """
#         Возвращает активный access_token.
#         Если токен истекает через < 5 минут — обновляет его.
#         """
#         auth_record = OzonAuth.objects.filter(is_active=True).first()
        
#         if not auth_record:
#             raise Exception("Нет активного OAuth-токена. Пройдите авторизацию.")
        
#         # Проверяем, не истекает ли токен в ближайшие 5 минут
#         time_until_expiry = auth_record.expires_at - timezone.now()
        
#         if time_until_expiry < timedelta(minutes=5):
#             logger.info(f"⏰ Токен истекает через {time_until_expiry}. Обновляем...")
#             return self._refresh_token(auth_record)
        
#         return auth_record.access_token
    
#     def _refresh_token(self, auth_record):
#         """
#         Обновляет access_token через refresh_token.
#         """
#         if not auth_record.refresh_token:
#             logger.error("❌ Нет refresh_token. Требуется повторная авторизация.")
#             raise Exception("Нет refresh_token. Пройдите авторизацию заново.")
        
#         try:
#             response = requests.post(
#                 self.token_url,
#                 data={
#                     "grant_type": "refresh_token",
#                     "client_id": self.client_id,
#                     "client_secret": self.client_secret,
#                     "refresh_token": auth_record.refresh_token,
#                 },
#                 headers={"Content-Type": "application/x-www-form-urlencoded"},
#                 timeout=10
#             )
            
#             if response.status_code != 200:
#                 logger.error(f"❌ Ошибка обновления токена: {response.status_code} {response.text}")
#                 raise Exception(f"Ошибка обновления токена: {response.status_code}")
            
#             data = response.json()
            
#             # Обновляем запись в БД
#             auth_record.access_token = data['access_token']
#             auth_record.refresh_token = data['refresh_token']  # Ozon возвращает новый refresh_token
#             auth_record.expires_at = timezone.now() + timedelta(hours=1)  # access_token живёт 1 час
#             auth_record.save()
            
#             logger.info(f"✅ Токен успешно обновлён. Новый expires_at: {auth_record.expires_at}")
#             return data['access_token']
            
#         except requests.exceptions.RequestException as e:
#             logger.error(f"❌ Ошибка запроса при обновлении токена: {e}")
#             raise Exception(f"Ошибка сети при обновлении токена: {e}")
    
#     def _headers_oauth(self):
#         token = self._get_active_token()
#         return {
#             "Authorization": f"Bearer {token}",
#             "Content-Type": "application/json",
#         }
    
#     def _make_request(self, path, payload, auth='oauth'):
#         headers = self._headers_oauth() if auth == 'oauth' else self._headers_api_key()
#         url = f"{self.base_url}{path}"
        
#         try:
#             response = requests.post(url, json=payload, headers=headers, timeout=30)
            
#             # Если 401 — пробуем обновить токен и повторить запрос
#             if response.status_code == 401 and auth == 'oauth':
#                 logger.warning("⚠️ Получен 401. Пробуем обновить токен...")
#                 auth_record = OzonAuth.objects.filter(is_active=True).first()
#                 if auth_record:
#                     self._refresh_token(auth_record)
#                     # Повторяем запрос с новым токеном
#                     headers = self._headers_oauth()
#                     response = requests.post(url, json=payload, headers=headers, timeout=30)
            
#             response.raise_for_status()
#             return response.json()
            
#         except requests.exceptions.HTTPError as e:
#             try:
#                 body = e.response.text[:500]
#             except Exception:
#                 body = ""
#             logger.error(f"Ozon API {path} -> HTTP {e.response.status_code}: {body}")
#             return {"error": f"HTTP {e.response.status_code}. Ozon: {body}"}
#         except Exception as e:
#             logger.error(f"Ozon API {path} -> {e}")
#             return {"error": str(e)}
    
#     def get_pvz_clusters(self, viewport, zoom=10):
#         payload = {
#             "viewport": viewport,
#             "zoom": zoom
#         }
#         return self._make_request('/v1/delivery/map', payload, auth='oauth')
    
#     def get_pvz_info(self, map_point_ids):
#         payload = {
#             "map_point_ids": [int(pid) for pid in map_point_ids]
#         }
#         return self._make_request('/v1/delivery/point/info', payload, auth='oauth')
    
#     def calculate_checkout(self, items, map_point_id, phone, warehouse_id,
#                            delivery_schema="MIX", delivery_type="pick_up"):
#         payload = {
#             "buyer_phone": str(phone),
#             "delivery_schema": delivery_schema,
#             "delivery_type": {
#                 delivery_type: {
#                     "map_point_id": int(map_point_id) if delivery_type == "pick_up"
#                     else {"coordinates": {"latitude": 0, "longitude": 0}}
#                 }
#             },
#             "items": items,
#             "warehouse_id": int(warehouse_id),
#         }
        
#         logger.info(f"📤 Ozon checkout payload: {json.dumps(payload, ensure_ascii=False)}")
#         return self._make_request('/v2/delivery/checkout', payload, auth='oauth')