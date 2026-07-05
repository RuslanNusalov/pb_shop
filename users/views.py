from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.http import HttpResponse
from django.template.response import TemplateResponse

from orders.models import Order
from .forms import CustomUserCreationForm, CustomUserLoginForm, CustomUserUpdateForm
from django.contrib import messages
from main.models import Product


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
        return TemplateResponse(request, 'users/register.html', context)
    return render(request, 'users/register_page.html', context)


def login_view(request):
    if request.method == 'POST':
        form = CustomUserLoginForm(request=request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            if request.headers.get('HX-Request'):
                return HttpResponse(headers={'HX-Redirect': reverse('main:index')})
            return redirect('main:index')
    else:
        form = CustomUserLoginForm()

    context = {'form': form}
    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/login.html', context)
    return render(request, 'users/login_page.html', context)


@login_required(login_url=reverse_lazy('users:login'))
def profile_view(request):
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

    recommended_products = Product.objects.filter().order_by('-created_at')[:3]
    latest_order = Order.objects.filter(user=request.user).order_by('-created_at').first()

    context = {
        'form': form,
        'user': request.user,
        'recommended_products': recommended_products,
        'latest_order': latest_order,
    }

    if request.headers.get('HX-Request'):
        return TemplateResponse(request, 'users/profile.html', context)
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
    return TemplateResponse(request, 'users/partials/order_history.html', {'orders': orders})


@login_required(login_url=reverse_lazy('users:login'))
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'items__product_size__size'),
        id=order_id,
        user=request.user
    )
    return TemplateResponse(request, 'users/partials/order_detail.html', {'order': order})
