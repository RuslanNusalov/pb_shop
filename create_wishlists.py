import os

import django
from django.contrib.auth import get_user_model

from wishlist.models import Wishlist

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pb_shop.settings')
django.setup()

User = get_user_model()

# Создаём Wishlist для всех пользователей, у которых его нет
users_without_wishlist = User.objects.filter(wishlist__isnull=True)
count = users_without_wishlist.count()

for user in users_without_wishlist:
    Wishlist.objects.create(user=user)
    print(f"✅ Created wishlist for {user.email}")

print(f"\n Total wishlists created: {count}")