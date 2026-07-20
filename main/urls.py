from django.urls import path, re_path
from . import views

app_name = 'main'

urlpatterns = [
    re_path(r'^product/(?P<slug>[-\w]+)/$', views.ProductDetailView.as_view(), name='product_detail'),
    re_path(r'^catalog/(?P<category_slug>[-\w]+)/$', views.CatalogView.as_view(), name='catalog'),
    path('product/<slug:slug>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('catalog/<slug:category_slug>/', views.CatalogView.as_view(), name='catalog'),
    path('catalog/', views.CatalogView.as_view(), name='catalog_all'),
    path('', views.IndexView.as_view(), name='index'),
]
