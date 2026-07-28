import os
import django
from django.contrib.auth import get_user_model


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

User = get_user_model()

if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(
        username='admin_spbpb',
        email='spbpb@bk.ru',
        password='zipjyk-nudju6-cUffot'  # ← Смените пароль!
    )
    print("✅ Superuser created!")
