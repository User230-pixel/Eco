from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
import json
from django.contrib.messages import get_messages

from ..models import (
    Product,
    Cart,
    CartItem,
    OrderItem,
    Order,
)

from main.models import Profile
from .payments import _Rollback

from shop.views.views import (
    get_cached_categories
)

from main.views.views import (
    rate_limit
)

from .payments import (
    _async_order_email,
)

from django.contrib import messages
from django.conf import settings
from django.db import transaction, IntegrityError

import uuid
from yookassa import Payment as YookassaPayment
from django.urls import reverse

from django.db.models import F

import logging
import threading

from django.db.models import Sum

logger = logging.getLogger(__name__)

@login_required(login_url='main:get_login_form')
def toggle_select(request):
    """Переключает флаг выбора товара. Сюда можно добавить заголовок HX-Trigger для фронтенда"""
    if not request.headers.get("HX-Request"):
        return HttpResponse(status=400)

    product_id = request.POST.get("selected_products")
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)

    cart_item.is_selected = not cart_item.is_selected
    cart_item.save()

    return render(request, "shop/partials/_cart_totals.html", {"cart": cart})

@login_required(login_url='main:get_login_form')
def cart_detail(request):
    """Просмотр корзины со всеми товарами"""
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related("product")

    total_quantity = cart.items.aggregate(total=Sum('quantity'))['total'] or 0

    return render(
        request,
        "shop/cart_detail.html",
        {
            "cart": cart, 
            "cart_items": cart_items, 
            "total_quantity": total_quantity,
            "categories": get_cached_categories()
        },
    )

@login_required(login_url='main:get_login_form')
@rate_limit('cart', 30, 60)
def add_to_cart(request, id, slug):
    """Добавление товара в корзину с проверкой остатка на складе"""
    product = get_object_or_404(Product, id=id, slug=slug)
    cart, created = Cart.objects.get_or_create(user=request.user)

    if request.method == "POST":
        try:
            quantity = int(request.POST.get("quantity", 1))
            if quantity < 1:
                quantity = 1
        except ValueError:
            quantity = 1

        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=id)
            
            cart_item = CartItem.objects.select_for_update().filter(
                cart=cart, product=product
            ).first()
            current_quantity = cart_item.quantity if cart_item else 0
            total_requested = current_quantity + quantity

            if total_requested <= product.stock:
                if not cart_item:
                    cart_item = CartItem(cart=cart, product=product)

                cart_item.quantity = total_requested
                cart_item.is_selected = True
                cart_item.save()
                messages.success(request, f"Товар {product.name} добавлен в корзину.")
            else:
                messages.error(
                    request,
                    f"Нельзя добавить столько шт. На складе доступно всего {product.stock} шт.",
                )

    return redirect(request.META.get("HTTP_REFERER", "shop:product_list"))

@login_required(login_url='main:get_login_form')
@rate_limit('checkout', 35, 300)
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = cart.items.filter(is_selected=True).select_related('product')

    if not cart_items.exists():
        messages.warning(request, "Вы не выбрали ни одного товара.")
        return redirect('shop:cart_detail')

    profile, _ = Profile.objects.get_or_create(user=request.user)
    address = getattr(profile, "address", "") or ""

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                status="awaiting_payment",
                total_price=0,
                delivery_address=address,
            )

            total_sum = 0
            for item in cart_items:
                product = (
                    Product.objects
                    .select_for_update()
                    .get(id=item.product_id)
                )
                if product.stock < item.quantity:
                    messages.error(
                        request,
                        f"Товара {product.name} нет в наличии в нужном количестве. "
                        f"Доступно: {product.stock} шт.",
                    )
                    raise _Rollback()

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    price=product.price,
                    quantity=item.quantity,
                )
                total_sum += product.price * item.quantity

            order.total_price = total_sum
            order.save(update_fields=["total_price"])
    except _Rollback:
        return redirect('shop:cart_detail')
    except Exception as e:
        logger.error("Ошибка создания заказа для user=%s: %s", request.user.id, e, exc_info=True)
        messages.error(request, "Ошибка оформления заказа. Обратитесь в поддержку.")
        return redirect('shop:cart_detail')

    success_url = request.build_absolute_uri(reverse('shop:payment_success'))
    idempotence_key = str(uuid.uuid4())

    try:
        payment = YookassaPayment.create(
            {
                "amount": {"value": f"{order.total_price:.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": success_url},
                "capture": True,
                "description": f"Заказ №{order.id}",
                "metadata": {
                    "order_id": order.id,
                    "user_id": request.user.id,
                },
            },
            idempotence_key,
        )
    except Exception as e:
        logger.error("Ошибка создания платежа в ЮKassa для order=%s: %s", order.id, e, exc_info=True)
        order.status = "failed"
        order.save(update_fields=["status"])
        messages.error(request, "Ошибка платежной системы. Пожалуйста, обратитесь в поддержку.")
        return redirect('shop:cart_detail')

    order.yookassa_payment_id = payment.id
    order.save(update_fields=["yookassa_payment_id"])

    request.session['last_payment_id'] = payment.id
    return redirect(payment.confirmation.confirmation_url)


@login_required(login_url='main:get_login_form')
def increase_cart_item(request, item_id):
    """Увеличить количество товара на 1 с проверкой остатка на складе"""
    with transaction.atomic():
        cart_item = get_object_or_404(
            CartItem.objects.select_for_update().select_related('product'), 
            id=item_id, 
            cart__user=request.user
        )
        
        product = Product.objects.select_for_update().get(id=cart_item.product.id)
        
        if cart_item.quantity + 1 <= product.stock:
            cart_item.quantity += 1
            cart_item.save()
            messages.success(request, f'Количество товара "{product.name}" увеличено')
        else:
            messages.error(request, f'Нельзя добавить больше! На складе доступно всего {product.stock} шт.')

    return redirect("shop:cart_detail")

@login_required(login_url='main:get_login_form')
def decrease_cart_item(request, item_id):
    """Уменьшить количество товара на 1"""
    with transaction.atomic():
        cart_item = get_object_or_404(
            CartItem.objects.select_for_update().select_related('product'), 
            id=item_id, 
            cart__user=request.user
        )

        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
            messages.info(request, f'Количество товара "{cart_item.product.name}" уменьшено')
        else:
            product_name = cart_item.product.name
            cart_item.delete()
            messages.info(request, f'Товар "{product_name}" удален из корзины')

    return redirect("shop:cart_detail")

@login_required(login_url='main:get_login_form')
def remove_from_cart(request, item_id):
    """Полностью удалить товар из корзины"""
    with transaction.atomic():
        cart_item = get_object_or_404(
            CartItem.objects.select_for_update().select_related('product'), 
            id=item_id, 
            cart__user=request.user
        )
        product_name = cart_item.product.name
        cart_item.delete()
        messages.success(request, f'Товар "{product_name}" удален из корзины')
    
    return redirect("shop:cart_detail")

@login_required(login_url='main:get_login_form')
def clear_cart(request):
    """Очистить всю корзину"""
    with transaction.atomic():
        cart = get_object_or_404(Cart, user=request.user)
        
        if cart.items.exists():
            cart.items.all().delete()
            messages.success(request, "Корзина успешно очищена")
        else:
            messages.warning(request, "Корзина уже пуста")

    return redirect("shop:cart_detail")
