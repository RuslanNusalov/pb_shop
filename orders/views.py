
import logging
import re
from decimal import Decimal

from django.conf import settings
from django.contrib import messages  # ✅ ДОБАВЛЕНО
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
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

from .apiship_client import ApiShipClient
from .forms import OrderForm
from .models import Order, OrderItem

logger = logging.getLogger(__name__)

PVZ_PAGE_SIZE = 30
#OZON_TEST_WAREHOUSE_ID = getattr(settings, 'OZON_TEST_WAREHOUSE_ID', '')
#OZON_TEST_SKU = getattr(settings, 'OZON_TEST_SKU', '')


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
            'dadata_api_key': settings.DADATA_API_KEY,
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

        # ==========================================
        # 1. УМНАЯ ПОДМЕНА ДАННЫХ ДЛЯ ВАЛИДАЦИИ
        # ==========================================
        delivery_method = form_data.get('delivery_method', 'ozon')

        if delivery_method in ['ozon', 'pickup']:
            # А. Телефон и адрес: для Ozon берем из специальных полей
            if delivery_method == 'ozon':
                from orders.apiship_client import normalize_phone_for_ozon
                raw_phone = form_data.get('ozon_phone', '')
                form_data['phone'] = normalize_phone_for_ozon(raw_phone)
                form_data['address'] = f"ПВЗ Ozon: {form_data.get('ozon_point_name', 'Не указан')}"
                form_data['city'] = form_data.get('ozon_city', 'Не указан')
            else:  # pickup
                form_data['address'] = "Самовывоз из магазина"
                form_data['city'] = "Санкт-Петербург"  # Замените на ваш город, если нужно

            # Б. Имя и Фамилия: подставляем данные пользователя или заглушку
            if not form_data.get('first_name'):
                form_data['first_name'] = request.user.first_name if request.user.is_authenticated else "Покупатель"
            if not form_data.get('last_name'):
                form_data['last_name'] = request.user.last_name if request.user.is_authenticated else "Интернет-магазин"
            
            # В. Остальные обязательные поля адреса заполняем безопасными значениями
            form_data['region'] = form_data.get('region') or "Не указан"
            form_data['postal_code'] = form_data.get('postal_code') or "000000"
        # ==========================================

        form = OrderForm(form_data, user=request.user)

        if not form.is_valid():
            logger.warning(f"Checkout form errors: {form.errors}")
            context = self._checkout_context(
                form, cart, error_message='Пожалуйста, исправьте ошибки в форме.'
            )
            if request.headers.get('HX-Request'):
                return TemplateResponse(request, 'orders/checkout_content.html', context)
            return render(request, 'orders/checkout.html', context)

        cart_items = list(cart.items.select_related('product', 'product_size'))

        try:
            with transaction.atomic():
                # 1. Проверка остатков
                for item in cart_items:
                    product_size = ProductSize.objects.select_for_update().get(pk=item.product_size_id)
                    if product_size.stock < item.quantity:
                        raise ValidationError(
                            f'Недостаточно товара «{item.product.name}» '
                            f'(размер {product_size.size.name}): доступно {product_size.stock} шт.'
                        )

                # 2. Расчет сумм
                subtotal = cart.subtotal
                discount = cart.promo_discount
                total = subtotal - discount
                
                # БЕЗОПАСНОЕ получение стоимости доставки (превращаем в Decimal)
                raw_delivery_cost = form_data.get('ozon_delivery_cost', 0) if delivery_method == 'ozon' else 0
                try:
                    delivery_cost = Decimal(str(raw_delivery_cost).replace(',', '.'))
                except (ValueError, TypeError):
                    delivery_cost = Decimal('0.00')
                    
                final_total = total + delivery_cost

                # 3. Формируем комментарий для менеджера
                delivery_comment = ""
                if delivery_method == 'ozon':
                    delivery_comment = f"Доставка Ozon. ПВЗ: {form_data.get('ozon_point_name', 'Не указан')} (ID: {form_data.get('ozon_point_id', '')}). Стоимость доставки: {delivery_cost} ₽"
                elif delivery_method == 'pickup':
                    delivery_comment = "Самовывоз из магазина"
                
                user_instructions = form.cleaned_data.get('special_instructions', '').strip()
                final_instructions = f"{delivery_comment}\n{user_instructions}".strip() if delivery_comment else user_instructions

                # 4. Создание заказа (ТОЛЬКО проверенные поля модели)
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
                    special_instructions=final_instructions,
                    status='pending',
                    subtotal=subtotal,
                    promo_discount=discount,
                    promo_code=cart.promo_code,
                    total=final_total,
                )

                # 5. Создание товаров заказа и списание остатков
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

                # 6. Обновление промокода
                if cart.promo_code_id:
                    PromoCode.objects.filter(pk=cart.promo_code_id).update(
                        usage_count=F('usage_count') + 1
                    )

                # 7. Очистка корзины
                cart.items.all().delete()
                cart.promo_code = None
                cart.promo_discount = Decimal('0.00')
                cart.save(update_fields=['promo_code', 'promo_discount'])

        except ValidationError as e:
            logger.error(f"Validation error during checkout: {e}")
            context = self._checkout_context(form, cart, error_message=str(e))
            if request.headers.get('HX-Request'):
                return TemplateResponse(request, 'orders/checkout_content.html', context)
            return render(request, 'orders/checkout.html', context)
            
        except Exception as e:
            # Перехватывает ЛЮБУЮ неожиданную ошибку (например, ошибку базы данных), 
            # логирует полный traceback и не дает сайту упасть с 500-й ошибкой.
            logger.exception(f"Unexpected error during checkout: {e}")
            context = self._checkout_context(
                form, cart, 
                error_message='Произошла внутренняя ошибка при оформлении заказа. Пожалуйста, попробуйте позже или свяжитесь с нами.'
            )
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


def _norm(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'\b(ул|улица|проспект|пр-т|пр|переулок|пер|шоссе|ш|бульвар|б-р|набережная|наб|дом|д|корпус|к|строение|стр)\b\.?', ' ', s)
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\d\s]', ' ', s)).strip()


@require_GET
def ozon_pvz_list(request):
    raw_city = (request.GET.get('ozon_city') or '').strip()
    street_q = (request.GET.get('ozon_street') or '').strip()
    is_append = request.GET.get('append') == '1'
    try:
        offset = max(int(request.GET.get('offset', 0)), 0)
    except ValueError:
        offset = 0

    if not raw_city:
        return HttpResponse("<p class='text-gray-500 text-sm text-center py-4'>Введите город, чтобы увидеть пункты выдачи</p>")

    # Если в поле города ввели полный адрес: "Москва, Ленина, 10"
    city, street_from_city = raw_city, ''
    if ',' in raw_city:
        parts = [p.strip() for p in raw_city.split(',') if p.strip()]
        city = parts[0]
        street_from_city = ' '.join(parts[1:])
    if not street_q:
        street_q = street_from_city

    cache_key = f"apiship_pvz_ozonlog_{_norm(city)}"
    points = cache.get(cache_key)
    if points is None:
        data = ApiShipClient().get_all_pvz(city=city, service="ozonlog")
        if 'error' in data:
            return HttpResponse(f"<p class='text-red-500 text-sm text-center py-4'>Ошибка загрузки ПВЗ: {data['error']}</p>")
        points = data.get('rows', [])
        cache.set(cache_key, points, 60 * 30)

    # ── фильтрация по улице ──
    tokens = [t for t in _norm(street_q).split() if t]
    if tokens:
        house_tokens = [t for t in tokens if t.isdigit()]
        word_tokens = [t for t in tokens if not t.isdigit()]
        scored = []
        for p in points:
            addr = _norm(f"{p.get('street') or ''} {p.get('address') or ''}")
            house = _norm(str(p.get('house') or ''))
            if word_tokens and not all(t in addr for t in word_tokens):
                continue
            score = 0
            if word_tokens and all(t in _norm(p.get('street') or '') for t in word_tokens):
                score += 10
            if house_tokens and any(h == house for h in house_tokens):
                score += 20
            elif house_tokens and any(h in addr for h in house_tokens):
                score += 5
            scored.append((score, p))
        scored.sort(key=lambda x: (-x[0], x[1].get('address') or ''))
        filtered = [p for _, p in scored]
    else:
        filtered = sorted(points, key=lambda p: p.get('address') or '')

    total_found = len(filtered)
    page = filtered[offset:offset + PVZ_PAGE_SIZE]
    next_offset = offset + len(page)

    context = {
        'pvz_list': page,
        'total_found': total_found,
        'total_city': len(points),
        'city': city,
        'street_q': street_q,
        'next_offset': next_offset,
        'has_more': next_offset < total_found,
    }

    template = 'orders/partials/ozon_pvz_rows.html' if is_append else 'orders/partials/ozon_pvz_list.html'
    return render(request, template, context)


@require_GET
def ozon_delivery_checkout(request):
    """Рассчитывает стоимость доставки через ApiShip"""
    map_point_id = request.GET.get('map_point_id', '')
    city = request.GET.get('ozon_city', 'Москва')
    point_name = request.GET.get('point_name') or f"ПВЗ №{map_point_id}"
    point_address = request.GET.get('point_address') or ''
    
    if not map_point_id:
        return HttpResponse("<p class='text-red-500 text-xs'>Выберите пункт выдачи.</p>")

    # Тестовые габариты (можно будет брать из корзины)
    test_items = [
        {"length": 25, "width": 20, "height": 10, "weight": 0.5, "quantity": 1} # вес в кг, клиент переведет в граммы
    ]
    
    sender_city = getattr(settings, 'APISHIP_SENDER_CITY', 'Санкт-Петербург')

    client = ApiShipClient()
    response_data = client.calculate_delivery(
        service="ozonlog",
        sender_city=sender_city,
        receiver_city=city,
        receiver_point_id=map_point_id,
        items=test_items
    )

    
    if 'error' in response_data:
        logger.error(f"Ошибка расчёта ApiShip: {response_data['error']}")
        return HttpResponse(f"<p class='text-red-500 text-xs'>⚠️ {response_data['error']}</p>")

        # ApiShip /calculator: тарифы в deliveryToPoint / deliveryToDoor
    tariffs = []
    for block in response_data.get('deliveryToPoint', []):
        if block.get('providerKey') == 'ozonlog':
            tariffs.extend(block.get('tariffs', []))

    if not tariffs:
        return HttpResponse(
            "<p class='text-yellow-600 text-xs'>ℹ️ Доставка в этот пункт недоступна. Выберите другой.</p>"
        )

    # Берём самый дешёвый доступный тариф
    tariff = min(tariffs, key=lambda t: t.get('deliveryCost') or 10**9)

    cost = tariff.get('deliveryCost') or tariff.get('deliveryCostOriginal') or 0
    days_min = tariff.get('daysMin')
    days_max = tariff.get('daysMax')

    if days_min and days_max:
        delivery_time = f"{days_min}–{days_max} дн."
    elif days_min:
        delivery_time = f"от {days_min} дн."
    else:
        delivery_time = "уточняется"

    logger.info(f"✅ ApiShip расчёт: cost={cost}, time={delivery_time}, tariffId={tariff.get('tariffId')}")

    return render(request, 'orders/partials/ozon_delivery_cost.html', {
        'cost': cost,
        'delivery_time': delivery_time,
        'map_point_id': map_point_id,
        'point_name': point_name,
        'point_address': point_address,
        'tariff_id': tariff.get('tariffId'),
        'provider_key': 'ozonlog',
    })