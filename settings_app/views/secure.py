import logging

from django.conf import settings
from django.contrib import messages

from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from main.models import CustomUser
from settings_app.models import VerificationCode
from django.contrib.auth import logout
from datetime import timedelta
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from django.contrib.auth import update_session_auth_hash

from main.views.send import (
    send_verification_code_to_email,
)

from main.views.views import (
    send_notifications
)

from main.views.auth import (
    _safe_redirect
)
from settings_app.views.views import send_verification_code_to_phone

from main.views.views import get_client_ip


logger = logging.getLogger(__name__)

CODE_ATTEMPT_WINDOW = 60 * 15
SMS_RESEND_INTERVAL = 60
SMS_MAX_PER_HOUR = 3

NOTIFY_COOLDOWN_HOUR = 3600
NOTIFY_COOLDOWN_DAY = 86400
FAILED_LOGIN_THRESHOLD = 3


def smart_password_reset(request):
    error_message = None

    user_ip = get_client_ip(request)
    ip_limit_key = f"reset_page_limit_{user_ip}"

    code_sent = request.session.get("reset_password_flow", False)

    if request.method == "POST":
        cache.add(ip_limit_key, 0, NOTIFY_COOLDOWN_HOUR)
        page_visits = cache.incr(ip_limit_key)

        if page_visits > settings.MAX_PAGE_VISITS_PER_HOUR:
            return render(request, "settings_app/password_reset.html", {
                "code_sent": False,
                "error_message": "Вы исчерпали лимит запросов на сброс пароля. Доступ заблокирован на 1 час.",
                "is_blocked": True,
            })

        if not code_sent:
            email = request.POST.get("email", "").strip()
            try:
                CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                messages.success(request, "Если такой email зарегистрирован, код отправлен.")
                return redirect(request.path)

            cache.delete(f"reset_attempts_{email}")
            send_verification_code_to_email(email, purpose="reset")

            request.session["reset_password_email"] = email
            request.session["reset_password_flow"] = True
            request.session.modified = True

            messages.success(request, "Код восстановления отправлен на ваш Email!")
            return redirect(request.path)

        else:
            user_code = request.POST.get("code", "").strip()
            new_password = request.POST.get("password", "")
            reset_email = request.session.get("reset_password_email")

            if not reset_email:
                messages.error(request, "Сессия истекла. Начните заново.")
                request.session["reset_password_flow"] = False
                return redirect(request.path)

            attempts_key = f"reset_attempts_{reset_email}"

            cache.add(attempts_key, 0, 300)
            attempts = cache.incr(attempts_key)

            if attempts > settings.MAX_VERIFICATION_ATTEMPTS:
                error_message = "Слишком много неудачных попыток. Запросите новый код."
                context = {"code_sent": code_sent, "error_message": error_message, "email": reset_email}
                return render(request, "settings_app/password_reset.html", context)

            try:
                user_for_notify = None
                with transaction.atomic():
                    verification = VerificationCode.objects.select_for_update().filter(
                        email=reset_email,
                        purpose="reset",
                        is_used=False,
                        expires_at__gt=timezone.now(),
                    ).first()

                    if verification and verification.check_code(user_code):
                        user = CustomUser.objects.get(email=reset_email)

                        try:
                            validate_password(new_password, user=user)
                        except ValidationError as e:
                            for msg in e.messages:
                                messages.error(request, msg)
                            return render(request, "settings_app/password_reset.html", {
                                "code_sent": code_sent,
                                "error_message": " ".join(e.messages),
                                "email": reset_email,
                            })

                        user.set_password(new_password)
                        user.save(update_fields=["password"])

                        verification.is_used = True
                        verification.save(update_fields=["is_used"])
                        cache.delete(attempts_key)

                        user_for_notify = user

                    else:
                        remains = settings.MAX_VERIFICATION_ATTEMPTS - attempts
                        if remains > 0:
                            error_message = f"Неверный или истекший код. Осталось попыток: {remains}."
                        else:
                            error_message = "Слишком много неудачных попыток. Запросите новый код."

                        context = {"code_sent": code_sent, "error_message": error_message, "email": reset_email}
                        return render(request, "settings_app/password_reset.html", context)

                if user_for_notify is not None:
                    send_notifications(
                        user=user_for_notify,
                        title="Пароль изменён",
                        message="Пароль от вашего аккаунта был успешно изменён.",
                        notification_type="success",
                    )
                    send_notifications(
                        user=user_for_notify,
                        title="Внимание!",
                        message="Если это были не вы — немедленно свяжитесь с поддержкой.",
                        notification_type="warning",
                    )

                request.session.pop("reset_password_email", None)
                request.session.pop("reset_password_flow", None)
                request.session.modified = True

                messages.success(request, "Пароль успешно изменен! Войдите.")
                return redirect("main:index")

            except Exception as e:
                logger.error("Ошибка верификации сброса пароля: %s", e)
                error_message = "Ошибка сервера. Попробуйте снова."
                context = {"code_sent": code_sent, "error_message": error_message, "email": reset_email}
                return render(request, "settings_app/password_reset.html", context)

    reset_email = request.session.get("reset_password_email", "")
    context = {
        "code_sent": code_sent,
        "error_message": error_message,
        "email": reset_email,
    }
    return render(request, "settings_app/password_reset.html", context)


@require_POST
def resend_password_reset_code(request):
    email = request.session.get("reset_password_email")

    if not email:
        messages.error(request, "Сессия истекла. Начните сброс пароля заново.")
        request.session["reset_password_flow"] = False
        return redirect("settings_app:smart_password_reset")

    last_code = VerificationCode.objects.filter(
        email=email,
        purpose="reset",
        is_used=False,
        created_at__gte=timezone.now() - timedelta(minutes=4, seconds=30),
    ).first()

    if last_code:
        messages.error(request, "Код уже был отправлен. Пожалуйста, подождите.")
        return redirect("settings_app:smart_password_reset")

    resend_key = f"resend_password_code_{email}"

    cache.add(resend_key, 0, 3600)
    resend_count = cache.incr(resend_key)

    if resend_count > 3:
        messages.error(request, "Вы исчерпали лимит повторных отправок. Попробуйте через час.")
    else:
        VerificationCode.objects.filter(
            email=email, purpose="reset", is_used=False,
        ).update(is_used=True)
        send_verification_code_to_email(email, purpose="reset")
        messages.success(request, "Новый код восстановления успешно отправлен!")

    return redirect("settings_app:smart_password_reset")


@login_required
def change_phone_view(request):
    phone_flow_active = request.session.get("change_phone_flow", False)
    pending_phone = request.session.get("pending_phone")

    if request.method == "POST":

        if "submit_phone" in request.POST:
            new_phone = request.POST.get("new_phone_input")

            resend_key = f"resend_phone_code_{request.user.id}"
            resend_count = cache.get(resend_key, 0)

            if resend_count >= 3:
                messages.error(request, "Вы исчерпали лимит отправок СМС. Попробуйте через час.")
                return redirect("settings_app:change_phone")

            if CustomUser.objects.filter(phone_number=new_phone).exists():
                messages.error(request, "Этот номер телефона уже привязан к другому аккаунту.")
                return redirect("settings_app:change_phone")

            VerificationCode.objects.filter(
                phone_number=new_phone,
                purpose="change_phone",
                is_used=False,
            ).update(is_used=True)

            send_verification_code_to_phone(new_phone, purpose="change_phone", user=request.user)

            cache.delete(f"change_phone_attempts_user:{request.user.id}")

            request.session["change_phone_flow"] = True
            request.session["pending_phone"] = new_phone
            cache.set(resend_key, resend_count + 1, NOTIFY_COOLDOWN_HOUR)

            messages.success(request, f"Код подтверждения отправлен на номер {new_phone}!")
            return redirect("settings_app:change_phone")

        elif "submit_code" in request.POST:
            entered_code = request.POST.get("entered_code", "").strip()

            user_attempts_key = f"change_phone_attempts_user:{request.user.id}"
            user_attempts = cache.get(user_attempts_key, 0)

            if user_attempts >= settings.MAX_VERIFICATION_ATTEMPTS:
                notify_key = f"change_phone_block_notified:{request.user.id}"
                if not cache.get(notify_key):
                    send_notifications(
                        user=request.user,
                        title="Подозрительная активность",
                        message="Зафиксировано слишком много неудачных попыток смены номера телефона. Если это были не вы — смените пароль.",
                        notification_type="warning",
                    )
                    cache.set(notify_key, 1, NOTIFY_COOLDOWN_HOUR)

                messages.error(request, "Слишком много попыток. Запросите новый код.")
                return redirect("settings_app:change_phone")

            valid_code = VerificationCode.objects.filter(
                user=request.user,
                phone_number=pending_phone,
                purpose="change_phone",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if valid_code and valid_code.check_code(entered_code):
                valid_code.is_used = True
                valid_code.save(update_fields=["is_used"])
                cache.delete(user_attempts_key)

                current_user = request.user
                current_user.phone_number = pending_phone
                current_user.save(update_fields=["phone_number"])

                send_notifications(
                    user=current_user,
                    title="Номер телефона изменён",
                    message=f"К вашему аккаунту привязан новый номер: {pending_phone}.",
                    notification_type="success",
                )

                send_notifications(
                    user=current_user,
                    title="Внимание!",
                    message=f"Если это были не вы — немедленно смените пароль.",
                    notification_type="warning",
                )

                request.session["change_phone_flow"] = False
                request.session.pop("pending_phone", None)

                messages.success(request, "Номер телефона успешно изменен!")
            else:
                cache.add(user_attempts_key, 0, CODE_ATTEMPT_WINDOW)
                user_attempts = cache.incr(user_attempts_key)
                if user_attempts >= settings.MAX_VERIFICATION_ATTEMPTS:
                    notify_key = f"change_phone_block_notified:{request.user.id}"
                    if not cache.get(notify_key):
                        send_notifications(
                            user=request.user,
                            title="Подозрительная активность",
                            message="Зафиксировано слишком много неудачных попыток смены номера телефона. Если это были не вы — смените пароль.",
                            notification_type="warning",
                        )
                        cache.set(notify_key, 1, NOTIFY_COOLDOWN_HOUR)

                    messages.error(request, "Слишком много попыток. Запросите новый код.")
                else:
                    messages.error(request, "Неверный код подтверждения. Попробуйте еще раз.")
                return redirect("settings_app:change_phone")

            return redirect("main:cabinet")

    return render(request, "settings_app/change_phone.html", {
        "phone_flow_active": phone_flow_active,
        "pending_phone": pending_phone,
    })


def logout_view(request):
    previous_url = request.session.get("previous_url", "/")
    logout(request)
    return _safe_redirect(request, previous_url)


@login_required
def change_email_view(request):
    email_flow_active = request.session.get("change_email_flow", False)
    pending_email = request.session.get("pending_email")

    if request.method == "POST":

        if "submit_email" in request.POST:
            new_email = (request.POST.get("new_email_input") or "").strip().lower()

            if not new_email:
                messages.error(request, "Введите новый Email.")
                return redirect("settings_app:edit-email")

            resend_key = f"resend_email_code_{request.user.id}"
            resend_count = cache.get(resend_key, 0)

            if resend_count >= 3:
                messages.error(request, "Вы исчерпали лимит отправок кода. Попробуйте через час.")
                return redirect("settings_app:edit-email")

            if CustomUser.objects.filter(email=new_email).exists():
                messages.error(request, "Этот Email уже привязан к другому аккаунту.")
                return redirect("settings_app:edit-email")

            if new_email == request.user.email:
                messages.error(request, "Этот Email уже привязан к вашему аккаунту.")
                return redirect("settings_app:edit-email")

            VerificationCode.objects.filter(
                email=new_email,
                purpose="change_email",
                is_used=False,
            ).update(is_used=True)

            send_verification_code_to_email(new_email, purpose="change_email")

            cache.delete(f"change_email_attempts_user:{request.user.id}")

            request.session["change_email_flow"] = True
            request.session["pending_email"] = new_email
            cache.set(resend_key, resend_count + 1, NOTIFY_COOLDOWN_HOUR)

            messages.success(request, f"Код подтверждения отправлен на {new_email}!")
            return redirect("settings_app:edit-email")

        elif "submit_code" in request.POST:
            entered_code = request.POST.get("entered_code", "").strip()

            user_attempts_key = f"change_email_attempts_user:{request.user.id}"
            user_attempts = cache.get(user_attempts_key, 0)

            if user_attempts >= settings.MAX_VERIFICATION_ATTEMPTS:
                notify_key = f"change_email_block_notified:{request.user.id}"
                if not cache.get(notify_key):
                    send_notifications(
                        user=request.user,
                        title="Подозрительная активность",
                        message="Зафиксировано слишком много неудачных попыток смены Email. Если это были не вы — смените пароль.",
                        notification_type="warning",
                    )
                    cache.set(notify_key, 1, NOTIFY_COOLDOWN_HOUR)

                messages.error(request, "Слишком много попыток. Запросите новый код.")
                return redirect("settings_app:edit-email")

            with transaction.atomic():
                valid_code = VerificationCode.objects.select_for_update().filter(
                    email=pending_email,
                    purpose="change_email",
                    is_used=False,
                    expires_at__gt=timezone.now(),
                ).first()
                code_is_valid = bool(valid_code and valid_code.check_code(entered_code))

                if code_is_valid:
                    valid_code.is_used = True
                    valid_code.save(update_fields=["is_used"])
                    current_user = request.user
                    current_user.email = pending_email
                    current_user.save(update_fields=["email"])

            if code_is_valid:
                cache.delete(user_attempts_key)

                send_notifications(
                    user=current_user,
                    title="Email изменён",
                    message=f"К вашему аккаунту привязан новый Email: {pending_email}.",
                    notification_type="success",
                )
                send_notifications(
                    user=current_user,
                    title="Внимание!",
                    message="Если это были не вы — немедленно смените пароль.",
                    notification_type="warning",
                )

                request.session["change_email_flow"] = False
                request.session.pop("pending_email", None)

                messages.success(request, "Email успешно изменён!")
            else:
                cache.add(user_attempts_key, 0, CODE_ATTEMPT_WINDOW)
                user_attempts = cache.incr(user_attempts_key)

                if user_attempts >= settings.MAX_VERIFICATION_ATTEMPTS:
                    notify_key = f"change_email_block_notified:{request.user.id}"
                    if not cache.get(notify_key):
                        send_notifications(
                            user=request.user,
                            title="Подозрительная активность",
                            message="Зафиксировано слишком много неудачных попыток смены Email. Если это были не вы — смените пароль.",
                            notification_type="warning",
                        )
                        cache.set(notify_key, 1, NOTIFY_COOLDOWN_HOUR)

                    messages.error(request, "Слишком много попыток. Запросите новый код.")
                else:
                    messages.error(request, "Неверный код подтверждения. Попробуйте ещё раз.")
                return redirect("settings_app:edit-email")

            return redirect("main:cabinet")

    return render(request, "settings_app/change_email.html", {
        "email_flow_active": email_flow_active,
        "pending_email": pending_email,
    })


@require_POST
@login_required
def resend_email_code(request):
    pending_email = request.session.get("pending_email")

    if not pending_email:
        messages.error(request, "Сессия истекла. Начните смену Email заново.")
        request.session["change_email_flow"] = False
        return redirect("settings_app:edit-email")

    last_code = VerificationCode.objects.filter(
        email=pending_email,
        purpose="change_email",
        is_used=False,
        created_at__gte=timezone.now() - timedelta(minutes=4, seconds=30),
    ).first()

    if last_code:
        messages.error(request, "Код уже был отправлен. Пожалуйста, подождите.")
        return redirect("settings_app:edit-email")

    resend_key = f"resend_email_code_{request.user.id}"

    cache.add(resend_key, 0, NOTIFY_COOLDOWN_HOUR)
    resend_count = cache.incr(resend_key)

    if resend_count > 3:
        messages.error(request, "Вы исчерпали лимит повторных отправок. Попробуйте через час.")
    else:
        VerificationCode.objects.filter(
            email=pending_email,
            purpose="change_email",
            is_used=False,
        ).update(is_used=True)

        send_verification_code_to_email(pending_email, purpose="change_email")
        messages.success(request, "Новый код успешно отправлен!")

    return redirect("settings_app:edit-email")

@login_required
@require_POST
def logout_all(request):
    user = request.user
    
    try:
        user.password = make_password(get_random_string(32))
        user.save()
        
        update_session_auth_hash(request, user)
        
        messages.success(request, "Вы успешно вышли со всех остальных устройств.")
    except Exception:
        messages.error(request, "Произошла ошибка при выходе с устройств. Попробуйте позже.")
        
    return redirect("main:cabinet")

@login_required
@require_POST
def delete_account(request):
    user = request.user
    
    try:

        logout(request)

        user.delete()
        
        messages.success(request, "Ваш аккаунт был успешно и безвозвратно удален.")
        return redirect("main:login_submit")
        
    except Exception:
        messages.error(request, "Не удалось удалить аккаунт. Обратитесь в поддержку.")
        return redirect("main:cabinet")