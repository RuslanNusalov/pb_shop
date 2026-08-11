from main.models import Category


def global_wishlist_count(request):
    """Добавляет счётчик избранного в контекст ВСЕХ шаблонов"""
    count = 0
    
    if request.user.is_authenticated:
        # ВАРИАНТ 1: Если у тебя связь ManyToMany напрямую в User
        # count = request.user.wishlist.count() 
        
        # ВАРИАНТ 2: Если есть отдельная модель Wishlist (как у тебя скорее всего)
        try:
            # Замени 'wishlist' на название твоего приложения, если другое
            # И 'products' на название поля связи
            wishlist = request.user.wishlist 
            count = wishlist.products.count()
        except:
            count = 0
            
    return {'wishlist_count': count}


def global_categories(request):
    return {
        'categories': Category.objects.all(),
    }
