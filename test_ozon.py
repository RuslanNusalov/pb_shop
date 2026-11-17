import os
import django

# Настраиваем окружение Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

import requests
from django.conf import settings

client_id = getattr(settings, 'OZON_OAUTH_CLIENT_ID', '')
client_secret = getattr(settings, 'OZON_OAUTH_CLIENT_SECRET', '')
redirect_uri = getattr(settings, 'OZON_OAUTH_REDIRECT_URI', '')

# ВАЖНО: Вставьте сюда СВЕЖИЙ код из URL после нажатия "Разрешить" в Ozon!
# Старый код уже не работает (живет 5-10 минут).
code="c29b4eee-25e5-4a28-9543-f6900433195f&state=isE-PTlq4IWhwxWEc-6dyg"

payload = {
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "redirect_uri": redirect_uri
}

print("=" * 60)
print(f"Client ID: {client_id}")
print(f"Code: {code[:20]}...")
print("=" * 60)

# Ozon часто требует form-urlencoded, а не json для oauth/token
urls_to_try = [
    "https://api-seller.ozon.ru/v1/oauth/token",
    "https://api-seller.ozon.ru/v2/auth/token",
    "https://api-seller.ozon.ru/oauth/token",
]

for url in urls_to_try:
    print(f"\n[TEST] {url}")
    
    # Тест 1: Отправка как JSON (как было раньше)
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"  JSON  -> {r.status_code} | {r.text[:150]}")
    except Exception as e:
        print(f"  JSON  -> ERROR: {e}")
    
    # Тест 2: Отправка как Form Data (стандарт OAuth 2.0, часто требуется Ozon)
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        r = requests.post(url, data=payload, headers=headers, timeout=10)
        print(f"  FORM  -> {r.status_code} | {r.text[:150]}")
    except Exception as e:
        print(f"  FORM  -> ERROR: {e}")

print("\n" + "=" * 60)
print("ГОТОВО. Найдите строку со статусом 200 или 400 (invalid_grant).")
print("=" * 60)