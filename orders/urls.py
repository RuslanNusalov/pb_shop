from django.urls import path

from .views import (
    CheckoutView,
    OrderDetailView,
    cancel_order,
    order_history,
    views_oauth,
)

app_name = 'orders'

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('order-history/', order_history, name='order_history'),
    path('order/<int:order_id>/', OrderDetailView.as_view(), name='order_detail'),
    path('order/<int:order_id>/cancel/', cancel_order, name='cancel_order'),

    # Ozon OAuth маршруты
    path('ozon/oauth/login/', views_oauth.ozon_oauth_login, name='ozon_oauth_login'),
    path('ozon/oauth/callback/', views_oauth.ozon_oauth_callback, name='ozon_oauth_callback'),
]