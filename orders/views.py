import csv
import logging
import os
import re
import time
import traceback
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

from .apiship_client import ApiShipClient
from .cities import find_city_coords_fallback
from .forms import OrderForm
from .models import Order, OrderItem, OzonPVZ
from .ozon_client import OzonDeliveryClient

logger = logging.getLogger(__name__)

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
    """Возвращает список ПВЗ Ozon через ApiShip"""
    city = request.GET.get('ozon_city', '').strip()
    if not city:
        return HttpResponse("<p class='text-gray-500 text-sm text-center py-4'>Введите город для поиска ПВЗ</p>")

    client = ApiShipClient()
    response_data = client.get_pvz_list(city=city, service="ozonlog")

    if 'error' in response_data:
        return HttpResponse(f"<p class='text-red-500 text-sm text-center py-4'>Ошибка загрузки ПВЗ: {response_data['error']}</p>")

    # ApiShip возвращает список в ключе 'result' или сразу массив
    points = response_data.get('result', response_data if isinstance(response_data, list) else [])
    
    if not points:
        return HttpResponse("<p class='text-gray-500 text-sm text-center py-4'>ПВЗ не найдены. Попробуйте изменить запрос.</p>")

    # Ограничиваем вывод для скорости (ApiShip и так может вернуть много, берём первые 100)
    points = points[:100]

    context = {'pvz_list': points}
    return render(request, 'orders/partials/ozon_pvz_list.html', context)


@require_GET
def ozon_delivery_checkout(request):
    """Рассчитывает стоимость доставки через ApiShip"""
    map_point_id = request.GET.get('map_point_id', '')
    phone_raw = request.GET.get('phone', '')
    city = request.GET.get('ozon_city', 'Москва') # Город получателя
    
    if not map_point_id:
        return HttpResponse("<p class='text-red-500 text-xs'>Выберите пункт выдачи.</p>")

    # Для теста используем дефолтные габариты коробки (можно будет брать из корзины)
    test_items = [
        {"length": 25, "width": 20, "height": 10, "weight": 0.5, "quantity": 1}
    ]
    
    # Город отправителя (замените на ваш реальный город склада)
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
        return HttpResponse(f"<p class='text-red-500 text-xs font-medium'>⚠️ Ошибка расчёта: {response_data['error']}</p>")

    # Парсим ответ ApiShip (структура зависит от их API, обычно это result.price или подобное)
    # Если структура другая, мы увидим её в логах и поправим
    result = response_data.get('result', {})
    
    # В ApiShip стоимость обычно лежит в result.price или result.total
    cost = result.get('price') or result.get('total') or 0
    delivery_time = result.get('delivery_time') or result.get('min_days', 'Уточняется')

    return render(request, 'orders/partials/ozon_delivery_cost.html', {
        'cost': cost,
        'delivery_time': f"{delivery_time} дн.",
        'map_point_id': map_point_id
    })