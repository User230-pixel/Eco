from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db import transaction

from main.models import (
    Profile,
    Subscription,
    ProfileLike
)
from shop.models import (
    Order,
    OrderItem,
    Product,
    SellerReply,
    Review,
)
from main.forms import (
    ProfileForm,
    ChangePhoneForm,
    ChangeEmailForm,
)

from blog.models import (
    Comment
)

from shop.views.views import get_cached_categories

from main.views.views import (
    rate_limit,
    blogger_required,
    shopper_required,
)

from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator

from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

@login_required(login_url='main:get_login_form')
def cabinet_view(request):
    referer = request.META.get('HTTP_REFERER', '/')
    profile, created = Profile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(orders, 4)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

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
        "orders": page_obj,
        "counter": counter,
    }
    return render(request, "shop/cabinet.html", context)


@login_required(login_url='main:get_login_form')
@rate_limit('profile', 20, 600)
def cabinet_update(request):
    if request.method == "GET":
        return redirect("shop:profile")

    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(orders, 4)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    counter = orders.count()
    
    LIMIT_TIMEOUT = 3600  
    email_changed = False
    phone_changed = False

    if "email" in request.POST and request.POST.get("email", "").strip() != user.email:
        if cache.get(f"cooldown_email_{user.id}"):
            messages.error(request, "Изменять Email можно не чаще, чем раз в час!")
            return _render_cabinet_error_response(request, user, profile, "Email: Изменение заблокировано по времени.")
        email_changed = True

    phone_value = request.POST.get("phone_number") or request.POST.get("phone")
    if phone_value is not None and phone_value.strip() != getattr(profile, 'phone', ''):
        if cache.get(f"cooldown_phone_{user.id}"):
            messages.error(request, "Изменять номер телефона можно не чаще, чем раз в час!")
            return _render_cabinet_error_response(request, user, profile, "Телефон: Изменение заблокировано по времени.")
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

        return _render_cabinet_error_response(request, user, profile, error_messages, profile_form, email_form, phone_form)

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
        "orders": page_obj,
        "counter": counter,
    }
    return render(request, "shop/cabinet_form.html", context)


def _render_cabinet_error_response(request, user, profile, error_messages, profile_form=None, email_form=None, phone_form=None):
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


@login_required(login_url='main:get_login_form')
def profile(request, pk):
    profile_user = get_object_or_404(User, Q(role_shopper=True) | Q(is_superuser=True), pk=pk)
    profile_obj, _ = Profile.objects.get_or_create(user=profile_user)
    products = Product.objects.filter(user=profile_user).select_related('category2nd').order_by('-created_at')
    sellers = SellerReply.objects.filter(review__product__user=profile_user).select_related('review', 'review__product')[:20]


    sellers_with_url = []
    for reply in sellers:
        if reply.review and reply.review.product:
            product_url = reverse("shop:product_detail", kwargs={
                "id": reply.review.product.id,
                "slug": reply.review.product.slug,
            })
            sellers_with_url.append({
                'reply': reply,
                'url': f"{product_url}#review-{reply.review.id}",
            })
        else:
            sellers_with_url.append({'reply': reply, 'url': None})


    is_auth = request.user.is_authenticated
    user_is_subscribed = is_auth and Subscription.objects.filter(subscriber=request.user, to_profile=profile_obj).exists()
    user_has_liked = is_auth and ProfileLike.objects.filter(from_user=request.user, to_profile=profile_obj).exists()    

    paginator = Paginator(products, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'products': page_obj,
        'profile_user': profile_user,
        'profile_obj': profile_obj,
        "user_has_liked": user_has_liked,
        "user_is_subscribed": user_is_subscribed,
        "sellers": sellers_with_url,
        "products_count": paginator.count,
        "is_owner": is_auth and request.user.pk == profile_user.pk,
    }

    return render(request, "shop/profile.html", context)