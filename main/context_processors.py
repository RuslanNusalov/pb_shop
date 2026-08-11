from django.core.cache import cache

from main.models import Category
from wishlist.models import Wishlist


def global_wishlist_count(request):
    """Добавляет счётчик избранного в контекст ВСЕХ шаблонов"""
    count = 0
    
    if request.user.is_authenticated:
        try:
            wishlist = request.user.wishlist
            count = wishlist.products.count()
        except (AttributeError, Wishlist.DoesNotExist):
            count = 0
        except Exception:
            count = 0
            
    return {'wishlist_count': count}


def global_categories(request):
    """Возвращает активные категории с кэшированием"""
    
    # Пробуем получить из кэша
    categories = cache.get('global_categories')
    
    if categories is None:
        # ✅ Используем фильтр is_active=True (поле уже есть в БД)
        categories = list(Category.objects.filter(
            is_active=True
        ).values('id', 'name', 'slug').order_by('name'))
        
        # Кэшируем на 1 час
        cache.set('global_categories', categories, 3600)
    
    return {'categories': categories}