from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse, NoReverseMatch
from shop.models import Order
from django.db import transaction

from main.views.views import driver_required, send_notifications


DRIVER_ALLOWED_TRANSITIONS = {
    "pending":    ["shipped"],
    "processing": ["shipped"],
    "shipped":    ["delivered"],
}

STATUS_NOTIFICATIONS = {
    "shipped": {
        "title": "Заказ отправлен",
        "message": "Ваш заказ №{order_id} передан в доставку.",
        "notification_type": "info",
    },
    "delivered": {
        "title": "Заказ доставлен",
        "message": "Ваш заказ №{order_id} успешно доставлен. Спасибо!",
        "notification_type": "success",
    },
}

def _get_order_url(order):
    try:
        return reverse("shop:order_detail", args=[order.id])
    except NoReverseMatch:
        return ""


@driver_required
@require_POST
def driver_update_order_status(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")

    valid_statuses = {key for key, _ in Order.STATUS_CHOICES}
    if new_status not in valid_statuses:
        return HttpResponseBadRequest("Неизвестный статус")

    allowed = DRIVER_ALLOWED_TRANSITIONS.get(order.status, [])
    if new_status not in allowed:
        if request.headers.get("HX-Request"):
            return render(request, "main/notification.html", {
                "message": f"Нельзя перевести заказ из «{order.get_status_display()}» "
                           f"в «{dict(Order.STATUS_CHOICES)[new_status]}»",
                "type": "error",
            }, status=400)

        messages.error(
            request,
            f"Нельзя перевести заказ из «{order.get_status_display()}» "
            f"в «{dict(Order.STATUS_CHOICES)[new_status]}»"
        )
        return redirect("main:driver_orders")

    with transaction.atomic():
        order.status = new_status
        order.save(update_fields=["status"])
        notif = STATUS_NOTIFICATIONS.get(new_status)

        if notif:
            transaction.on_commit(lambda: send_notifications(
                user=order.user,
                title=notif["title"],
                message=notif["message"].format(order_id=order.id),
                notification_type=notif["notification_type"],
                url=_get_order_url(order),
            ))

    if request.headers.get("HX-Request"):
        return render(request, "main/partials/_driver_order_row.html", {
            "order": order,
        })

    messages.success(request, f"Статус заказа {order.id} обновлён.")
    return redirect("main:driver_orders")

@driver_required
def driver_orders(request):
    orders = Order.objects.filter(
        status__in=["pending", "processing", "shipped"]
    ).select_related("user").order_by("-created_at")

    template = (
        "main/partials/_driver_orders_list.html"
        if request.headers.get("HX-Request")
        else "main/driver_orders.html"
    )
    return render(request, template, {"orders": orders})