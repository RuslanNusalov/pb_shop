from django.contrib import admin
from .models import Cart, CartItem, PromoCode

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ('product', 'product_size', 'quantity', 'total_price')
    readonly_fields = ('total_price',)
    can_delete = False

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'total_items', 'subtotal', 'total', 'promo_code', 'created_at')
    readonly_fields = ('total_items', 'subtotal', 'total', 'promo_discount')
    list_filter = ('created_at', 'promo_code')
    search_fields = ('session_key',)
    inlines = [CartItemInline]

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'product_size', 'quantity', 'total_price', 'added_at')
    list_filter = ('added_at', 'product_size__size')
    search_fields = ('product__name', 'product_size__size__name')

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'is_valid', 'usage_count', 'max_usage')
    list_filter = ('is_active', 'discount_type', 'valid_from', 'valid_to')
    search_fields = ('code',)