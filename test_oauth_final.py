import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

import requests
from django.conf import settings

client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
redirect_uri = getattr(settings, 'OZON_OAUTH_REDIRECT_URI', '')

# ВСТАВЬТЕ СЮДА СВЕЖИЙ КОД ИЗ БРАУЗЕРА
code = "8eabc56c-3914-4a71-bcd7-c0e21e82b6c8&state=FAnBLjO50PWMl5E4EdzeFg"

# OAuth 2.0 ТРЕБУЕТ form-urlencoded, а не json!
payload = {
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "redirect_uri": redirect_uri
}

headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (compatible; PBShopBot/1.0)"
}

# Проверяем все возможные варианты URL
urls_to_test = [
    "https://api-seller.ozon.ru/v1/oauth/token",
    "https://api-seller.ozon.ru/v2/auth/token",
    "https://xapi.ozon.ru/oauth/token"
]

print("=" * 70)
print(f"Тестируем код: {code[:20]}...")
print("=" * 70)

for url in urls_to_test:
    print(f"\n[TEST] {url}")
    try:
        # ВАЖНО: используем data=, а не json=
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ  : {response.text}")
    except Exception as e:
        print(f"Ошибка сети: {e}")

print("\n" + "=" * 70)
print("Ищите статус 200 (успех) или 400 с текстом 'invalid_grant' (значит URL верный, но код протух).")
print("=" * 70)