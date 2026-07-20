from django.urls import path
from . import views

app_name = 'wishlist'

urlpatterns = [
    path('toggle/<int:size_id>/', views.ToggleWishlistView.as_view(), name='toggle'),
    path('', views.WishlistListView.as_view(), name='list'),
    path('toggle-btn/<int:product_id>/<int:size_id>/', views.GetWishlistToggleBtn.as_view(), name='get_toggle_btn'),
]