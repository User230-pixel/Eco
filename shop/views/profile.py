from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction

from main.models import (
    Profile,
)
from shop.models import (
    Order,
    OrderItem,
    Product,
)
from main.forms import (
    ProfileForm,
    ChangePhoneForm,
    ChangeEmailForm,
)

from shop.views.views import get_cached_categories

from main.views.views import (
    rate_limit
)

from django.contrib import messages
from django.core.cache import cache


@login_required(login_url='main:get_login_form')
def profile_view(request):
    referer = request.META.get('HTTP_REFERER', '/')
    profile, created = Profile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    counter = orders.count()
    
    if '/profile' not in referer:
        request.session['previous_url'] = referer
        
    user = request.user
    if user.first_name and user.last_name:
        avatar = user.first_name[0] + user.last_name[0]
    else:
        avatar = user.username[0] if user.username else "?"

    context = {
        "user": request.user,
        "profile": profile,
        "categories": get_cached_categories(),
        "avatar": avatar,
        "orders": orders,
        "counter": counter,
    }
    return render(request, "shop/profile.html", context)


@login_required(login_url='main:get_login_form')
@rate_limit('profile', 20, 600)
def profile_update(request):
    if request.method == "GET":
        return redirect("shop:profile")

    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    counter = orders.count()
    
    LIMIT_TIMEOUT = 3600  
    email_changed = False
    phone_changed = False

    if "email" in request.POST and request.POST.get("email", "").strip() != user.email:
        if cache.get(f"cooldown_email_{user.id}"):
            messages.error(request, "Изменять Email можно не чаще, чем раз в час!")
            return _render_profile_error_response(request, user, profile, "Email: Изменение заблокировано по времени.")
        email_changed = True

    phone_value = request.POST.get("phone_number") or request.POST.get("phone")
    if phone_value is not None and phone_value.strip() != getattr(profile, 'phone', ''):
        if cache.get(f"cooldown_phone_{user.id}"):
            messages.error(request, "Изменять номер телефона можно не чаще, чем раз в час!")
            return _render_profile_error_response(request, user, profile, "Телефон: Изменение заблокировано по времени.")
        phone_changed = True

    if "address" not in request.POST and not request.FILES:
        profile_form = ProfileForm(instance=profile)
        profile_form_valid = True
        profile_form_errors = {}
    else:
        profile_form = ProfileForm(request.POST, request.FILES, instance=profile)
        if profile_form.is_valid():
            profile_form_valid = True
        else:
            profile_form_valid = False
            profile_form_errors = profile_form.errors

    email_form = None
    email_valid = True

    if "email" in request.POST:
        email_form = ChangeEmailForm(request.POST, instance=user)
        if email_form.is_valid():
            user.email = email_form.cleaned_data["email"]
        else:
            email_valid = False

    phone_form = None
    phone_valid = True

    if phone_value is not None:
        post_data = request.POST.copy()
        post_data["phone_number"] = phone_value

        phone_form = ChangePhoneForm(post_data, instance=user)
        if phone_form.is_valid():
            validated_phone = phone_form.cleaned_data["phone_number"]
            user.phone_number = validated_phone
            profile.phone = validated_phone
        else:
            phone_valid = False

    if "first_name" in request.POST:
        user.first_name = request.POST.get("first_name", "").strip()
    if "last_name" in request.POST:
        user.last_name = request.POST.get("last_name", "").strip()

    has_errors = not profile_form_valid or not email_valid or not phone_valid

    if has_errors:
        error_messages = []

        if not profile_form_valid:
            for field, errors in profile_form_errors.items():
                for error in errors: error_messages.append(f"{field}: {error}")

        if email_form and not email_valid:
            for field, errors in email_form.errors.items():
                for error in errors: error_messages.append(f"Email: {error}")

        if phone_form and not phone_valid:
            for field, errors in phone_form.errors.items():
                for error in errors: error_messages.append(f"Телефон: {error}")

        if error_messages:
            messages.error(request, error_messages[0])
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме")

        return _render_profile_error_response(request, user, profile, error_messages, profile_form, email_form, phone_form)

    with transaction.atomic():
        if "address" in request.POST or request.FILES:
            profile_form.save() 
            
        user.save()
        profile.save()
        
        if email_changed:
            cache.set(f"cooldown_email_{user.id}", True, LIMIT_TIMEOUT)
        if phone_changed:
            cache.set(f"cooldown_phone_{user.id}", True, LIMIT_TIMEOUT)

    user = request.user
    if user.first_name and user.last_name:
        avatar = user.first_name[0] + user.last_name[0]
    else:
        avatar = user.username[0] if user.username else "?"

    context = {
        "user": user,
        "profile": profile,
        "avatar": avatar,
        "success": True,
        "orders": orders,
        "counter": counter,
    }
    return render(request, "shop/profile_form.html", context)


def _render_profile_error_response(request, user, profile, error_messages, profile_form=None, email_form=None, phone_form=None):
    if isinstance(error_messages, str):
        error_messages = [error_messages]

    context = {
        "user": user,
        "profile": profile,
        "categories": get_cached_categories(),
        "email_form": email_form or ChangeEmailForm(instance=user),
        "phone_form": phone_form or ChangePhoneForm(instance=user),
        "profile_form": profile_form or ProfileForm(instance=profile),
        "success": False,
        "form_errors": error_messages,
    }
    return render(request, "shop/profile_form.html", context)