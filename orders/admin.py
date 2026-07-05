from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ('image_preview', 'product', 'product_size', 'quantity', 'price', 'item_total')
    readonly_fields = ('image_preview', 'item_total')
    can_delete = False

    @admin.display(description='Изображение')
    def image_preview(self, obj):
        if obj.product and hasattr(obj.product, 'main_image') and obj.product.main_image:
            return mark_safe(
                f'<img src="{obj.product.main_image.url}" '
                f'style="max-height: 80px; max-width: 80px; object-fit: cover; border-radius: 4px;" />'
            )
        return mark_safe('<span style="color: gray;">Нет изображения</span>')

    @admin.display(description='Сумма позиции')
    def item_total(self, obj):
        try:
            return f"{obj.total:.2f} ₽" if obj.total else "0.00 ₽"
        except Exception:
            return mark_safe('<span style="color: red;">Ошибка данных</span>')


@admin.action(description='✅ Подтвердить оплату')
def mark_paid(modeladmin, request, queryset):
    count = queryset.filter(status='pending').update(status='paid', paid_at=timezone.now())
    modeladmin.message_user(request, f'✅ Оплачено: {count} заказов')

@admin.action(description='⏳ Срок оплаты истёк')
def mark_expired(modeladmin, request, queryset):
    count = queryset.filter(status='pending').update(status='expired')
    modeladmin.message_user(request, f'⏳ Просрочено: {count} заказов')

@admin.action(description=' Передать в сборку')
def mark_processing(modeladmin, request, queryset):
    count = queryset.filter(status='paid').update(status='processing')
    modeladmin.message_user(request, f'📦 В сборке: {count} заказов')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'full_name', 'email', 'payment_reference',
        'total', 'status', 'created_at', 'is_expired_badge'
    )
    list_filter = ('status', 'created_at', 'promo_code')
    search_fields = ('user__email', 'first_name', 'last_name', 'payment_reference', 'email')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'created_at', 'updated_at', 'subtotal', 'promo_discount',
        'total', 'payment_reference', 'expires_at'
    )
    inlines = [OrderItemInline]
    actions = [mark_paid, mark_expired, mark_processing]
    ordering = ('-created_at',)

    fieldsets = (
        ('Клиент и доставка', {
            'fields': ('user', 'first_name', 'last_name', 'email', 'phone',
                       'address', 'city', 'region', 'postal_code', 'special_instructions')
        }),
        ('Финансы и промокоды', {
            'fields': ('subtotal', 'promo_discount', 'promo_code', 'total')
        }),
        ('Оплата и статус', {
            'fields': ('status', 'payment_reference', 'paid_at', 'expires_at', 'payment_screenshot')
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # После создания заказа блокируем изменение контактных данных и финансов
        if obj and obj.pk:
            return self.readonly_fields + (
                'user', 'first_name', 'last_name', 'email', 'phone',
                'address', 'city', 'region', 'postal_code', 'special_instructions',
                'subtotal', 'promo_discount', 'total', 'promo_code'
            )
        return self.readonly_fields

    @admin.display(description='ФИО', ordering='last_name')
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or "—"

    @admin.display(description='Срок оплаты')
    def is_expired_badge(self, obj):
        if hasattr(obj, 'is_expired') and obj.is_expired:
            return mark_safe('<span style="color: red; font-weight: bold;">⚠️ Просрочен</span>')
        return mark_safe('<span style="color: green;">✅ Активен</span>')