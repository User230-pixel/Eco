from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

from ..models import (
    Product,
    Cart,
    CartItem,
    OrderItem,
    Order,
)

from main.models import Profile
from .services import (
    InsufficientStock,
    cancel_order,
    fail_unpaid_order,
    reserve_order_stock,
)

from shop.views.views import (
    get_cached_categories
)

from main.views.views import (
    rate_limit
)

from django.contrib import messages
from django.db import transaction

from yookassa import Payment as YookassaPayment
from yookassa.domain.exceptions import ApiError
from django.urls import reverse

import logging

from django.db.models import Sum

from django.views.decorators.http import require_POST

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
@require_POST
@rate_limit('checkout', 35, 300)
def checkout(request):
    order = None
    try:
        with transaction.atomic():
            cart = Cart.objects.select_for_update().get(user=request.user)
            order = (
                Order.objects.select_for_update()
                .filter(user=request.user, status="awaiting_payment")
                .order_by("-created_at")
                .first()
            )

            if order is None:
                cart_items = list(
                    cart.items.filter(is_selected=True)
                    .select_related("product")
                    .order_by("product_id", "id")
                )
                if not cart_items:
                    messages.warning(request, "Вы не выбрали ни одного товара.")
                    return redirect("shop:cart_detail")

                profile, _ = Profile.objects.get_or_create(user=request.user)
                order = Order.objects.create(
                    user=request.user,
                    status="awaiting_payment",
                    total_price=0,
                    delivery_address=profile.address or "",
                )

                total_sum = 0
                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        price=item.product.price,
                        quantity=item.quantity,
                    )
                    total_sum += item.product.price * item.quantity

                order.total_price = total_sum
                order.save(update_fields=["total_price"])

            reserve_order_stock(order)
    except InsufficientStock as e:
        messages.error(request, str(e))
        return redirect('shop:cart_detail')
    except Exception as e:
        logger.error("Ошибка создания заказа для user=%s: %s", request.user.id, e, exc_info=True)
        messages.error(request, "Ошибка оформления заказа. Обратитесь в поддержку.")
        return redirect('shop:cart_detail')

    if order.yookassa_payment_id:
        try:
            payment = YookassaPayment.find_one(order.yookassa_payment_id)
        except Exception as e:
            logger.error(
                "Ошибка получения платежа %s для order=%s: %s",
                order.yookassa_payment_id,
                order.id,
                e,
                exc_info=True,
            )
            messages.error(request, "Не удалось проверить платёж. Попробуйте ещё раз позже.")
            return redirect("shop:cart_detail")

        if payment.status == "succeeded":
            request.session["last_payment_id"] = payment.id
            return redirect("shop:payment_success")
        if payment.status == "canceled":
            cancel_order(order)
            messages.error(request, "Предыдущий платёж отменён. Повторите оформление заказа.")
            return redirect("shop:cart_detail")

        confirmation_url = getattr(
            getattr(payment, "confirmation", None),
            "confirmation_url",
            None,
        )
        if confirmation_url:
            return redirect(confirmation_url)

        messages.error(request, "Платёж ещё обрабатывается. Попробуйте позже.")
        return redirect("shop:cart_detail")

    success_url = request.build_absolute_uri(reverse('shop:payment_success'))
    idempotence_key = f"eco-order-{order.pk}"

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
    except ApiError as e:
        status_code = getattr(e, "HTTP_CODE", 0)
        logger.error(
            "Ошибка создания платежа в ЮKassa для order=%s (HTTP %s): %s",
            order.id,
            status_code,
            e,
            exc_info=True,
        )
        if 400 <= status_code < 500 and status_code not in (409, 429):
            fail_unpaid_order(order)
            messages.error(
                request,
                "ЮKassa отклонила создание платежа. Резерв товара снят; попробуйте позже.",
            )
        else:
            messages.error(
                request,
                "Не удалось подтвердить создание платежа. Повторите оформление: "
                "заказ и резерв товара сохранены, повторный запрос не создаст второй платёж.",
            )
        return redirect("shop:cart_detail")
    except Exception as e:
        logger.error("Ошибка создания платежа в ЮKassa для order=%s: %s", order.id, e, exc_info=True)
        messages.error(
            request,
            "Не удалось подтвердить создание платежа. Повторите оформление: "
            "заказ и резерв товара сохранены, повторный запрос не создаст второй платёж.",
        )
        return redirect('shop:cart_detail')

    order.yookassa_payment_id = payment.id
    order.save(update_fields=["yookassa_payment_id"])

    request.session['last_payment_id'] = payment.id
    return redirect(payment.confirmation.confirmation_url)

@require_POST
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

@require_POST
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

@require_POST
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

@require_POST
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
