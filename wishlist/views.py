import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from main.models import ProductSize

from .models import Wishlist

logger = logging.getLogger(__name__)

class ToggleWishlistView(View):
    def get(self, request, size_id):
        product_size = get_object_or_404(ProductSize, id=size_id)
        return redirect('main:product_detail', slug=product_size.product.slug)

    # ✅ ИСПРАВЛЕНО: добавлен аргумент size_id
    def post(self, request, size_id):
        if not request.user.is_authenticated:
            if request.headers.get('HX-Request'):
                product_size = get_object_or_404(ProductSize, id=size_id)
                next_url = reverse('main:product_detail', kwargs={'slug': product_size.product.slug})
                response = HttpResponse()
                response['HX-Redirect'] = f'/users/login/?next={next_url}'
                return response
            return JsonResponse({'error': 'Требуется авторизация'}, status=401)

        product_size = get_object_or_404(ProductSize, id=size_id)
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

        if wishlist.products.filter(id=product_size.id).exists():
            wishlist.products.remove(product_size)
            is_in = False
        else:
            wishlist.products.add(product_size)
            is_in = True

        count = wishlist.products.count()

        if request.headers.get('HX-Request'):
            response = render(request, 'wishlist/partials/toggle_btn.html', {
                'product_size': product_size,
                'is_in_wishlist': is_in,
                'count': count
            })
            response['HX-Trigger'] = json.dumps({'wishlistUpdated': {'count': count}})
            return response

        return JsonResponse({'status': 'success', 'added': is_in, 'count': count})


# 2️⃣ LIST VIEW (Страница "Избранное")
@method_decorator(login_required, name='dispatch')  # ✅ КРИТИЧНО ВАЖНО: защита от анонимов
class WishlistListView(TemplateView):
    template_name = 'wishlist/wishlist_list.html'
    partial_template_name = 'wishlist/partials/wishlist_content.html'

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        
        # ✅ Логика разделения: Partial для HTMX, Full для обычного браузера
        if request.headers.get('HX-Request'):
            return render(request, self.partial_template_name, context)
            
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Безопасно, так как есть @login_required
        wishlist, _ = Wishlist.objects.get_or_create(user=self.request.user)
        
        # Оптимизация запросов
        products = wishlist.products.select_related(
            'product',           # сначала сам товар
            'product__category', # затем категория товара
            'size'               # и размер
        ).prefetch_related(
            'product__images'    # если нужны фото товара
        ).order_by('-wishlisted_by__updated_at')
        
        context['wishlist'] = wishlist
        context['products'] = products
        context['wishlist_count'] = products.count()
        
        return context


class GetWishlistToggleBtn(View):
    """Возвращает HTML кнопки избранного для конкретного РАЗМЕРА"""
    def get(self, request, product_id, size_id):
        product_size = get_object_or_404(ProductSize, id=size_id)

        wishlist = None

        # ✅ ПРАВИЛЬНАЯ ПРОВЕРКА: ищем именно ProductSize в избранном
        is_in = False
        if request.user.is_authenticated:
            wishlist = getattr(request.user, 'wishlist', None)
            if wishlist:
                # ✅ Проверяем, есть ли КОНКРЕТНЫЙ размер (product_size) в избранном
                is_in = wishlist.products.filter(id=product_size.id).exists()
                logger.info(f"🔍 Checking: product_size.id={product_size.id}")
                logger.info(f"📦 User wishlist contains: {list(wishlist.products.values_list('id', flat=True))}")
                logger.info(f"✅ Result: is_in={is_in}")

        return render(request, 'wishlist/partials/toggle_btn.html', {
            'product_size': product_size,  # ← передаём размер, а не товар
            'is_in_wishlist': is_in,
            'count': wishlist.products.count() if wishlist else 0
        })
