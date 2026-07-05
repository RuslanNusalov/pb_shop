import json
from django.shortcuts import get_object_or_404
from django.views.generic import View
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from django.core.exceptions import ValidationError
from django.db import transaction
from main.models import Product, ProductSize
from .models import Cart, CartItem, PromoCode
from .forms import AddToCartForm, PromoCodeForm


class CartMixin:
    def get_cart(self, request):
        if hasattr(request, 'cart'):
            return request.cart
        
        if not request.session.session_key:
            request.session.create()

        cart, created = Cart.objects.get_or_create(
            session_key=request.session.session_key
        )

        request.session['cart_id'] = cart.id
        request.session.modified = True
        request.cart = cart  # Кэшируем на текущий запрос
        return cart
    
    def render_cart_modal(self, request, cart):
        context = {
            'cart': cart,
            'cart_items': cart.items.select_related(
                'product',
                'product_size__size'
            ).order_by('-added_at')
        }
        return TemplateResponse(request, 'cart/cart_modal.html', context)
    
    def _htmx_error(self, request, message):
        """Единый формат ошибки для HTMX (статус 200 + триггер уведомления)"""
        response = HttpResponse(status=200)
        response['HX-Trigger'] = json.dumps({
            "showToast": {"message": message, "type": "error"}
        })
        return response


class CartModalView(CartMixin, View):
    http_method_names = ['get']
    def get(self, request):
        cart = self.get_cart(request)
        return self.render_cart_modal(request, cart)


class AddToCartView(CartMixin, View):
    http_method_names = ['post']
    @transaction.atomic
    def post(self, request, slug):
        cart = self.get_cart(request)
        product = get_object_or_404(Product, slug=slug)

        form = AddToCartForm(request.POST, product=product)
        if not form.is_valid():
            return self._htmx_error(request, "Проверьте правильность выбора")
        
        size_id = form.cleaned_data.get('size_id')
        if size_id:
            try:
                product_size = ProductSize.objects.get(id=size_id, product=product)
            except ProductSize.DoesNotExist:
                return self._htmx_error(request, "Выбранный размер не найден")
        else:
            product_size = product.product_sizes.filter(stock__gt=0).first()
            if not product_size:
                return self._htmx_error(request, "Товар временно отсутствует")

        quantity = form.cleaned_data['quantity']
        if product_size.stock < quantity:
            return self._htmx_error(request, f"Доступно только {product_size.stock} шт.")

        existing_item = cart.items.filter(product=product, product_size=product_size).first()
        if existing_item:
            if existing_item.quantity + quantity > product_size.stock:
                remaining = product_size.stock - existing_item.quantity
                return self._htmx_error(request, f"Можно добавить ещё {remaining} шт.")
            
        cart_item = cart.add_product(product, product_size, quantity)

        if request.headers.get('HX-Request'):
            # ✅ Возвращаем HTML модалки + триггер успешного действия
            response = self.render_cart_modal(request, cart)
            response['HX-Trigger'] = json.dumps({
                "showToast": {"message": f"{product.name} добавлен в корзину", "type": "success"},
                "cartUpdated": {"total": cart.total_items}
            })
            return response
        else:
            return JsonResponse({
                'success': True,
                'total_items': cart.total_items,
                'message': f'{product.name} добавлен в корзину',
                'cart_item_id': cart_item.id
            })
        

class UpdateCartItemView(CartMixin, View):
    http_method_names = ['post']
    @transaction.atomic
    def post(self, request, item_id):
        cart = self.get_cart(request)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)

        try:
            quantity = int(request.POST.get('quantity', 1))
        except (ValueError, TypeError):
            return self._htmx_error(request, "Некорректное количество")

        if quantity < 0:
            return self._htmx_error(request, "Количество не может быть отрицательным")
        
        if quantity == 0:
            cart_item.delete()
        else:
            if quantity > cart_item.product_size.stock:
                return self._htmx_error(request, f"Доступно только {cart_item.product_size.stock} шт.")
            
            cart_item.quantity = quantity
            cart_item.save()

        return self.render_cart_modal(request, cart)
    

class RemoveCartItemView(CartMixin, View):
    http_method_names = ['post']
    def post(self, request, item_id):
        cart = self.get_cart(request)

        try:
            cart_item = cart.items.get(id=item_id)
            cart_item.delete()
            return self.render_cart_modal(request, cart)
        except CartItem.DoesNotExist:
            return self._htmx_error(request, "Товар уже удалён из корзины")
        
    
class CartCountView(CartMixin, View):
    http_method_names = ['get']
    def get(self, request):
        cart = self.get_cart(request)
        return JsonResponse({
            'total_items': cart.total_items,
            'subtotal': float(cart.subtotal)
        })
    

class ClearCartView(CartMixin, View):
    http_method_names = ['post']
    def post(self, request):
        cart = self.get_cart(request)
        cart.clear()

        if request.headers.get('HX-Request'):
            return TemplateResponse(request, 'cart/cart_empty.html', {'cart': cart})
        return JsonResponse({'success': True, 'message': 'Корзина очищена'})


class CartSummaryView(CartMixin, View):
    http_method_names = ['get']
    def get(self, request):
        cart = self.get_cart(request)
        return self.render_cart_modal(request, cart)  # Переиспользуем существующий метод
    

class ApplyPromoCodeView(CartMixin, View):
    def post(self, request):
        cart = self.get_cart(request)
        form = PromoCodeForm(request.POST)
        
        if form.is_valid():
            code = form.cleaned_data['code']
            try:
                promo = PromoCode.objects.get(code__iexact=code)
                cart.apply_promo(promo)
                msg = f"✅ Промокод применён! Скидка: -{cart.promo_discount} ₽"
                status = "success"
            except PromoCode.DoesNotExist:
                msg = "❌ Промокод не найден"
                status = "error"
            except ValidationError as e:
                msg = f"❌ {str(e)}"
                status = "error"
        else:
            msg = "❌ Введите промокод"
            status = "error"

        if request.headers.get('HX-Request'):
            response = TemplateResponse(request, 'cart/promo_section.html', {
                'cart': cart, 'message': msg, 'status': status
            })
            response['HX-Trigger'] = json.dumps({
                "cartUpdated": {"total": float(cart.total), "discount": float(cart.promo_discount)}
            })
            return response
        
        return JsonResponse({"status": status, "message": msg})

class RemovePromoCodeView(CartMixin, View):
    def post(self, request):
        cart = self.get_cart(request)
        cart.remove_promo()
        
        if request.headers.get('HX-Request'):
            response = TemplateResponse(request, 'cart/promo_section.html', {
                'cart': cart, 'message': 'Промокод удалён', 'status': 'info'
            })
            response['HX-Trigger'] = json.dumps({
                "cartUpdated": {"total": float(cart.total), "discount": 0}
            })
            return response
        
        return JsonResponse({"status": "success", "message": "Промокод удалён"})