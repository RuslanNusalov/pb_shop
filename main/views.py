import logging

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views.generic import DetailView, TemplateView

from main.mixins import WishlistContextMixin

from .models import Banner, Category, Product, Size

logger = logging.getLogger(__name__)


class IndexView(WishlistContextMixin, TemplateView):
    template_name = 'main/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['banners'] = Banner.objects.filter(is_active=True)
        context['categories'] = Category.objects.all()
        context['current_category_slug'] = None
        # Оптимизация: сразу берем только нужные поля
        context['new_products'] = Product.objects.filter(is_active=True).order_by('-created_at')[:8]
        return context


class CatalogView(WishlistContextMixin, TemplateView):
    template_name = 'main/catalog.html'

    FILTER_MAPPING = {
        'color': lambda qs, val: qs.filter(color__iexact=val),
        'min_price': lambda qs, val: qs.filter(price__gte=val),
        'max_price': lambda qs, val: qs.filter(price__lte=val),
        'size': lambda qs, val: qs.filter(product_sizes__size__name=val),
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category_slug = kwargs.get('category_slug')
        current_category = None

        # 1. Базовые запросы (объединены и отсортированы)
        categories = Category.objects.all()
        # ✅ ИСПРАВЛЕНО: prefetch_related убран для wishlisted_by (так как связь теперь через Size)
        products = Product.objects.prefetch_related('category', 'product_sizes').all().order_by('-created_at')

        # 2. Фильтр по категории
        if category_slug:
            current_category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=current_category)

        # 3. Поиск и сброс
        is_reset = self.request.GET.get('reset_search') == 'true'
        query = '' if is_reset else self.request.GET.get('q', '').strip()

        if query:
            products = products.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )

        # 4. Остальные фильтры
        filter_params = {'q': query}
        for param, filter_func in self.FILTER_MAPPING.items():
            value = self.request.GET.get(param)
            if value:
                try:
                    products = filter_func(products, value)
                    filter_params[param] = value
                except (ValueError, TypeError):
                    filter_params[param] = ''
            else:
                filter_params[param] = ''

        # 5. Убираем дубликаты (обязательно после фильтрации по размерам)
        products = products.distinct()

        # ✅ 6. КОРРЕКТНАЯ ЛОГИКА WISHLIST ДЛЯ КАТАЛОГА
        # Нам нужно получить ID ТОВАРОВ (Product), у которых хотя бы один размер есть в избранном.
        # wishlist.products теперь содержит ProductSize, поэтому идем по связи product__id
        if self.request.user.is_authenticated:
            context['wishlist_ids'] = set(
                self.request.user.wishlist.products.values_list('product__id', flat=True)
            )
        else:
            context['wishlist_ids'] = set()

        # 7. Сборка контекста
        context.update({
            'categories': categories,
            'products': products,
            'current_category': current_category,
            'current_category_slug': current_category.slug if current_category else None,
            'filter_params': filter_params,
            'sizes': Size.objects.all(),
            'search_query': query,
            'show_search': self.request.GET.get('show_search') == 'true',
            'reset_search': is_reset,
        })

        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        
        if request.headers.get('HX-Request'):
            if context.get('show_search'):
                return TemplateResponse(request, 'main/search_input.html', context)
            if context.get('reset_search'):
                return TemplateResponse(request, 'main/search_button.html', {})
            
            template = 'main/partials/catalog_content.html'
            if request.GET.get('show_filters') == 'true':
                template = 'main/filter_modal.html'
            return TemplateResponse(request, template, context)
            
        return TemplateResponse(request, self.template_name, context)
        

class ProductDetailView(WishlistContextMixin, DetailView):
    model = Product
    template_name = 'main/product_detail.html'           
    partial_template_name = 'main/partials/product_detail_content.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        context['categories'] = Category.objects.all()
        context['current_category'] = product.category
        context['related_products'] = (
            Product.objects.filter(category=product.category)
            .exclude(id=product.id)[:4] 
            if product.category else Product.objects.none()
        )
        
        # ✅ КОРРЕКТНАЯ ЛОГИКА WISHLIST ДЛЯ ДЕТАЛЬНОЙ СТРАНИЦЫ
        # Здесь нам нужны ID РАЗМЕРОВ (ProductSize), чтобы подсветить конкретную кнопку размера.
        # wishlist.products.values_list('id') вернет именно ID ProductSize.
        if self.request.user.is_authenticated:
            context['wishlist_size_ids'] = set(
                self.request.user.wishlist.products.values_list('id', flat=True)
            )
            logger.debug(f"Wishlist size IDs: {context['wishlist_size_ids']}")
        else:
            context['wishlist_size_ids'] = set()
            
        return context

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        
        if request.headers.get('HX-Request') == 'true':
            response.template_name = self.partial_template_name
            
        return response
    
