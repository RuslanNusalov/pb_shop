from .models import Cart


def cart_processor(request):
    # Создаем сессию, если её нет
    if not request.session.session_key:
        request.session.create()

    # ✅ Распаковываем кортеж: cart — это объект, created — булево значение
    cart, created = Cart.objects.get_or_create(
        session_key=request.session.session_key
    )

    return {
        'cart_total_items': cart.total_items,   # ✅ Теперь обращаемся к объекту Cart
        'cart_subtotal': cart.subtotal,         # ✅
    }