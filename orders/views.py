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
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (  # ✅ ДОБАВЛЕНО get_object_or_404
    get_object_or_404,
    redirect,
    render,
)
from django.template.response import TemplateResponse
from django.urls import reverse_lazy  # ✅ ДОБАВЛЕНО reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.views.generic import DetailView, View

from cart.models import PromoCode
from cart.views import CartMixin
from main.mixins import WishlistContextMixin
from main.models import ProductSize

from .cities import find_city_coords_fallback
from .forms import OrderForm
from .models import Order, OrderItem, OzonPVZ
from .ozon_client import OzonDeliveryClient

logger = logging.getLogger(__name__)

OZON_TEST_WAREHOUSE_ID = getattr(settings, 'OZON_TEST_WAREHOUSE_ID', '')
OZON_TEST_SKU = getattr(settings, 'OZON_TEST_SKU', '')


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
    city = (request.GET.get('ozon_city') or request.GET.get('city') or '').strip()
    
    if not city or len(city) < 3:
        return HttpResponse("<p class='text-gray-500 text-sm text-center py-4'>Введите название города (мин. 3 символа)</p>")
    
    logger.info(f"🔍 Поиск ПВЗ для города: {city}")
    
    # 1. Проверяем кэш
    cached_pvz = OzonPVZ.objects.filter(city__icontains=city, enabled=True).order_by('name')[:150]
    
    if cached_pvz.exists():
        logger.info(f"✅ Найдено {cached_pvz.count()} ПВЗ в кэше для {city}")
        return render(request, 'orders/partials/ozon_pvz_list.html', {
            'pvz_list': cached_pvz,
            'from_cache': True
        })
    
    logger.info(f"⏳ Кэш пуст, запрашиваем Ozon API для {city}")
    
    # 2. Геокодинг
    lat, lon = None, None
    
    # Пробуем DaData
    dadata_key = getattr(settings, 'DADATA_API_KEY', '')
    if dadata_key:
        try:
            dadata_response = requests.post(
                "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address",
                headers={
                    "Authorization": f"Token {dadata_key}",
                    "Content-Type": "application/json",
                },
                json={"query": city},
                timeout=10
            )
            if dadata_response.status_code == 200:
                dadata_data = dadata_response.json()
                if dadata_data.get('suggestions'):
                    lat = float(dadata_data['suggestions'][0]['data']['geo_lat'])
                    lon = float(dadata_data['suggestions'][0]['data']['geo_lon'])
                    logger.info(f"📍 DaData нашёл {city}: lat={lat}, lon={lon}")
        except Exception as e:
            logger.warning(f"⚠️ DaData ошибка: {e}")
    
    # Fallback на встроенный список
    if not lat or not lon:
        logger.info(f"⚠️ DaData не нашла {city}, используем fallback")
        coords = find_city_coords_fallback(city)
        if coords:
            lat, lon = coords
            logger.info(f"📍 Fallback нашёл {city}: lat={lat}, lon={lon}")
    
    # Если ничего не нашли
    if not lat or not lon:
        logger.warning(f"❌ Город не найден: {city}")
        return HttpResponse(f"<p class='text-red-500 text-sm text-center py-4'>Город '{city}' не найден. Попробуйте написать полностью.</p>")
    
    # 3. Viewport
    delta = 0.45
    viewport = {
        "left_bottom": {"lat": lat - delta, "long": lon - delta},
        "right_top": {"lat": lat + delta, "long": lon + delta}
    }
    
    # 4. Получаем кластеры
    client = OzonDeliveryClient()
    clusters_response = client.get_pvz_clusters(viewport, zoom=10)
    
    if 'error' in clusters_response:
        logger.error(f"❌ Ошибка кластеров: {clusters_response['error']}")
        return HttpResponse(f"<p class='text-red-500 text-sm text-center py-4'>Ошибка: {clusters_response['error']}</p>")
    
    clusters = clusters_response.get('clusters', [])
    logger.info(f"📦 Получено кластеров: {len(clusters)}")
    
    # 5. Собираем ID
    all_point_ids = []
    for cluster in clusters:
        all_point_ids.extend([str(pid) for pid in cluster.get('map_point_ids', [])])
    
    logger.info(f"🔢 Всего точек: {len(all_point_ids)}")
    
    if not all_point_ids:
        logger.warning(f"⚠️ Нет точек для {city}")
        return HttpResponse(f"<p class='text-gray-500 text-sm text-center py-4'>ПВЗ не найдены в радиусе 50 км от '{city}'</p>")
    
    all_point_ids = all_point_ids[:1000]
    
    # 6. Получаем детали пачками (максимум 10 пачек = 1000 точек)
    import time as time_module
    all_details = []
    max_batches = 10  # 10 пачек × 100 точек = 1000 точек максимум
    batch_count = 0
    
    for i in range(0, len(all_point_ids), 100):
        if batch_count >= max_batches:
            break
        batch = all_point_ids[i:i+100]
        info_response = client.get_pvz_info(batch)
        if 'error' not in info_response:
            points = info_response.get('points', [])
            all_details.extend(points)
            logger.info(f"📋 Пачка {batch_count + 1}: получено {len(points)} точек")
        else:
            logger.warning(f"⚠️ Ошибка пачки {batch_count + 1}: {info_response.get('error')}")
        batch_count += 1
        if i + 100 < len(all_point_ids):
            time_module.sleep(0.15)  # Чуть меньше пауза для скорости
    
    logger.info(f"✅ Всего получено деталей: {len(all_details)}")
    
    # 7. Сохраняем в кэш (map_point_id лежит внутри delivery_method!)
    saved_count = 0
    for point_data in all_details:
        try:
            dm = point_data.get('delivery_method', {})
            mp_id = dm.get('map_point_id')  # ← ИСПРАВЛЕНО: берём из delivery_method
            if not mp_id:
                continue
            addr = dm.get('address_details', {})
            coord = dm.get('coordinates', {})
            
            OzonPVZ.objects.update_or_create(
                map_point_id=mp_id,
                defaults={
                    'name': dm.get('name', ''),
                    'address': dm.get('address', ''),
                    'city': addr.get('city', city),
                    'region': addr.get('region', ''),
                    'lat': coord.get('lat'),
                    'lng': coord.get('long') or coord.get('lng'),
                    'enabled': point_data.get('enabled', True),
                    'working_hours': dm.get('working_hours'),
                }
            )
            saved_count += 1
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения точки: {e}")
            continue
    
    logger.info(f"💾 Сохранено в кэш: {saved_count} точек")
    
    # 8. Возвращаем данные (ищем по региону или координатам)
    from django.db.models import Q
    
    # Пробуем найти по региону (например, "Московская" для Москвы)
    fresh_pvz = OzonPVZ.objects.filter(
        Q(region__icontains=city) | Q(city__icontains=city),
        enabled=True
    ).order_by('name')[:150]
    
    # Если ничего не нашли по региону/городу, берём ближайшие по координатам
    if not fresh_pvz.exists():
        logger.info(f"⚠️ Не найдено по городу/региону, ищем по координатам")
        # Упрощённый поиск: берём все точки в радиусе ~50 км
        fresh_pvz = OzonPVZ.objects.filter(
            lat__gte=lat - 0.45, lat__lte=lat + 0.45,
            lng__gte=lon - 0.45, lng__lte=lon + 0.45,
            enabled=True
        ).order_by('name')[:50]
    
    logger.info(f"🔍 Найдено в кэше после сохранения: {fresh_pvz.count()}")
    
    return render(request, 'orders/partials/ozon_pvz_list.html', {
        'pvz_list': fresh_pvz,
        'from_cache': False
    })


@require_GET
def ozon_delivery_checkout(request):
    try:
        map_point_id = request.GET.get('map_point_id', '')
        phone_raw = request.GET.get('phone', '')
        
        logger.info(f"🔍 Получены параметры: map_point_id={map_point_id}, phone={phone_raw}")
        
        # 1. Очистка телефона
        phone = ''.join(c for c in phone_raw if c.isdigit())
        if phone.startswith('8'):
            phone = '7' + phone[1:]
        
        if not phone or len(phone) < 11:
            return HttpResponse("<p class='text-red-500 text-xs font-medium'>⚠️ Введите корректный номер телефона (минимум 11 цифр).</p>")
        if not map_point_id:
            return HttpResponse("<p class='text-red-500 text-xs'>Выберите пункт выдачи.</p>")

        # 2. Получаем настройки
        test_sku_str = getattr(settings, 'OZON_TEST_SKU', None)
        warehouse_id = getattr(settings, 'OZON_TEST_WAREHOUSE_ID', None)
        
        logger.info(f"⚙️ Настройки: OZON_TEST_SKU={test_sku_str}, WAREHOUSE_ID={warehouse_id}")
        
        if not test_sku_str or not warehouse_id:
            logger.error("❌ Отсутствуют OZON_TEST_SKU или OZON_TEST_WAREHOUSE_ID")
            return HttpResponse("<p class='text-red-500 text-xs'>Ошибка конфигурации: не указан тестовый SKU или склад.</p>")

        try:
            test_sku = int(test_sku_str)
            warehouse_id = int(warehouse_id)
            map_point_id = int(map_point_id)
        except ValueError as e:
            logger.error(f"❌ Ошибка преобразования типов: {e}")
            return HttpResponse(f"<p class='text-red-500 text-xs'>Ошибка: SKU и warehouse_id должны быть числами. {e}</p>")

        # 3. Вызываем Ozon API
        from orders.ozon_client import OzonDeliveryClient
        client = OzonDeliveryClient()
        
        logger.info(f"📦 Отправляем запрос: sku={test_sku}, map_point_id={map_point_id}, phone={phone}, warehouse_id={warehouse_id}")
        
        response_data = client.calculate_checkout(
            items=[{"sku": test_sku, "quantity": 1}],
            map_point_id=map_point_id,
            phone=phone,
            warehouse_id=warehouse_id,
            delivery_schema="MIX",
            delivery_type="pick_up"  # ← для ПВЗ/постаматов
        )
        
        logger.info(f"📊 Ответ Ozon: {response_data}")
        
        # 4. Обработка ответа
        if 'error' in response_data:
            logger.error(f"❌ Ozon вернул ошибку: {response_data['error']}")
            return HttpResponse(f"<p class='text-red-500 text-xs font-medium'>⚠️ Ошибка расчёта: {response_data['error']}</p>")
        
        # 5. Парсинг результата
        delivery_options = response_data.get('delivery_options', [])
        if not delivery_options:
            logger.warning(f"⚠️ Нет вариантов доставки. Ответ: {response_data}")
            return HttpResponse("<p class='text-yellow-600 text-xs'>ℹ️ Доставка в этот пункт временно недоступна.</p>")
        
        option = delivery_options[0]
        cost = option.get('price', 0)
        
        delivery_days = option.get('delivery_days', {})
        min_days = delivery_days.get('min', 0)
        max_days = delivery_days.get('max', 0)
        delivery_time = f"{min_days}-{max_days} дн." if min_days != max_days else f"{min_days} дн."
        
        logger.info(f"✅ Успех: cost={cost}, delivery_time={delivery_time}")
        
        return render(request, 'orders/partials/ozon_delivery_cost.html', {
            'cost': cost,
            'delivery_time': delivery_time,
            'map_point_id': map_point_id
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"💥 Критическая ошибка в ozon_delivery_checkout:\n{error_details}")
        # Временно выводим детали ошибки в браузер (УДАЛИТЬ ПОСЛЕ ДИАГНОСТИКИ!)
        return HttpResponse(f"<pre style='color:red;font-size:10px;'>ОШИБКА 500:\n{error_details}</pre>")


# ==========================================
# ВРЕМЕННЫЙ DEBUG VIEW (УДАЛИТЬ ПОСЛЕ ДИАГНОСТИКИ!)
# ==========================================
@require_GET
def ozon_debug(request):

    pvz = OzonPVZ.objects.filter(enabled=True).exclude(map_point_id__isnull=True).first()
    if not pvz:
        return JsonResponse({'error': 'нет ПВЗ в кэше'})

    sku = int(getattr(settings, 'OZON_TEST_SKU', 0))
    wh = int(getattr(settings, 'OZON_TEST_WAREHOUSE_ID', 0))
    phone = '79111719087'
    client = OzonDeliveryClient()

    # Правильный payload по документации
    payload = {
        "buyer_phone": phone,
        "delivery_schema": "MIX",
        "delivery_type": {
            "pick_up": {
                "map_point_id": int(pvz.map_point_id)
            }
        },
        "items": [{"sku": sku, "quantity": 1}],
        "warehouse_id": wh,
    }

    resp = client._make_request('/v2/delivery/checkout', payload, auth='oauth')
    
    return JsonResponse({
        'pvz_id': pvz.map_point_id, 'sku': sku, 'warehouse': wh,
        'payload': payload,
        'response': resp,
    }, json_dumps_params={'ensure_ascii': False, 'indent': 2})