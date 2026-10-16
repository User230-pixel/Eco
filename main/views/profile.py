from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db import transaction

from main.models import Profile, ProfileLike, Subscription
from shop.models import Order
from ..forms import ProfileForm
from .views import rate_limit

User = get_user_model()



@login_required(login_url='main:get_login_form')
def profile(request, user_id):
    """Публичный профиль. Свой → редирект в кабинет."""
    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        return redirect("main:cabinet")

    profile_obj, _ = Profile.objects.get_or_create(user=target)

    if target.first_name and target.last_name:
        avatar = target.first_name[0] + target.last_name[0]
    else:
        avatar = target.username[0] if target.username else "?"

    context = {
        "target": target,
        "profile": profile_obj,
        "avatar": avatar,
        "is_self": False,
        "user_has_liked": ProfileLike.objects.filter(
            from_user=request.user, to_profile=profile_obj
        ).exists(),
        "user_is_subscribed": Subscription.objects.filter(
            subscriber=request.user, to_profile=profile_obj
        ).exists(),
    }
    return render(request, "main/profile.html", context)



@login_required(login_url='main:get_login_form')
def cabinet(request):
    """Личный кабинет."""
    referer = request.META.get('HTTP_REFERER', '/')

    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    counter = orders.count()

    if '/cabinet' not in referer and '/profile' not in referer:
        request.session['previous_url'] = referer

    user = request.user
    if user.first_name and user.last_name:
        avatar = user.first_name[0] + user.last_name[0]
    else:
        avatar = user.username[0] if user.username else "?"

    context = {
        "user": user,
        "profile": profile_obj,
        "avatar": avatar,
        "orders": orders,
        "counter": counter,
    }
    return render(request, "main/cabinet.html", context)


@login_required(login_url='main:get_login_form')
@rate_limit('profile', 20, 600)
def cabinet_update(request):
    """HTMX: обновление публичных данных (имя, био, аватар)."""
    if request.method == "GET":
        return redirect("main:cabinet")

    user = request.user
    profile_obj, _ = Profile.objects.get_or_create(user=user)

    profile_form = ProfileForm(request.POST, request.FILES, instance=profile_obj)

    if "first_name" in request.POST:
        user.first_name = request.POST.get("first_name", "").strip()
    if "last_name" in request.POST:
        user.last_name = request.POST.get("last_name", "").strip()

    if not profile_form.is_valid():
        error_messages = []
        for field, errors in profile_form.errors.items():
            for error in errors:
                error_messages.append(f"{field}: {error}")

        if error_messages:
            messages.error(request, error_messages[0])

        return _render_cabinet_error_response(request, user, profile_obj, error_messages, profile_form)

    with transaction.atomic():
        profile_form.save()
        user.save()

    if user.first_name and user.last_name:
        avatar = user.first_name[0] + user.last_name[0]
    else:
        avatar = user.username[0] if user.username else "?"

    context = {
        "user": user,
        "profile": profile_obj,
        "avatar": avatar,
        "success": True,
    }
    return render(request, "main/cabinet_form.html", context)


def _render_cabinet_error_response(request, user, profile_obj, error_messages, profile_form=None):
    if isinstance(error_messages, str):
        error_messages = [error_messages]

    context = {
        "user": user,
        "profile": profile_obj,
        "profile_form": profile_form or ProfileForm(instance=profile_obj),
        "success": False,
        "form_errors": error_messages,
    }
    return render(request, "main/cabinet_form.html", context)




@login_required(login_url='main:get_login_form')
@require_POST
def toggle_profile_like(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        return JsonResponse({"error": "Нельзя лайкать себя"}, status=400)

    profile_obj, _ = Profile.objects.get_or_create(user=target)

    like, created = ProfileLike.objects.get_or_create(
        from_user=request.user, to_profile=profile_obj
    )

    if created:
        Profile.objects.filter(pk=profile_obj.pk).update(likes_count=F("likes_count") + 1)
    else:
        like.delete()
        Profile.objects.filter(pk=profile_obj.pk).update(likes_count=F("likes_count") - 1)

    profile_obj.refresh_from_db()
    return JsonResponse({"liked": created, "likes_count": profile_obj.likes_count})


@login_required(login_url='main:get_login_form')
@require_POST
def toggle_subscription(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        return JsonResponse({"error": "Нельзя подписаться на себя"}, status=400)

    profile_obj, _ = Profile.objects.get_or_create(user=target)

    sub, created = Subscription.objects.get_or_create(
        subscriber=request.user, to_profile=profile_obj
    )

    if created:
        Profile.objects.filter(pk=profile_obj.pk).update(subscribers_count=F("subscribers_count") + 1)
    else:
        sub.delete()
        Profile.objects.filter(pk=profile_obj.pk).update(subscribers_count=F("subscribers_count") - 1)

    profile_obj.refresh_from_db()
    return JsonResponse({"subscribed": created, "subscribers_count": profile_obj.subscribers_count})