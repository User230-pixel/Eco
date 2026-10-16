from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST

from shop.models import Order

from main.views.views import driver_required


DRIVER_ALLOWED_TRANSITIONS = {
    "pending":    ["shipped"],
    "processing": ["shipped"],
    "shipped":    ["delivered"],
}


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

    order.status = new_status
    order.save(update_fields=["status"])

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