import logging
import threading
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from ..forms import LoginForm, SignUpForm, VerificationForm
from ..models import CustomUser
from settings_app.models import VerificationCode
from .send import (
    send_verification_code_to_email,
    _async_welcome_email,
)

from settings_app.views.verify import (
    send_verification_code_to_phone
)

from .views import guest_only, rate_limit, send_notifications, get_previous_app

logger = logging.getLogger(__name__)

CODE_ATTEMPT_WINDOW = 60 * 15
SMS_RESEND_INTERVAL = 60
SMS_MAX_PER_HOUR = 3

NOTIFY_COOLDOWN_HOUR = 3600
NOTIFY_COOLDOWN_DAY = 86400
FAILED_LOGIN_THRESHOLD = 3

BASE_TEMPLATES = {
    'shop': 'shop/base.html',
    'main': 'main/base.html',
    'blog': 'blog/base.html',
}

def _safe_redirect(request, url, fallback="/"):
    """Редирект только на свой хост, иначе fallback."""
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(url)
    return redirect(fallback)


@guest_only
def get_login_form(request):
    previous_app = get_previous_app(request)
    
    if previous_app == 'shop':
        base_template = 'shop/base.html'
    elif previous_app == 'main':
        base_template = 'main/base.html'
    elif previous_app == 'blog':
        base_template = 'blog/base.html'
    else:
        base_template = 'main/base.html'

    if request.GET.get("next"):
        messages.error(request, "Доступ запрещен. Для просмотра этой страницы необходимо авторизоваться.")

    context = {"login_form": LoginForm(),
               "base_template": base_template,
               }

    if request.headers.get("HX-Request"):
        return render(request, "main/partials/login_form.html", context)

    return render(request, "main/login.html", context)


@guest_only
def get_register_form(request):
    previous_app = get_previous_app(request)
    
    if previous_app == 'shop':
        base_template = 'shop/base.html'
    elif previous_app == 'main':
        base_template = 'main/base.html'
    elif previous_app == 'blog':
        base_template = 'blog/base.html'
    else:
        base_template = 'main/base.html'

    context = {"register_form": SignUpForm(),
               "base_template": base_template,
               }

    if request.headers.get("HX-Request"):
        return render(request, "main/partials/register_form.html", context)

    return render(request, "main/register.html", context)


@rate_limit('login', settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_LIMIT_TIMEOUT)
def login_submit(request):
    previous_url = request.POST.get("next") or request.session.get("previous_url", "/")
    form = LoginForm(data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        user = authenticate(username=username, password=password)

        if user is not None and user.is_active:
            if hasattr(user, "action_points") and user.action_points <= 0:
                block_key = f"action_points_block_notified:{user.id}"
                if not cache.get(block_key):
                    send_notifications(
                        user=user,
                        title="Доступ ограничен",
                        message="Вы исчерпали лимит действий. Доступ к покупкам и продажам заблокирован до следующего месяца.",
                        notification_type="error",
                    )
                    cache.set(block_key, 1, NOTIFY_COOLDOWN_DAY)

                form.add_error(
                    None,
                    "Вы исчерпали лимит действий! Доступ заблокирован до следующего месяца.",
                )
                context = {"login_form": form}
                if request.headers.get("HX-Request"):
                    return render(request, "main/partials/login_form.html", context)
                return render(request, "main/login.html", context)

            login(request, user)

            send_notifications(
                user=user,
                title="Вход в аккаунт",
                message="Вы успешно вошли в аккаунт. Теперь вам доступны покупки, продажи товаров и другие приложения экосистемы.",
                notification_type="success"
            )
            send_notifications(
                user=user,
                title="Внимание!",
                message="Если это были не вы, рекомендуем немедленно сменить пароль.",
                notification_type="warning"
            )

            if request.headers.get("HX-Request"):
                response = HttpResponse()
                response["HX-Redirect"] = _safe_redirect(request, previous_url).url
                return response
            return _safe_redirect(request, previous_url)
        else:
            form.add_error(None, "Неверное имя пользователя или пароль.")

            existing = CustomUser.objects.filter(username=username).first()
            if existing is not None:
                notify_key = f"failed_login_notified:{existing.id}"
                if not cache.get(notify_key):
                    count_key = f"failed_login_count:{existing.id}"
                    cache.add(count_key, 0, NOTIFY_COOLDOWN_HOUR)
                    count = cache.incr(count_key)
                    if count >= FAILED_LOGIN_THRESHOLD:
                        send_notifications(
                            user=existing,
                            title="Неудачные попытки входа",
                            message="Зафиксированы неудачные попытки входа в ваш аккаунт. Если это не вы — смените пароль.",
                            notification_type="warning",
                        )
                        cache.set(notify_key, 1, NOTIFY_COOLDOWN_HOUR)

    context = {"login_form": form}

    if request.headers.get("HX-Request"):
        return render(request, "main/partials/login_form.html", context)
    return render(request, "main/login.html", context)


@rate_limit('register', 5, 3600)
def register_submit(request):
    form = SignUpForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        password = form.cleaned_data["password1"]

        user_data = {
            "username": form.cleaned_data["username"],
            "email": form.cleaned_data["email"],
            "phone_number": str(form.cleaned_data.get("phone_number", "")),
            "password_hash": make_password(password),
        }

        request.session["verification_data"] = user_data
        rotate_token(request)

        send_verification_code_to_email(user_data["email"], purpose="register")

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect("main:get_verify_form").url
            return response
        return redirect("main:get_verify_form")

    context = {"register_form": form}
    if request.headers.get("HX-Request"):
        return render(request, "main/partials/register_form.html", context)
    return render(request, "main/register.html", context)

import time
import threading
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.db import transaction, IntegrityError
from django.core.cache import cache
from django.utils import timezone
from django.http import HttpResponse
from django.conf import settings

# Предполагается, что эти константы импортируются или объявлены в вашем файле:
# SMS_MAX_PER_HOUR, SMS_RESEND_INTERVAL, NOTIFY_COOLDOWN_HOUR

@guest_only
def verify_phone_page(request):
    user_data = request.session.get("verification_data")
    
    # ЖЕСТКАЯ ЗАЩИТА: Проверяем наличие данных И флаг успешного подтверждения Email
    if not user_data or not user_data.get("email_verified"):
        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Redirect"] = redirect("main:get_register_form").url
            return response
        return redirect("main:get_register_form")

    # Уникальные ключи кэша
    email_slug = user_data.get('email', 'unknown')
    phone_slug = user_data.get('phone_number', 'unknown')
    attempts_key = f"verify_phone_attempts_{email_slug}"
    sms_count_key = f"sms_sent_count_{phone_slug}"

    # 1. АТОМАРНЫЙ ИНКРЕМЕНТ И ПРОВЕРКА ПОПЫТОК НА САМОМ ВХОДЕ (Для POST)
    if request.method == "POST":
        try:
            attempts = cache.incr(attempts_key)
        except ValueError:
            # Если ключа в кэше еще не было, incr падает. Инициализируем единицей на 5 минут (300 сек)
            cache.set(attempts_key, 1, 300)
            attempts = 1

        if attempts > settings.MAX_VERIFICATION_ATTEMPTS:
            error_message = "Слишком много неудачных попыток. Запросите код заново."
            return render(request, "main/verify_phone.html", {
                "verification_form": VerificationForm(request.POST),
                "error_message": error_message,
            })

    # Для GET запроса просто проверяем, нет ли уже блокировки перебора
    elif request.method == "GET":
        if cache.get(attempts_key, 0) > settings.MAX_VERIFICATION_ATTEMPTS:
            error_message = "Слишком много неудачных попыток. Запросите код заново."
            return render(request, "main/verify_phone.html", {
                "verification_form": VerificationForm(),
                "error_message": error_message,
            })

    # 2. ЛОГИКА ОТПРАВКИ СМС (Только для GET запроса)
    sms_count = cache.get(sms_count_key, 0)

    if request.method == "GET":
        last_sent = request.session.get("sms_sent_time")
        current_time = time.time()

        if sms_count >= SMS_MAX_PER_HOUR:
            error_message = "Исчерпан лимит SMS. Попробуйте позже."
            return render(request, "main/verify_phone.html", {
                "verification_form": VerificationForm(),
                "error_message": error_message,
            })

        if not last_sent or (current_time - last_sent) > SMS_RESEND_INTERVAL:
            send_verification_code_to_phone(
                user_data["phone_number"],
                purpose="register",
            )
            # Если ключа лимита СМС нет — создаем его, затем увеличиваем
            cache.add(sms_count_key, 0, NOTIFY_COOLDOWN_HOUR)
            cache.incr(sms_count_key)
            request.session["sms_sent_time"] = current_time
            request.session.modified = True

    # 3. ОБРАБОТКА ВАЛИДАЦИИ ФОРМЫ (Для POST)
    form = VerificationForm(request.POST or None)
    error_message = None

    if request.method == "POST" and form.is_valid():
        previous_url = request.session.get("previous_url", "/")
        input_code = form.cleaned_data["code"]

        try:
            with transaction.atomic():
                verification = VerificationCode.objects.select_for_update().filter(
                    phone_number=user_data["phone_number"],
                    purpose="register",
                    is_used=False,
                    expires_at__gt=timezone.now(),
                ).first()

                if verification and verification.check_code(input_code):
                    # Код верный — создаем пользователя
                    user = CustomUser(
                        username=user_data["username"],
                        email=user_data["email"],
                        password=user_data["password_hash"],
                        phone_number=user_data.get("phone_number") or None,
                        is_active=True,
                    )
                    user.save()

                    # Помечаем код использованным
                    verification.is_used = True
                    verification.save(update_fields=["is_used"])
                    
                    # Полностью очищаем кэш попыток брутфорса
                    cache.delete(attempts_key)

                    # Асинхронная отправка email
                    threading.Thread(
                        target=_async_welcome_email,
                        args=(user.username, user.email),
                    ).start()

                    # Очищаем сессию регистрации
                    request.session.pop("verification_data", None)
                    request.session.pop("sms_sent_time", None)
                    request.session.modified = True

                    login(request, user)

                    send_notifications(
                        user=user,
                        title="Добро пожаловать!",
                        message="Аккаунт успешно создан. Заполните профиль, чтобы получить доступ ко всем возможностям.",
                        notification_type="success",
                    )

                    if request.headers.get("HX-Request"):
                        response = HttpResponse()
                        response["HX-Redirect"] = _safe_redirect(request, previous_url).url
                        return response
                    return _safe_redirect(request, previous_url)

                else:
                    # Код неверный. Счетчик attempts увеличился в самом начале функции,
                    # поэтому здесь мы просто выводим текст ошибки.
                    current_attempts = cache.get(attempts_key, 0)
                    if current_attempts > settings.MAX_VERIFICATION_ATTEMPTS:
                        error_message = "Слишком много неудачных попыток. Запросите код заново."
                    else:
                        error_message = "Неверный или истекший код из СМС."

                    return render(request, "main/verify_phone.html", {
                        "verification_form": form,
                        "error_message": error_message,
                    })

        except IntegrityError:
            error_message = "Пользователь с таким номером телефона или email уже зарегистрирован."
            return render(request, "main/verify_phone.html", {
                "verification_form": form,
                "error_message": error_message,
            })

    return render(request, "main/verify_phone.html", {
        "verification_form": form,
        "error_message": error_message,
    })

