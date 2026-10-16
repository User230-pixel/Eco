import logging
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from .views import moderator_required
from django.http import HttpResponseForbidden

User = get_user_model()

logger = logging.getLogger(__name__)

User = get_user_model()

@moderator_required
@login_required(login_url='main:get_login_form')
def users_list_view(request):
    """Список пользователей с живым поиском HTMX и бесконечным скроллом.
    Доступ только для модераторов и администраторов.
    """

    all_users = User.objects.all().order_by("id")

    search_query = request.GET.get("search", "").strip()
    if search_query:
        if search_query.isdigit() and len(search_query) <= 9:
            users_queryset = all_users.filter(
                Q(username__icontains=search_query) | Q(id=int(search_query))
            )
        else:
            users_queryset = all_users.filter(username__icontains=search_query)
    else:
        users_queryset = all_users

    paginator = Paginator(users_queryset, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "users": page_obj,
        "search_query": search_query,
    }

    if request.headers.get("HX-Request"):
        if request.GET.get("page"):
            return render(request, "main/user_list.html", context)
        return render(request, "main/user_table.html", context)

    stats = User.objects.aggregate(
        total_users_count=Count("id", filter=Q(role_user=True)),
        total_drivers_count=Count("id", filter=Q(role_driver=True)),
        total_bloggers_count=Count("id", filter=Q(role_blogger=True)),
        total_moderators_count=Count("id", filter=Q(role_moderator=True)),
        total_admins_count=Count("id", filter=Q(role_admin=True)),
    )
    context.update(stats)
    context["now"] = timezone.now()

    return render(request, "main/users.html", context)

@moderator_required
@login_required(login_url='main:get_login_form')
def delete_user(request, user_id):
    if request.method != "POST":
        return HttpResponseForbidden("Метод не разрешён")

    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        messages.error(request, "Нельзя удалить самого себя.")
        return redirect("shop:profile")

    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, "Нельзя удалить суперпользователя.")
        return redirect("shop:profile")

    username = target.username
    target.delete()
    messages.success(request, f"Пользователь «{username}» удалён.")
    return redirect("shop:profile")