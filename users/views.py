from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from main.models import Product
from orders.models import Order
from wishlist.models import Wishlist

from .forms import CustomUserCreationForm, CustomUserLoginForm, CustomUserUpdateForm


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if request.headers.get('HX-Request'):
                return HttpResponse(headers={'HX-Redirect': reverse('main:index')})
            return redirect('main:index')
    else:
        form = CustomUserCreationForm()

    context = {'form': form}
    # ✅ Если HTMX, отдаем только форму (без базы)
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/register_form.html', context)
    return render(request, 'users/register_page.html', context)


def login_view(request):
    if request.method == 'POST':
        form = CustomUserLoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect('users:profile')
    else:
        form = CustomUserLoginForm()

    context = {'form': form}
    # ✅ Если HTMX, отдаем только форму
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/login_form.html', context)
    return render(request, 'users/login_page.html', context)


@login_required(login_url=reverse_lazy('users:login'))
def profile_view(request):
    # Гарантируем наличие Wishlist
    Wishlist.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = CustomUserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлён.')
            if request.headers.get("HX-Request"):
                return HttpResponse(headers={'HX-Redirect': reverse('users:profile')})
            return redirect('users:profile')
    else:
        form = CustomUserUpdateForm(instance=request.user)

    recommended_products = Product.objects.filter(is_active=True).order_by('-created_at')[:3]
    latest_order = Order.objects.filter(user=request.user).order_by('-created_at').first()

    context = {
        'form': form,
        'user': request.user,
        'recommended_products': recommended_products,
        'latest_order': latest_order,
    }

    # ✅ ГЛАВНОЕ ИСПРАВЛЕНИЕ:
    if request.headers.get('HX-Request'):
        # Для HTMX отдаем ЧИСТЫЙ контент (без хедера/футера)
        return TemplateResponse(request, 'users/partials/profile_content.html', context)
    
    # Для обычного перехода отдаем полную страницу
    return TemplateResponse(request, 'users/profile_page.html', context)


@login_required(login_url=reverse_lazy('users:login'))
def account_details(request):
    return TemplateResponse(request, 'users/partials/account_details.html', {'user': request.user})


@login_required(login_url=reverse_lazy('users:login'))
def edit_account_details(request):
    form = CustomUserUpdateForm(instance=request.user)
    return TemplateResponse(request, 'users/partials/edit_account_details.html', {
        'user': request.user,
        'form': form
    })


@login_required(login_url=reverse_lazy('users:login'))
def update_account_details(request):
    if request.method != 'POST':
        if request.headers.get('HX-Request'):
            return HttpResponse(headers={'HX-Redirect': reverse('users:profile')})
        return redirect('users:profile')

    form = CustomUserUpdateForm(request.POST, instance=request.user)

    if form.is_valid():
        user = form.save()
        if request.headers.get('HX-Request'):
            return TemplateResponse(request, 'users/partials/account_details.html', {'user': user})
        return redirect('users:profile')

    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/edit_account_details.html', {
            'user': request.user, 'form': form
        })
    messages.error(request, 'Проверьте правильность заполнения полей.')
    return redirect('users:profile')


@login_required(login_url=reverse_lazy('users:login'))
def logout_view(request):
    logout(request)
    if request.headers.get('HX-Request'):
        return HttpResponse(headers={'HX-Redirect': reverse('main:index')})
    return redirect('main:index')


@login_required(login_url=reverse_lazy('users:login'))
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # ✅ ДОБАВЛЕНО: Проверка HTMX для истории заказов
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/order_history_content.html', {'orders': orders})
    
    return render(request, 'users/order_history.html', {'orders': orders})


@login_required(login_url=reverse_lazy('users:login'))
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'items__product_size__size'),
        id=order_id,
        user=request.user
    )
    
    # ✅ ДОБАВЛЕНО: Проверка HTMX для деталей заказа
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/order_detail_content.html', {'order': order})
        
    return TemplateResponse(request, 'users/order_detail.html', {'order': order})


@login_required(login_url=reverse_lazy('users:login'))
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == 'pending':
        order.status = 'cancelled'
        order.save()
        messages.success(request, f'Заказ №{order.id} успешно отменён')
    else:
        messages.error(request, 'Этот заказ нельзя отменить')
    
    return redirect('users:order_detail', order_id=order.id)