from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from main.models import Product

# from orders.models import Order  # ← Убрано, т.к. логика заказов переносится в orders.views
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
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/register_form.html', context)
    return render(request, 'users/register.html', context)


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
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/login_form.html', context)
    return render(request, 'users/login.html', context)


@login_required(login_url=reverse_lazy('users:login'))
def profile_view(request):
    # Гарантируем наличие Wishlist у пользователя
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

    # Данные для превью на странице профиля
    # 💡 Если хочешь полностью отвязать users от orders, перенеси latest_order в orders.views или убери
    latest_order = None
    # latest_order = Order.objects.filter(user=request.user).order_by('-created_at').first()
    
    recommended_products = Product.objects.filter(is_active=True).order_by('-created_at')[:3]

    context = {
        'form': form,
        'user': request.user,
        'recommended_products': recommended_products,
        'latest_order': latest_order,
    }

    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/partials/profile_content.html', context)
    return TemplateResponse(request, 'users/profile.html', context)


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
            'user': request.user, 
            'form': form
        })
    messages.error(request, 'Проверьте правильность заполнения полей.')
    return redirect('users:profile')


@login_required(login_url=reverse_lazy('users:login'))
def logout_view(request):
    logout(request)
    if request.headers.get('HX-Request'):
        return HttpResponse(headers={'HX-Redirect': reverse('main:index')})
    return redirect('main:index')