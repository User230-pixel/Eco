import ipaddress
import json
import logging
import threading
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from yookassa import Configuration
from yookassa import Payment as YookassaPayment

from shop.models import Order

from .services import (
    PaymentError,
    cancel_order,
    mark_order_paid,
    send_order_paid_email,
)
from main.views.views import get_client_ip

Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

logger = logging.getLogger(__name__)

YOOKASSA_WEBHOOK_NETWORKS = [
    ipaddress.ip_network("185.32.187.0/24"),
]

class _Rollback(Exception):
    pass

def _is_yookassa_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in YOOKASSA_WEBHOOK_NETWORKS)


def _async_order_email(subject, message, recipients):
    """Фоновая отправка письма, чтобы не блокировать вебхук."""
    def _worker():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=recipients,
                fail_silently=False,
            )
        except Exception as mail_err:
            logger.error("Ошибка фоновой отправки почты: %s", mail_err)

    threading.Thread(target=_worker, daemon=True).start()


@csrf_exempt
@require_POST
def yookassa_webhook(request):
    client_ip = get_client_ip(request)
    if not _is_yookassa_ip(client_ip):
        logger.warning("Вебхук с недопустимого IP: %s", client_ip)
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body)
        payment_id = payload["object"]["id"]
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Некорректный вебхук: %s", e)
        return HttpResponse(status=400)

    try:
        payment = YookassaPayment.find_one(payment_id)
    except Exception as e:
        logger.error("Ошибка запроса к ЮKassa для платежа %s: %s", payment_id, e)
        return HttpResponse(status=200)

    metadata = payment.metadata or {}
    order_id = metadata.get("order_id")
    user_id = metadata.get("user_id")

    if not order_id:
        logger.warning("В metadata платежа %s нет order_id", payment_id)
        return HttpResponse(status=200)

    order = Order.objects.filter(id=order_id).select_related("user").first()
    if not order:
        logger.error("Заказ %s не найден (платёж %s)", order_id, payment_id)
        return HttpResponse(status=200)

    if user_id and str(order.user_id) != str(user_id):
        logger.warning(
            "user_id в metadata (%s) не совпадает с владельцем заказа %s (%s)",
            user_id, order_id, order.user_id,
        )
        return HttpResponse(status=200)

    if payment.status == "succeeded":
        try:
            changed = mark_order_paid(order, payment)
        except PaymentError as e:
            logger.error("Оплата заказа %s: %s", order_id, e)
            return HttpResponse(status=200)
        except Exception as e:
            logger.error("Транзакция для заказа %s: %s", order_id, e, exc_info=True)
            return HttpResponse(status=500)

        if changed:
            send_order_paid_email(order)

    elif payment.status == "canceled":
        try:
            cancel_order(order)
        except Exception as e:
            logger.error("Ошибка отмены заказа %s: %s", order_id, e, exc_info=True)
            return HttpResponse(status=500)

    else:
        logger.info("Необрабатываемый статус %s для заказа %s", payment.status, order_id)

    return HttpResponse(status=200)


@login_required(login_url="main:get_login_form")
def payment_success(request):
    payment_id = request.GET.get("payment_id") or request.session.get("last_payment_id")
    if not payment_id:
        logger.error("payment_success: не передан payment_id")
        return redirect("shop:payment_fail")

    try:
        payment = YookassaPayment.find_one(payment_id)
    except Exception as e:
        logger.error("payment_success: ошибка ЮKassa для %s: %s", payment_id, e)
        return redirect("shop:payment_fail")

    if payment.status != "succeeded":
        return redirect("shop:payment_fail")

    order = (
        Order.objects
        .select_related("user")
        .filter(yookassa_payment_id=payment_id)
        .first()
    )
    if not order:
        order_id = (payment.metadata or {}).get("order_id")
        order = (
            Order.objects
            .select_related("user")
            .filter(id=order_id)
            .first()
        )

    if not order or order.user_id != request.user.id:
        logger.warning(
            "payment_success: заказ не найден или чужой (payment=%s, user=%s)",
            payment_id, request.user.id,
        )
        return HttpResponseForbidden("Платёж недоступен")

    try:
        changed = mark_order_paid(order, payment)
    except PaymentError as e:
        logger.error("payment_success: %s", e)
        return redirect("shop:payment_fail")
    except Exception as e:
        logger.error("payment_success: транзакция для %s: %s", order.id, e, exc_info=True)
        messages.error(request, "Ошибка обработки платежа. Поддержка уведомлена.")
        return redirect("shop:payment_fail")

    if changed:
        send_order_paid_email(order)

    request.session.pop("last_payment_id", None)
    return render(request, "shop/order_success.html", {"order": order})


@login_required(login_url="main:get_login_form")
def payment_fail(request):
    return render(request, "shop/payment_fail.html")