from django.urls import path

from .views import CheckoutView, OrderDetailView

app_name = 'orders'

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    #path('order/<int:order_id>/', OrderDetailView.as_view(), name='order_detail'), 
]