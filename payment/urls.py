from django.urls import path
from . import views

app_name = 'payment'

urlpatterns = [
    path('orders/<int:order_id>/instructions/', views.payment_instructions, name='payment_instructions'),
    path('orders/<int:order_id>/upload-proof/', views.upload_payment_proof, name='upload_proof'),
    path('orders/<int:order_id>/success/', views.payment_success, name='payment_success'),
    path('orders/<int:order_id>/expired/', views.payment_expired, name='payment_expired'),
    # path('webhook/', views.manual_payment_webhook, name='webhook'),  # если понадобится
]