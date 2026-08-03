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
    partial_template_name = 'main/partials/index_content.html'  # ← Фрагмент для HTMX

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['banners'] = Banner.objects.filter(is_active=True)
        context['categories'] = Category.objects.all()
        context['current_category_slug'] = None
        context['new_products'] = Product.objects.filter(is_active=True).order_by('-created_at')[:8]
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        # ✅ Если запрос от HTMX → отдаём только контент
        if request.headers.get('HX-Request'):
            return TemplateResponse(request, self.partial_template_name, context)
        # ✅ Иначе → полная страница
        return TemplateResponse(request, self.template_name, context)


class CatalogView(WishlistContextMixin, TemplateView):
    template_name = 'main/catalog.html'
    partial_template_name = 'main/partials/catalog_content.html'  # ← Фрагмент для HTMX

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

        categories = Category.objects.all()
        products = Product.objects.prefetch_related('category', 'product_sizes').all().order_by('-created_at')

        if category_slug:
            current_category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=current_category)

        is_reset = self.request.GET.get('reset_search') == 'true'
        query = '' if is_reset else self.request.GET.get('q', '').strip()

        if query:
            products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

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

        products = products.distinct()

        if self.request.user.is_authenticated:
            context['wishlist_ids'] = set(
                self.request.user.wishlist.products.values_list('product__id', flat=True)
            )
        else:
            context['wishlist_ids'] = set()

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
            if request.GET.get('show_filters') == 'true':
                return TemplateResponse(request, 'main/filter_modal.html', context)
            
            # ✅ Основной HTMX-ответ для каталога
            return TemplateResponse(request, self.partial_template_name, context)
            
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
        
        if self.request.user.is_authenticated:
            context['wishlist_size_ids'] = set(
                self.request.user.wishlist.products.values_list('id', flat=True)
            )
        else:
            context['wishlist_size_ids'] = set()
            
        return context

    def get(self, request, *args, **kwargs):
        # ✅ Сначала проверяем HTMX, чтобы не рендерить полную страницу зря
        if request.headers.get('HX-Request'):
            return TemplateResponse(request, self.partial_template_name, self.get_context_data())
        return super().get(request, *args, **kwargs)