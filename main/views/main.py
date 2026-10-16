from django.shortcuts import render
from shop.models import Cart


def index(request):
    """Страница-навигатор"""
    cart_items_count = 0
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items_count = cart.get_total_quantity()
        except Cart.DoesNotExist:
            pass

    context = {
        'cart_items_count': cart_items_count,
    }
    return render(request, 'main/index.html', context)


def jobs(request):
    return render(request, 'main/jobs.html')