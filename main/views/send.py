import logging
import threading
from datetime import timedelta

import requests as sms_client

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from settings_app.models import VerificationCode
from ..forms import VerificationForm
from .views import guest_only


logger = logging.getLogger(__name__)


def _async_send_code_email(email, code, purpose="register"):
    """Внутренняя фоновая функция для отправки письма (сеть)"""
    subjects = {
        "register": "Ваш код подтверждения регистрации",
        "reset": "Восстановление пароля",
        "change_email": "Подтверждение смены Email",
    }
    messages_map = {
        "register": f"Ваш код для подтверждения регистрации: {code}. Он действует 5 минут.",
        "reset": f"Ваш код для восстановления пароля: {code}. Он действует 5 минут.",
        "change_email": f"Ваш код для смены Email: {code}. Он действует 5 минут.",
    }

    subject = subjects.get(purpose, "Ваш код подтверждения")
    message = messages_map.get(purpose, f"Ваш код: {code}. Он действует 5 минут.")

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error("Ошибка отправки почты (%s): %s", purpose, e)


def _async_send_code_sms(phone_number, code):
    """Фоновая отправка SMS через SMS.ru"""
    try:
        api_id = settings.SMSRU_API_ID
        url = "https://sms.ru/sms/send"
        payload = {
            "api_id": api_id,
            "to": str(phone_number),
            "msg": f"Код подтверждения: {code}",
            "json": 1,
        }
        response = sms_client.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "OK":
                logger.info("СМС отправлено на номер %s", phone_number)
            else:
                logger.error("SMS.ru вернул ошибку: %s", result)
        else:
            logger.error("Сбой связи с SMS.ru. Статус: %s", response.status_code)
    except Exception as e:
        logger.error("Ошибка в фоновом потоке отправки СМС: %s", e)


def _async_order_email(subject, message, recipients):
    """Фоновая отправка чека на почту"""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as mail_err:
        logger.error("Ошибка фоновой отправки почты: %s", mail_err)


def _async_welcome_email(username, email):
    """Фоновая отправка приветственного письма"""
    try:
        send_mail(
            subject="Добро пожаловать!",
            message=f"Привет, {username}! Твой аккаунт успешно активирован. Теперь ты можешь пользоваться сайтом.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error("Ошибка отправки приветственного письма: %s", e)


def send_verification_code_to_email(email, purpose="register"):
    """
    Генерация кода и отправка на email.
    purpose: "register", "reset", "change_email"
    """
    VerificationCode.objects.filter(
        email=email,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    verification, raw_code = VerificationCode.generate(
        purpose=purpose,
        email=email,
    )

    thread = threading.Thread(
        target=_async_send_code_email,
        args=(email, raw_code, purpose),
        daemon=True,
    )
    thread.start()


def get_verify_form(request):
    """Отображение страницы ввода кода (GET)"""
    user_data = request.session.get("verification_data")

    if not user_data:
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect("main:get_register_form").url
            return response
        return redirect("main:get_register_form")

    context = {"verification_form": VerificationForm()}

    if request.headers.get("HX-Request"):
        return render(request, "main/partials/verify_form.html", context)
    return render(request, "main/verify.html", context)


@guest_only
def verify_code_page(request):
    user_data = request.session.get("verification_data")

    if not user_data:
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect("main:get_register_form").url
            return response
        return redirect("main:get_register_form")

    form = VerificationForm(request.POST or None)
    error_message = None
    attempts_key = f"verify_attempts_{user_data.get('email', 'unknown')}"

    if request.method == "POST":
        if form.is_valid():
            cache.add(attempts_key, 0, 300)
            attempts = cache.incr(attempts_key)

            if attempts > settings.MAX_VERIFICATION_ATTEMPTS:
                error_message = "Слишком много неудачных попыток. Запросите новый код."
                context = {"verification_form": form, "error_message": error_message}
                return render(request, "main/verify.html", context)

            input_code = form.cleaned_data["code"]

            try:
                with transaction.atomic():
                    verification = VerificationCode.objects.filter(
                        email=user_data["email"],
                        purpose="register",
                        is_used=False,
                        expires_at__gt=timezone.now(),
                    ).first()

                    if verification and verification.check_code(input_code):
                        verification.is_used = True
                        verification.save(update_fields=["is_used"])
                        cache.delete(attempts_key)

                        if request.headers.get("HX-Request"):
                            response = HttpResponse()
                            response["HX-Redirect"] = redirect("main:verify_phone_page").url
                            return response
                        return redirect("main:verify_phone_page")

                    else:
                        error_message = "Неверный или истекший код."
                        context = {"verification_form": form, "error_message": error_message}
                        return render(request, "main/verify.html", context)

            except Exception as e:
                logger.error("Ошибка верификации: %s", e)
                error_message = "Ошибка сервера. Попробуйте снова."
                context = {"verification_form": form, "error_message": error_message}
                return render(request, "main/verify.html", context)

    context = {
        "verification_form": form,
        "error_message": error_message,
    }
    return render(request, "main/verify.html", context)


@require_POST
def resend_verification_code(request):
    """Повторная отправка кода регистрации"""
    user_data = request.session.get("verification_data")

    if not user_data:
        messages.error(request, "Сессия истекла.")
        return redirect("main:get_register_form")

    email = user_data["email"]

    last_code = VerificationCode.objects.filter(
        email=email,
        purpose="register",
        is_used=False,
        created_at__gte=timezone.now() - timedelta(minutes=4, seconds=30),
    ).first()

    if last_code:
        messages.error(request, "Код уже отправлен. Подождите 5 минут.")
        return redirect("main:get_verify_form")

    resend_key = f"resend_code_{email}"

    cache.add(resend_key, 0, 3600)
    resend_count = cache.incr(resend_key)

    if resend_count > 3:
        messages.error(request, "Вы исчерпали лимит повторных отправок. Попробуйте через час.")
    else:
        VerificationCode.objects.filter(
            email=email, purpose="register", is_used=False,
        ).update(is_used=True)
        send_verification_code_to_email(email, purpose="register")
        messages.success(request, "Новый код отправлен!")

    return redirect("main:get_verify_form")
