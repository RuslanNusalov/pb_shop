import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

User = get_user_model()

# Данные для входа
ADMIN_EMAIL = 'spbpb@bk.ru'
ADMIN_PASSWORD = 'zipjyk-nudju6-cUffot'  # ← Запомни или измени!
FIRST_NAME = 'Alena'
LAST_NAME = 'Tikhonova'

if not User.objects.filter(email=ADMIN_EMAIL).exists():
    User.objects.create_superuser(
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        first_name=FIRST_NAME,
        last_name=LAST_NAME
    )
    print("✅ Суперпользователь успешно создан!")
else:
    print("🔄 Суперпользователь уже существует, пропускаем.")