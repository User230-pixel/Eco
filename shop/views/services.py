import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F

from shop.models import CartItem, Order, Product
from main.models import Profile

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """A payment could not be applied to its order."""


class InsufficientStock(Exception):
    """Raised when an order cannot reserve all requested inventory."""


def fail_unpaid_order(order):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != "awaiting_payment":
            return False

        if order.stock_reserved:
            for item in order.items.all():
                Product.objects.filter(pk=item.product_id).update(
                    stock=F("stock") + item.quantity
                )
            order.stock_reserved = False

        order.status = "failed"
        order.save(update_fields=["status", "stock_reserved"])
        return True


def reserve_order_stock(order):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.stock_reserved:
            return

        items = order.items.select_related("product").order_by("product_id", "id")
        for item in items:
            reserved = Product.objects.filter(
                pk=item.product_id,
                stock__gte=item.quantity,
            ).update(stock=F("stock") - item.quantity)
            if not reserved:
                product = Product.objects.filter(pk=item.product_id).only("stock").first()
                available = product.stock if product else 0
                raise InsufficientStock(
                    f"Недостаточно товара «{item.product.name}». Доступно: {available} шт."
                )

        order.stock_reserved = True
        order.save(update_fields=["stock_reserved"])


def mark_order_paid(order, payment) -> bool:
    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .select_related("user")
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )

        if order.status != "awaiting_payment":
            logger.info("Заказ %s не в awaiting_payment (status=%s), пропускаем",
                        order.id, order.status)
            return False

        if not order.stock_reserved:
            try:
                reserve_order_stock(order)
            except InsufficientStock as e:
                raise PaymentError(str(e)) from e
            order.stock_reserved = True

        product_ids = [i.product_id for i in order.items.all()]
        CartItem.objects.filter(
            cart__user=order.user, product_id__in=product_ids
        ).delete()

        if not order.delivery_address:
            profile, _ = Profile.objects.get_or_create(user=order.user)
            order.delivery_address = getattr(profile, "address", "") or ""

        order.status = "pending"
        order.yookassa_payment_id = payment.id
        order.save(update_fields=[
            "status",
            "delivery_address",
            "yookassa_payment_id",
            "stock_reserved",
        ])
        return True


def cancel_order(order) -> bool:
    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .prefetch_related("items__product")
            .get(pk=order.pk)
        )
        if order.status in ("cancelled", "failed", "delivered"):
            return False

        if order.status in ("processing", "shipped"):
            logger.warning(
                "Попытка отменить заказ %s в статусе %s", order.id, order.status
            )
            return False

        if order.stock_reserved or order.status == "pending":
            for item in order.items.all():
                Product.objects.filter(id=item.product_id).update(
                    stock=F("stock") + item.quantity
                )
            order.stock_reserved = False
        order.status = "cancelled"
        order.save(update_fields=["status", "stock_reserved"])
        return True


def send_order_paid_email(order):
    items_text = "".join(
        f"• {item.product.name} — {item.quantity} шт. | {item.price} руб.\n"
        for item in order.items.select_related("product")
    )
    profile, _ = Profile.objects.get_or_create(user=order.user)
    phone = (
        getattr(order.user, "phone_number", "")
        or getattr(profile, "phone", "")
        or "Не указан"
    )
    message = (
        f"Новый заказ №{order.id} от: {order.user.username}\n"
        f"Адрес доставки: {order.delivery_address}\n"
        f"Телефон: {phone}\n\n"
        f"Список товаров:\n{items_text}\n"
        f"Итого оплачено: {order.total_price} руб."
    )
    recipients = [settings.EMAIL_HOST_USER]
    if order.user.email:
        recipients.append(order.user.email)
    send_mail(
        subject=f"Алишоп: Оплачен заказ №{order.id}",
        message=message,
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=recipients,
        fail_silently=False,
    )