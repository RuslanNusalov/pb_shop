from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from decimal import Decimal
from main.models import Product, ProductSize


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('paid', 'Оплачен (в обработке)'),
        ('processing', 'Сборка заказа'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён'),
        ('expired', 'Срок оплаты истёк'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    
    #  Контактные данные и адрес доставки
    first_name = models.CharField(max_length=50, verbose_name="Имя")
    last_name = models.CharField(max_length=50, verbose_name="Фамилия")
    email = models.EmailField(max_length=254, verbose_name="Эл. почта")
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="Адрес")
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Город")
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name="Регион")
    postal_code = models.CharField(max_length=20, blank=True, null=True, verbose_name="Индекс")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Телефон")
    special_instructions = models.TextField(blank=True, default="", verbose_name="Комментарий")
    
    # 💰 Финансы
    cart = models.ForeignKey('cart.Cart', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Корзина")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Подытог")
    promo_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Скидка")
    promo_code = models.ForeignKey('cart.PromoCode', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Промокод")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Итого к оплате")
    
    # 💳 Оплата и статус
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    payment_reference = models.CharField(max_length=50, blank=True, unique=True, 
                                         verbose_name="Номер для перевода",
                                         help_text="Уникальный код для комментария к платежу")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Срок оплаты",
                                      help_text="Дедлайн оплаты (автоматически +24ч)")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата оплаты",
                                   help_text="Дата фактического зачисления средств")
    payment_screenshot = models.ImageField(upload_to='payment_screenshots/', 
                                           null=True, blank=True, 
                                           verbose_name="Скриншот оплаты",
                                           help_text="Чек или скриншот перевода от клиента")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    def clean(self):
        """Валидация: Итого = Подытог - Скидка (не может быть < 0)"""
        if self.subtotal is not None and self.promo_discount is not None:
            expected_total = self.subtotal - self.promo_discount
            if self.total != max(Decimal('0'), expected_total):
                raise ValidationError(f"Итого ({self.total}) не совпадает с расчётом (Подытог - Скидка).")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Авто-расчёт итого, если не задан
        if self.subtotal is not None and self.promo_discount is not None and not self.total:
            self.total = max(Decimal('0'), self.subtotal - self.promo_discount)

        # Первичное сохранение для получения PK
        super().save(*args, **kwargs)
        
        # Генерация референса и дедлайна только для новых заказов
        if is_new:
            self.payment_reference = f"ORD-{self.pk}"
            self.expires_at = timezone.now() + timedelta(hours=24)
            # Обновляем только изменённые поля, чтобы не триггерить сигналы повторно
            super().save(update_fields=['payment_reference', 'expires_at'])

    def __str__(self):
        return f"Заказ #{self.pk} | {self.get_status_display()} | {self.email}"

    @property
    def is_expired(self):
        """Проверяет, истёк ли срок оплаты (только для pending заказов)"""
        return self.status == 'pending' and self.expires_at and self.expires_at < timezone.now()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_order_status_created'),
            models.Index(fields=['payment_reference'], name='idx_order_ref'),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="Заказ")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Товар")
    product_size = models.ForeignKey(
        ProductSize, 
        on_delete=models.SET_NULL,  # 🔒 Безопаснее для истории заказов
        null=True, 
        blank=True, 
        verbose_name="Размер"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена на момент покупки")

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
        indexes = [
            models.Index(fields=['order', 'product'], name='idx_orderitem_order_product'),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.product_size}) x {self.quantity}"

    @property
    def total(self):
        """Стоимость позиции = цена × количество"""
        return self.price * self.quantity