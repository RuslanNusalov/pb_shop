from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, UniqueConstraint
from decimal import Decimal

# 1. PromoCode вынесен наверх для чистоты ссылок
class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(
        max_length=10,
        choices=[('percent', 'Процент'), ('fixed', 'Фиксированная сумма')],
        default='percent'
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True)
    max_usage = models.PositiveIntegerField(default=0, help_text="0 = без лимита")
    usage_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField("Начало действия", blank=False)
    valid_to = models.DateTimeField("Окончание действия", blank=False)
    is_active = models.BooleanField(default=True)

    def clean(self):
        # 1. Проверяем, что даты указаны
        if self.valid_from is None or self.valid_to is None:
            raise ValidationError("Укажите даты начала и окончания действия промокода")
        
        # 2. Сравниваем только если обе даты присутствуют
        if self.valid_from > self.valid_to:
            raise ValidationError("Дата окончания не может быть раньше даты начала")
            
        if self.discount_type == 'percent' and not (0 < self.discount_value <= 100):
            raise ValidationError("Процент скидки должен быть от 0.01 до 100")
        if self.discount_type == 'fixed' and self.discount_value <= 0:
            raise ValidationError("Сумма скидки должна быть больше 0")

    def save(self, *args, **kwargs):
        self.full_clean()  # ✅ Гарантирует валидацию при любом сохранении
        super().save(*args, **kwargs)

    def is_valid(self):
        now = timezone.now()
        if not self.is_active: return False
        if now < self.valid_from or now > self.valid_to: return False
        if self.max_usage > 0 and self.usage_count >= self.max_usage: return False
        return True

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self):
        return f"{self.code} ({self.discount_value}{'%' if self.discount_type=='percent' else '₽'})"


class CartItem(models.Model):
    # ✅ Строковая ссылка избегает проблем порядка объявления классов
    cart = models.ForeignKey('Cart', related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('main.Product', on_delete=models.CASCADE)
    product_size = models.ForeignKey('main.ProductSize', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # ✅ Современный синтаксис Django 4.2+
        constraints = [
            UniqueConstraint(fields=['cart', 'product', 'product_size'], name='unique_cart_item')
        ]
        verbose_name = "Товар в корзине"
        verbose_name_plural = "Товары в корзине"

    def __str__(self):
        return f"{self.product.name} - {self.product_size.size.name} x {self.quantity}"

    @property
    def total_price(self):
        # ✅ Если price в Product уже Decimal, str() не нужен
        return self.product.price * self.quantity


class Cart(models.Model):
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True)
    promo_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"

    def __str__(self):
        return f"Cart {self.session_key}"

    @property
    def subtotal(self):
        # ✅ Один SQL-запрос вместо N+1
        result = self.items.aggregate(total=Sum(F('product__price') * F('quantity')))['total']
        return result or Decimal('0')

    @property
    def total(self):
        # ✅ Безопасное сравнение Decimal
        return max(Decimal('0'), self.subtotal - self.promo_discount)
    
    @property
    def total_items(self):
        """Возвращает общее количество единиц товара в корзине"""
        return self.items.aggregate(total=Sum('quantity'))['total'] or 0

    def add_product(self, product, product_size, quantity=1):
        cart_item, created = CartItem.objects.get_or_create(
            cart=self, product=product, product_size=product_size,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save(update_fields=['quantity'])
        return cart_item

    def remove_item(self, item_id):
        try:
            self.items.get(id=item_id).delete()
            return True
        except CartItem.DoesNotExist:
            return False

    def update_item_quantity(self, item_id, quantity):
        try:
            item = self.items.get(id=item_id)
            if quantity > 0:
                item.quantity = quantity
                item.save(update_fields=['quantity'])
            else:
                item.delete()
            return True
        except CartItem.DoesNotExist:
            return False

    def clear(self):
        self.items.all().delete()

    def apply_promo(self, promo_code):
        # ✅ Защита от повторного применения
        if self.promo_code:
            raise ValidationError("Промокод уже применён")
            
        # ✅ Атомарная блокировка для защиты от race condition
        with transaction.atomic():
            promo_code = PromoCode.objects.select_for_update().get(pk=promo_code.pk)
            
            if not promo_code.is_valid():
                raise ValidationError("Промокод недействителен")
            if self.subtotal < promo_code.min_order_amount:
                raise ValidationError(f"Минимальная сумма заказа: {promo_code.min_order_amount} ₽")

            if promo_code.discount_type == 'percent':
                discount = (self.subtotal * promo_code.discount_value) / 100
            else:
                discount = min(promo_code.discount_value, self.subtotal)

            # ✅ Надёжное округление до копеек
            self.promo_discount = discount.quantize(Decimal('0.01'))
            self.promo_code = promo_code
            self.save(update_fields=['promo_discount', 'promo_code'])

    def remove_promo(self):
        self.promo_discount = 0
        self.promo_code = None
        self.save(update_fields=['promo_discount', 'promo_code'])

        