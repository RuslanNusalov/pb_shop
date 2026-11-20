import logging
import time
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib import messages  # ✅ ДОБАВЛЕНО
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpResponse
from django.shortcuts import (  # ✅ ДОБАВЛЕНО get_object_or_404
    get_object_or_404,
    redirect,
    render,
)
from django.template.response import TemplateResponse
from django.urls import reverse_lazy  # ✅ ДОБАВЛЕНО reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.views.generic import DetailView, View

from cart.models import PromoCode
from cart.views import CartMixin
from main.mixins import WishlistContextMixin
from main.models import ProductSize

from .forms import OrderForm
from .models import Order, OrderItem, OzonPVZ
from .ozon_client import OzonDeliveryClient

logger = logging.getLogger(__name__)

OZON_TEST_WAREHOUSE_ID = getattr(settings, 'OZON_TEST_WAREHOUSE_ID', '')
OZON_TEST_OFFER_ID = getattr(settings, 'OZON_TEST_OFFER_ID', '')


@method_decorator(login_required(login_url=reverse_lazy('users:login')), name='dispatch') # ✅ Используем reverse_lazy
class CheckoutView(WishlistContextMixin, CartMixin, View):
    def _checkout_context(self, form, cart, error_message=None):
        return {
            'form': form,
            'cart': cart,
            'cart_items': cart.items.select_related('product', 'product_size__size').order_by('-added_at'),
            'subtotal': cart.subtotal,
            'total': cart.total,
            'error_message': error_message,
        }

    def get(self, request):
        cart = self.get_cart(request)

        total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
        if total_items == 0:
            if request.headers.get('HX-Request'):
                return TemplateResponse(request, 'orders/empty_cart.html', {'message': 'Корзина пуста'})
            return redirect('cart:cart_modal')

        form = OrderForm(user=request.user)
        context = self._checkout_context(form, cart)

        if request.headers.get('HX-Request'):
            return TemplateResponse(request, 'orders/checkout_content.html', context)
        return render(request, 'orders/checkout.html', context)

    def post(self, request):
        cart = self.get_cart(request)

        total_items = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
        if total_items == 0:
            return redirect('cart:cart_modal')

        form_data = request.POST.copy()
        if not form_data.get('email') and request.user.is_authenticated:
            form_data['email'] = request.user.email

        form = OrderForm(form_data, user=request.user)

        if not form.is_valid():
            logger.warning(f"Checkout form errors: {form.errors}")
            context = self._checkout_context(
                form, cart, error_message='Пожалуйста, исправьте ошибки в форме.'
            )
            # ✅ Если HTMX — возвращаем частичный шаблон, иначе полную страницу
            if request.headers.get('HX-Request'):
                return TemplateResponse(request, 'orders/checkout_content.html', context)
            return render(request, 'orders/checkout.html', context)

        cart_items = list(cart.items.select_related('product', 'product_size'))

        try:
            with transaction.atomic():
                for item in cart_items:
                    product_size = ProductSize.objects.select_for_update().get(pk=item.product_size_id)
                    if product_size.stock < item.quantity:
                        raise ValidationError(
                            f'Недостаточно товара «{item.product.name}» '
                            f'(размер {product_size.size.name}): доступно {product_size.stock} шт.'
                        )

                subtotal = cart.subtotal
                discount = cart.promo_discount
                total = subtotal - discount

                order = Order.objects.create(
                    user=request.user,
                    cart=cart,
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=form.cleaned_data['email'],
                    address=form.cleaned_data.get('address', ''),
                    city=form.cleaned_data.get('city', ''),
                    region=form.cleaned_data.get('region', ''),
                    postal_code=form.cleaned_data.get('postal_code', ''),
                    phone=form.cleaned_data.get('phone', ''),
                    special_instructions=form.cleaned_data.get('special_instructions', ''),
                    status='pending',
                    subtotal=subtotal,
                    promo_discount=discount,
                    promo_code=cart.promo_code,
                    total=total,
                )

                for item in cart_items:
                    ProductSize.objects.filter(pk=item.product_size_id).update(
                        stock=F('stock') - item.quantity
                    )
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        product_size=item.product_size,
                        quantity=item.quantity,
                        price=item.product.price or Decimal('0.00'),
                    )

                if cart.promo_code_id:
                    PromoCode.objects.filter(pk=cart.promo_code_id).update(
                        usage_count=F('usage_count') + 1
                    )

                cart.items.all().delete()
                cart.promo_code = None
                cart.promo_discount = Decimal('0.00')
                cart.save(update_fields=['promo_code', 'promo_discount'])

        except ValidationError as e:
            context = self._checkout_context(form, cart, error_message=str(e))
            if request.headers.get('HX-Request'):
                return TemplateResponse(request, 'orders/checkout_content.html', context)
            return render(request, 'orders/checkout.html', context)

        return redirect('payment:payment_instructions', order_id=order.pk)


class OrderDetailView(WishlistContextMixin, LoginRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_id'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).select_related('user', 'promo_code')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related('product', 'product_size__size')
        return context


@login_required(login_url=reverse_lazy('users:login'))
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'orders/partials/order_history_content.html', {'orders': orders})
    
    return render(request, 'orders/order_history.html', {'orders': orders})



@login_required(login_url=reverse_lazy('users:login'))
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == 'pending':
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Заказ №{order.id} успешно отменён')
    else:
        messages.error(request, 'Этот заказ нельзя отменить')
    
    return redirect('orders:order_detail', order_id=order.id)

@require_GET
def ozon_pvz_list(request):
    """Список ПВЗ для города: кэш → Ozon API через /v1/delivery/map"""
    city = request.GET.get('ozon_city', '').strip()
    
    if not city or len(city) < 2:
        return HttpResponse("<p class='text-gray-500 text-sm text-center py-4'>Введите название города (мин. 2 символа)</p>")
    
    # 1. Проверяем локальный кэш
    cached_pvz = OzonPVZ.objects.filter(
        city__icontains=city,
        enabled=True
    ).order_by('name')[:50]
    
    if cached_pvz.exists():
        return render(request, 'orders/partials/ozon_pvz_list.html', {
            'pvz_list': cached_pvz,
            'from_cache': True
        })
    
    # 2. Кэша нет — получаем координаты города через Nominatim (бесплатно)
    try:
        geo_response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"format": "json", "q": city, "limit": 1},
            headers={"User-Agent": "PBShopBot/1.0 (spbpb.ru)"},
            timeout=10
        )
        geo_data = geo_response.json()
        if not geo_data:
            return HttpResponse(f"<p class='text-red-500 text-sm text-center py-4'>Город '{city}' не найден</p>")
        
        lat = float(geo_data[0]['lat'])
        lon = float(geo_data[0]['lon'])
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"Ошибка геокодинга: {e}")
        return HttpResponse("<p class='text-red-500 text-sm text-center py-4'>Ошибка определения координат</p>")
    
    # 3. Формируем viewport (~50 км вокруг центра города)
    delta = 0.45
    viewport = {
        "left_bottom": {"lat": lat - delta, "long": lon - delta},
        "right_top": {"lat": lat + delta, "long": lon + delta}
    }
    
    # 4. Получаем кластеры точек через /v1/delivery/map (требует OAuth!)
    client = OzonDeliveryClient()
    clusters_response = client.get_pvz_clusters(viewport, zoom=10)
    
    if 'error' in clusters_response:
        return HttpResponse(
            f"<p class='text-red-500 text-sm text-center py-4'>Ошибка загрузки ПВЗ: {clusters_response['error']}</p>"
        )
    
    clusters = clusters_response.get('clusters', [])
    
    # 5. Собираем все map_point_ids из кластеров
    all_point_ids = []
    for cluster in clusters:
        all_point_ids.extend([str(pid) for pid in cluster.get('map_point_ids', [])])
    
    if not all_point_ids:
        return HttpResponse(f"<p class='text-gray-500 text-sm text-center py-4'>ПВЗ не найдены в радиусе 50 км от '{city}'</p>")
    
    # Ограничиваем до 200 точек для скорости
    all_point_ids = all_point_ids[:200]
    
    # 6. Получаем детали точек пачками по 100 (требует Api-Key)
    all_details = []
    for i in range(0, len(all_point_ids), 100):
        batch = all_point_ids[i:i+100]
        info_response = client.get_pvz_info(batch)
        if 'error' not in info_response:
            all_details.extend(info_response.get('points', []))
        if i + 100 < len(all_point_ids):
            time.sleep(0.2)  # Пауза, чтобы не превысить лимиты API
    
    # 7. Сохраняем полученные точки в наш кэш
    for point_data in all_details:
        dm = point_data.get('delivery_method', {})
        addr = dm.get('address_details', {})
        coord = dm.get('coordinates', {})
        
        OzonPVZ.objects.update_or_create(
            map_point_id=point_data.get('map_point_id'),
            defaults={
                'name': dm.get('name', ''),
                'address': dm.get('address', ''),
                'city': addr.get('city', city),
                'region': addr.get('region', ''),
                'lat': coord.get('lat'),
                'lng': coord.get('long'),
                'enabled': point_data.get('enabled', True),
                'working_hours': dm.get('working_hours'),
            }
        )
    
    # 8. Возвращаем свежие данные из кэша
    fresh_pvz = OzonPVZ.objects.filter(
        city__icontains=city,
        enabled=True
    ).order_by('name')[:50]
    
    return render(request, 'orders/partials/ozon_pvz_list.html', {
        'pvz_list': fresh_pvz,
        'from_cache': False
    })


@require_GET
def ozon_delivery_checkout(request):
    """Расчёт стоимости доставки для выбранного ПВЗ"""
    map_point_id = request.GET.get('map_point_id', '')
    phone = request.GET.get('phone', '')
    
    if not phone or len(phone.replace('+', '').replace(' ', '').replace('-', '')) < 10:
        return HttpResponse("<p class='text-red-500 text-xs font-medium'>⚠️ Введите корректный номер телефона.</p>")
    
    if not map_point_id:
        return HttpResponse("<p class='text-red-500 text-xs'>Выберите пункт выдачи.</p>")

    client = OzonDeliveryClient()
    
    response_data = client.calculate_checkout(
        items=[{"offer_id": OZON_TEST_OFFER_ID, "quantity": 1, "sku": 0}],
        map_point_id=map_point_id,
        phone=phone,
        warehouse_id=OZON_TEST_WAREHOUSE_ID,
        delivery_schema="MIX"
    )
    
    # Извлекаем стоимость и сроки доставки из ответа
    cost = None
    delivery_time = None
    error_msg = None
    
    if 'error' in response_data:
        error_msg = response_data['error']
    else:
        splits = response_data.get('splits', [])
        if splits:
            split = splits[0]
            commissions = split.get('commissions', {})
            if commissions and commissions.get('total'):
                cost = commissions['total'].get('amount')
            
            delivery_method = split.get('delivery_method', {})
            timeslots = delivery_method.get('timeslots', [])
            if timeslots:
                delivery_time = "1-2 дня"  # Упрощённое отображение
    
    context = {
        'cost': cost,
        'delivery_time': delivery_time,
        'error_msg': error_msg,
        'map_point_id': map_point_id,
    }
    
    return render(request, 'orders/partials/ozon_delivery_cost.html', context)


# ==========================================
# ВРЕМЕННЫЙ DEBUG VIEW (УДАЛИТЬ ПОСЛЕ ДИАГНОСТИКИ!)
# ==========================================
import time

import requests as req
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


@csrf_exempt
@require_GET
def ozon_debug(request):
    results = {}
    city = "Санкт-Петербург"
    results['city_searched'] = city
    
    # 1. Геокодинг
    try:
        geo = req.get("https://nominatim.openstreetmap.org/search", 
                      params={"format": "json", "q": city, "limit": 1},
                      headers={"User-Agent": "PBShopBot/1.0"}, timeout=10)
        results['geocoding'] = {'success': True, 'lat': geo.json()[0]['lat'], 'lon': geo.json()[0]['lon']}
    except Exception as e:
        results['geocoding'] = {'error': str(e)}
        return JsonResponse(results, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    
    lat, lon = float(geo.json()[0]['lat']), float(geo.json()[0]['lon'])
    
    # 2. Полный цикл
    try:
        from orders.models import OzonAuth, OzonPVZ
        from orders.ozon_client import OzonDeliveryClient
        
        auth = OzonAuth.objects.filter(is_active=True).first()
        results['oauth'] = {
            'token_exists': auth is not None,
            'is_valid': auth.expires_at > timezone.now() if auth else False
        }
        
        client = OzonDeliveryClient()
        viewport = {
            "left_bottom": {"lat": lat - 0.45, "long": lon - 0.45},
            "right_top": {"lat": lat + 0.45, "long": lon + 0.45}
        }
        
        clusters = client.get_pvz_clusters(viewport, zoom=10)
        results['clusters_count'] = len(clusters.get('clusters', []))
        
        all_point_ids = []
        for cluster in clusters.get('clusters', []):
            all_point_ids.extend([str(pid) for pid in cluster.get('map_point_ids', [])])
        
        results['total_point_ids_found'] = len(all_point_ids)
        all_point_ids = all_point_ids[:200] # Ограничиваем
        
        all_details = []
        first_batch_raw_response = None # <-- НОВОЕ: ловим сырой ответ
        
        for i in range(0, len(all_point_ids), 100):
            batch = all_point_ids[i:i+100]
            info_response = client.get_pvz_info(batch)
            
            if i == 0:
                first_batch_raw_response = info_response # <-- Сохраняем ответ первой пачки
                
            if 'error' not in info_response:
                all_details.extend(info_response.get('points', []))
            if i + 100 < len(all_point_ids):
                time.sleep(0.2)
                
        results['details_fetched_count'] = len(all_details)
        results['first_batch_raw_response'] = first_batch_raw_response # <-- Добавляем в вывод
        
        # 3. Тест сохранения
        if all_details:
            test_point = all_details[0]
            dm = test_point.get('delivery_method', {})
            addr = dm.get('address_details', {})
            coord = dm.get('coordinates', {})
            
            try:
                obj, created = OzonPVZ.objects.update_or_create(
                    map_point_id=test_point.get('map_point_id'),
                    defaults={
                        'name': dm.get('name', ''),
                        'address': dm.get('address', ''),
                        'city': addr.get('city', city),
                        'region': addr.get('region', ''),
                        'lat': coord.get('lat'),
                        'lng': coord.get('long'),
                        'enabled': test_point.get('enabled', True),
                    }
                )
                results['db_save_test'] = {'success': True, 'created': created, 'saved_name': dm.get('name')}
            except Exception as db_e:
                results['db_save_test'] = {'error': str(db_e)}
        else:
            results['db_save_test'] = 'Нет данных для сохранения (all_details пуст)'
            
    except Exception as e:
        results['full_flow_error'] = str(e)

    return JsonResponse(results, json_dumps_params={'ensure_ascii': False, 'indent': 2})