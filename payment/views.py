import os
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse
from django.http import HttpResponse
from django.utils import timezone
from orders.models import Order
import logging

logger = logging.getLogger(__name__)

PAYMENT_CARD_NUMBER = os.getenv('PAYMENT_CARD_NUMBER')
PAYMENT_CARD_HOLDER = os.getenv('PAYMENT_CARD_HOLDER')
PAYMENT_BANK_NAME = os.getenv('PAYMENT_BANK_NAME')


@login_required
def payment_instructions(request, order_id):
    """Показывает реквизиты для перевода и инструкцию"""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status in ['paid', 'processing', 'shipped', 'delivered']:
        return redirect('payment:payment_success', order_id=order.pk)

    if order.status == 'cancelled' or order.is_expired:
        if order.status == 'pending' and order.is_expired:
            order.status = 'expired'
            order.save(update_fields=['status'])
        return redirect('payment:payment_expired', order_id=order.pk)

    context = {
        'order': order,
        'card_number': PAYMENT_CARD_NUMBER,
        'card_holder': PAYMENT_CARD_HOLDER,
        'bank_name': PAYMENT_BANK_NAME,
        'amount': order.total,
        'reference': order.payment_reference,
        'expires_at': order.expires_at,
    }

    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'payment/payment_instructions_content.html', context)
    return TemplateResponse(request, 'payment/payment_instructions.html', context)


@login_required
def upload_payment_proof(request, order_id):
    """HTMX-эндпоинт для загрузки скриншота чека (опционально)"""
    if request.method != 'POST':
        return HttpResponse(status=405)

    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.FILES.get('proof'):
        order.payment_screenshot = request.FILES['proof']
        order.save(update_fields=['payment_screenshot'])

        if request.headers.get('HX-Request'):
            return HttpResponse(
                '<p class="text-green-600">✓ Чек загружен. Ожидайте подтверждения.</p>',
                headers={'HX-Trigger': 'proofUploaded'}
            )

    return HttpResponse(status=400)


@login_required
def payment_success(request, order_id):
    """Страница после успешной отправки оплаты"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {'order': order}
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'payment/success_content.html', context)
    return TemplateResponse(request, 'payment/success.html', context)


@login_required
def payment_expired(request, order_id):
    """Страница при истечении срока оплаты"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == 'pending' and order.is_expired:
        order.status = 'expired'
        order.save(update_fields=['status'])
    context = {'order': order}
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'payment/payment_expired_content.html', context)
    return TemplateResponse(request, 'payment/payment_expired.html', context)
