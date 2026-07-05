from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, DetailView
from django.template.response import TemplateResponse
from django.db.models import Q
from .models import Category, Product, Size


class IndexView(TemplateView):
    template_name = 'main/base.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['current_category_slug'] = None
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        if request.headers.get('HX-Request'):
            return TemplateResponse(request, 'main/home_content.html', context)
        return TemplateResponse(request, self.template_name, context)


class CatalogView(TemplateView):
    template_name = 'main/base.html'

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

        # 1. Базовые запросы
        categories = Category.objects.all()
        products = Product.objects.all().order_by('-created_at')

        # 2. Фильтр по категории
        if category_slug:
            current_category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=current_category)

        # 🔑 3. Поиск и сброс (ПЕРЕД применением фильтров!)
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

        # 🔑 5. Убираем дубликаты после всех JOIN-ов
        products = products.distinct()

        # 6. Сборка контекста
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
            
            template = 'main/filter_modal.html' if request.GET.get('show_filters') == 'true' else 'main/catalog.html'
            return TemplateResponse(request, template, context)
            
        return TemplateResponse(request, self.template_name, context)


class ProductDetailView(DetailView):
    model = Product
    template_name = 'main/base.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        context['categories'] = Category.objects.all()
        
        # 🔑 Безопасная выборка похожих товаров
        if product.category:
            context['related_products'] = Product.objects.filter(
                category=product.category
            ).exclude(id=product.id)[:4]
        else:
            context['related_products'] = Product.objects.none()

        # 🔑 Единый ключ для шаблонов (строка)
        context['current_category_slug'] = product.category.slug if product.category else None
        
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(**kwargs)
        if request.headers.get('HX-Request'):
            return TemplateResponse(request, 'main/product_detail.html', context)
        return TemplateResponse(request, self.template_name, context)