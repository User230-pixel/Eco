from django.shortcuts import render, redirect
from django.http import HttpResponse

from django.contrib import messages


from django.core.cache import cache

from functools import wraps

from django.conf import settings

from ..models import (
    Notification
)

ALLOWED_APPS = {"main", "shop", "phone_verify"}


def rate_limit(key_prefix, limit, timeout=300):
    """
    Декоратор для ограничения частоты запросов

    Аргументы:
        key_prefix (str): Префикс для ключа в кеше (например 'login', 'register')
        limit (int): Максимальное количество запросов за период
        timeout (int): Время в секундах, после которого счетчик сбрасывается

    Использование:
        @rate_limit('login', 5, 300)   5 попыток за 5 минут
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                key = f"rate_limit_{key_prefix}_{request.user.id}"
            else:
                ip = get_client_ip(request)
                key = f"rate_limit_{key_prefix}_{ip}"

            cache.add(key, 0, timeout)
            attempts = cache.incr(key)

            if attempts > limit:
                ttl = cache.ttl(key) if hasattr(cache, "ttl") else timeout
                return HttpResponse(
                    "Слишком много запросов. Попробуйте позже.",
                    status=429,
                    headers={'Retry-After': str(ttl or timeout)}
                )

            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def guest_only(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.headers.get('HX-Request'):
                return render(request, 'main/partials/_notification.html', {
                    'message': 'Вы уже авторизованы!',
                    'type': 'info'
                })
            messages.error(request, "Вы уже авторизованы. Пожалуйста, занимайтесь своими делами.")
            return redirect('shop:product_list')
        return view_func(request, *args, **kwargs)
    return wrapped


def get_client_ip(request):
    remote_addr = request.META.get("REMOTE_ADDR", "")
    trusted = getattr(settings, "TRUSTED_PROXY_IPS", [])

    if remote_addr in trusted:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
            if ips:
                return ips[-1]
    return remote_addr


def send_notifications(user, title, message, notification_type, url):
    if user is None:
        return None
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        url=url,
    )


def get_previous_app(request):
    """
    Возвращает имя приложения, с которого пришёл пользователь.
    Приоритет: GET-параметр 'from' → HTTP_REFERER → 'main'.
    """
    explicit_from = request.GET.get('from')
    if explicit_from in ALLOWED_APPS:
        return explicit_from

    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        from urllib.parse import urlparse
        path = urlparse(referer).path
        parts = [p for p in path.split('/') if p]
        if parts and parts[0] in ALLOWED_APPS:
            return parts[0]

    return 'main'

def role_required(role_field, message='У вас нет полномочий быть здесь!'):
    """
    Фабрика декораторов. Проверяет, что у пользователя есть
    указанная роль ИЛИ он админ/суперюзер.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user

            has_access = (
                user.is_authenticated
                and (
                    getattr(user, role_field, False)
                    or user.role_admin
                    or user.is_superuser
                )
            )

            if has_access:
                return view_func(request, *args, **kwargs)

            if request.headers.get('HX-Request'):
                return render(request, 'main/notification.html', {
                    'message': message,
                    'type': 'info',
                }, status=403)

            messages.error(request, "Доступ запрещен.")
            return redirect('main:get_login_form')

        return wrapped
    return decorator


shopper_required   = role_required('role_shopper')
driver_required    = role_required('role_driver')
blogger_required   = role_required('role_blogger')
moderator_required = role_required('role_moderator')