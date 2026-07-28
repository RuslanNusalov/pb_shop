# fix_admin_user.py
import os
import django
from django.contrib.auth import get_user_model


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

User = get_user_model()

# Данные для входа (запомните их!)
USERNAME = 'admin'
EMAIL = 'spbpb@bk.ru'
PASSWORD = 'zipjyk-nudju6-cUffot'  # ← Замените на свой сложный пароль

# Создаём или обновляем пользователя
user, created = User.objects.update_or_create(
    username=USERNAME,
    defaults={
        'email': EMAIL,
        'is_staff': True,
        'is_superuser': True,
    }
)
user.set_password(PASSWORD)
user.save()

print(f"✅ Пользователь '{USERNAME}' готов к входу!")