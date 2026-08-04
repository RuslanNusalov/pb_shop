from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('main.urls', namespace='main')),
    path('cart/', include('cart.urls', namespace='cart')),
    path('users/', include('users.urls', namespace='users')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('payment/', include('payment.urls', namespace='payment')),
    path('wishlist/', include('wishlist.urls')),
]

# ✅ Явная отдача медиа-фافайлов в продакшене
if not settings.DEBUG:
    urlpatterns += [
        path('media/<path:path>', serve, {'document_root': '/data/media'}),
    ]