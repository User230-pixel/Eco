import json

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from main.views.views import get_previous_app
from ..models import Notification


@login_required(login_url='main:get_login_form')
def notifications(request):
    notifications_queryset = request.user.notifications.all()

    current_filter = request.GET.get('filter', 'all')

    previous_app = get_previous_app(request)
    base_template = 'shop/base.html' if previous_app == 'shop' else 'main/base.html'

    if current_filter == 'unread':
        notifications_queryset = notifications_queryset.filter(is_read=False)
    elif current_filter == 'read':
        notifications_queryset = notifications_queryset.filter(is_read=True)

    notifications_list = list(notifications_queryset[:200])

    context = {
        'notifications': notifications_list,
        'current_filter': current_filter,
        'base_template': base_template,
    }
    return render(request, 'main/notifications.html', context)


@login_required(login_url='main:get_login_form')
@require_POST
def is_read_update(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)

    cache.delete(f"unread_notifications_count:{request.user.id}")

    filter_param = request.POST.get('filter', 'all')
    redirect_url = f"{reverse('main:notifications')}?filter={filter_param}"

    return redirect(redirect_url)

@login_required
@require_POST
def delete_notification(request):
    notif_id = request.POST.get("id")
    if not notif_id or not str(notif_id).isdigit():
        return HttpResponse(status=400)

    deleted, _ = Notification.objects.filter(id=int(notif_id), user=request.user).delete()
    if deleted == 0:
        return HttpResponse(status=404)

    cache.delete(f"unread_notifications_count:{request.user.id}")
    return HttpResponse(status=204)