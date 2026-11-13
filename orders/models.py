from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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

    DELIVERY_METHOD_CHOICES = [
        ('pickup', 'Самовывоз'),
        ('cdek', 'СДЭК'),
        ('ozon_pvz', 'Ozon Доставка (Пункт выдачи)'),
        ('ozon_courier', 'Ozon Доставка (Курьер)'),
    ]

    # ==========================================================
    # 👤 ПОЛЬЗОВАТЕЛЬ
    # ==========================================================
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='orders'
    )
    
    # ==========================================================
    # 📞 КОНТАКТНЫЕ ДАННЫЕ И АДРЕС
    # ==========================================================
    first_name = models.CharField(max_length=50, verbose_name="Имя")
    last_name = models.CharField(max_length=50, verbose_name="Фамилия")
    email = models.EmailField(max_length=254, verbose_name="Эл. почта")
    phone = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="Телефон",
        help_text="Обязателен для Ozon Доставки (формат: 79991234567)"
    )
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="Адрес")
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Город")
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name="Регион")
    postal_code = models.CharField(max_length=20, blank=True, null=True, verbose_name="Индекс")
    special_instructions = models.TextField(blank=True, default="", verbose_name="Комментарий")
    
    # ==========================================================
    # 💰 ФИНАНСЫ
    # ==========================================================
    cart = models.ForeignKey(
        'cart.Cart', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Корзина"
    )
    subtotal = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Подытог"
    )
    promo_discount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Скидка"
    )
    promo_code = models.ForeignKey(
        'cart.PromoCode', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Промокод"
    )
    delivery_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Стоимость доставки",
        help_text="Рассчитывается через API (Ozon/СДЭК) или фиксированная"
    )
    total = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        verbose_name="Итого к оплате"
    )
    
    # ==========================================================
    # 🚚 ДОСТАВКА
    # ==========================================================
    delivery_method = models.CharField(
        max_length=20, 
        choices=DELIVERY_METHOD_CHOICES, 
        default='pickup',
        verbose_name="Способ доставки"
    )
    
    # Поля для Ozon Доставки
    ozon_order_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="ID заказа в Ozon (order_id)",
        help_text="Возвращается методом v2/order/create"
    )
    
    ozon_posting_numbers = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name="Список номеров отправлений Ozon (posting_number)",
        help_text="Массив строк, т.к. заказ может быть разбит на несколько сплитов"
    )
    
    ozon_delivery_details = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name="Детали доставки Ozon",
        help_text="JSON: код ПВЗ, адрес курьера, сроки, данные сплитов"
    )
    
    # ==========================================================
    # 💳 ОПЛАТА И СТАТУС
    # ==========================================================
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending', 
        verbose_name="Статус"
    )
    payment_reference = models.CharField(
        max_length=50, 
        blank=True, 
        unique=True, 
        verbose_name="Номер для перевода",
        help_text="Уникальный код для комментария к платежу"
    )
    expires_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Срок оплаты",
        help_text="Дедлайн оплаты (автоматически +24ч)"
    )
    paid_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Дата оплаты",
        help_text="Дата фактического зачисления средств"
    )
    payment_screenshot = models.ImageField(
        upload_to='payment_screenshots/', 
        null=True, 
        blank=True, 
        verbose_name="Скриншот оплаты",
        help_text="Чек или скриншот перевода от клиента"
    )
    
    # ==========================================================
    # 📅 ВРЕМЕННЫЕ МЕТКИ
    # ==========================================================
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    # ==========================================================
    # 🔧 МЕТОДЫ
    # ==========================================================
    
    def clean(self):
        """Валидация заказа"""
        # 1. Проверка итоговой суммы
        if self.subtotal is not None and self.promo_discount is not None:
            expected_total = self.subtotal - self.promo_discount + self.delivery_cost
            if self.total != max(Decimal('0'), expected_total):
                raise ValidationError(
                    f"Итого ({self.total}) не совпадает с расчётом "
                    f"(Подытог {self.subtotal} - Скидка {self.promo_discount} + Доставка {self.delivery_cost})."
                )
        
        # 2. Проверка телефона для Ozon Доставки
        if self.delivery_method in ('ozon_pvz', 'ozon_courier'):
            if not self.phone:
                raise ValidationError({
                    'phone': 'Телефон обязателен для оформления доставки через Ozon.'
                })
            # Проверка формата телефона (должен быть без +, начиная с 7)
            clean_phone = self.phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not clean_phone.startswith('7') or len(clean_phone) != 11:
                raise ValidationError({
                    'phone': 'Телефон должен быть в формате 79991234567 (11 цифр, начиная с 7).'
                })

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Авто-расчёт итого, если не задан
        if self.subtotal is not None and self.promo_discount is not None and not self.total:
            self.total = max(
                Decimal('0'), 
                self.subtotal - self.promo_discount + self.delivery_cost
            )

        # Первичное сохранение для получения PK
        super().save(*args, **kwargs)
        
        # Генерация референса и дедлайна только для новых заказов
        if is_new:
            self.payment_reference = f"ORD-{self.pk}"
            self.expires_at = timezone.now() + timedelta(hours=24)
            super().save(update_fields=['payment_reference', 'expires_at'])

    def __str__(self):
        return f"Заказ #{self.pk} | {self.get_status_display()} | {self.email}"

    @property
    def is_expired(self):
        """Проверяет, истёк ли срок оплаты (только для pending заказов)"""
        return self.status == 'pending' and self.expires_at and self.expires_at < timezone.now()

    @property
    def ozon_posting_number(self):
        """
        Обратная совместимость: возвращает первый posting_number из списка.
        Используется в шаблонах, где ожидается одно значение.
        """
        if self.ozon_posting_numbers and isinstance(self.ozon_posting_numbers, list):
            return self.ozon_posting_numbers[0]
        return None

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_order_status_created'),
            models.Index(fields=['payment_reference'], name='idx_order_ref'),
            models.Index(fields=['ozon_order_id'], name='idx_order_ozon_id'),
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
    def total_price(self):
        """Стоимость позиции = цена × количество"""
        return self.price * self.quantity