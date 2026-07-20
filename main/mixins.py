class WishlistContextMixin:
    """Автоматически добавляет wishlist_count в контекст"""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.request.user.is_authenticated:
            wishlist = getattr(self.request.user, 'wishlist', None)
            # ✅ Считаем количество товаров через оптимизированный COUNT(*)
            context['wishlist_count'] = wishlist.products.count() if wishlist else 0
        else:
            context['wishlist_count'] = 0
            
        return context