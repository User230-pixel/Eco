from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.core.mail import send_mail

from ..models import (
    Product,
    Review,
    SellerReply,
)

from main.views.views import (
    rate_limit,
    send_notifications,
)

from django.conf import settings

import logging

from datetime import timedelta
from django.utils.html import escape
from django.urls import reverse

logger = logging.getLogger(__name__)


@login_required(login_url='main:get_login_form')
@require_POST
@rate_limit('review', 3, 300)
def add_review_htmx(request, id, slug):
    product = get_object_or_404(Product, id=id, available=True)
    text_0 = request.POST.get("text_0", "").strip()
    text_1 = request.POST.get("text_1", "").strip()

    if not (text_0 and text_1):
        return HttpResponse("Все поля формы обязательны к заполнению", status=400)

    time_threshold = timezone.now() - timedelta(minutes=3)
    recent_review_exists = Review.objects.filter(
        product=product,
        user=request.user,
        created_at__gte=time_threshold
    ).exists()

    if recent_review_exists:
        return HttpResponse("Вы слишком часто отправляете отзывы. Подождите пару минут.", status=429)

    try:
        review = Review.objects.create(
            product=product, user=request.user, text_0=text_0, text_1=text_1
        )

        safe_text_0 = escape(review.text_0)
        safe_text_1 = escape(review.text_1)

        try:
            email_message = (
                f"Здравствуйте, меня зовут {request.user}, вот мой отзыв:\n"
                f"Достоинства: {safe_text_1}\n"
                f"Недостатки: {safe_text_0}\n"
            )
            recipients = [settings.EMAIL_HOST_USER]

            send_mail(
                subject=f"Алишоп: отзыв",
                message=email_message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=recipients,
                fail_silently=False,
            )
        except Exception as mail_err:
            logger.error(f"Ошибка отправки почты в вебхуке: {mail_err}")
            return HttpResponse(status=200)

        html_content = f"""
        <div class="review-item animate-[fadeIn_0.3s_ease-in-out] bg-white dark:bg-void border border-gray-300 dark:border-edge p-[15px] rounded-[var(--radius)]">
            <div class="flex justify-between text-[13px] mb-3 border-b border-gray-300 dark:border-edge pb-1.5">
                <span class="review-author text-black dark:text-volt font-semibold">{escape(request.user.username)}</span>
                <span class="review-date text-gray-500 dark:text-gray-400 font-mono text-[11px]">Только что</span>
            </div>
            <div class="review-blocks flex flex-col gap-2">
                <div>
                    <strong class="block text-xs font-mono uppercase tracking-widest text-gray-900 dark:text-volt mb-0.5">➕ Преимущества:</strong>
                    <p class="review-content text-gray-900 dark:text-white text-sm m-0 leading-normal">{safe_text_1}</p>
                </div>
                <div class="mt-1">
                    <strong class="block text-xs font-mono uppercase tracking-widest text-red-600 dark:text-red-400 mb-0.5">➖ Недостатки:</strong>
                    <p class="review-content text-gray-900 dark:text-white text-sm m-0 leading-normal">{safe_text_0}</p>
                </div>
            </div>
        </div>
        """

        return HttpResponse(html_content)

    except Exception as e:
        return HttpResponse("Ошибка сервера при сохранении отзыва.", status=500)


@login_required(login_url="main:get_login_form")
@require_POST
def add_seller_reply(request, review_id):
    review = get_object_or_404(
        Review.objects.select_related("product__user", "user"),
        id=review_id,
    )

    is_seller = review.product.user_id == request.user.id
    is_admin = request.user.is_superuser

    if not (is_seller or is_admin):
        raise PermissionDenied("Вы не можете отвечать на этот отзыв.")

    if hasattr(review, "seller_reply"):
        messages.error(request, "Вы уже ответили на этот отзыв.")
        return redirect(review.product.get_absolute_url())

    text = request.POST.get("text", "").strip()

    if not text:
        messages.error(request, "Ответ не может быть пустым.")
        return redirect(review.product.get_absolute_url())

    if len(text) > 2000:
        messages.error(request, "Ответ слишком длинный (макс. 2000).")
        return redirect(review.product.get_absolute_url())

    SellerReply.objects.create(
        review=review,
        seller=request.user,
        text=text,
    )

    product_url = reverse("shop:product_detail", kwargs={
        "id": review.product.id,
        "slug": review.product.slug,
    })

    send_notifications(
        user=review.user,
        title="Ответ на ваш отзыв",
        message=f"Продавец ответил на ваш отзыв о товаре «{review.product.name}»",
        notification_type="info",
        url=f"{product_url}#review-{review.id}",
    )

    messages.success(request, "Ответ добавлен.")
    return redirect(review.product.get_absolute_url())


@login_required(login_url="main:get_login_form")
@require_POST
def edit_seller_reply(request, review_id):
    review = get_object_or_404(
        Review.objects.select_related("product__user"),
        id=review_id,
    )
    reply = get_object_or_404(SellerReply, review=review)

    is_seller = review.product.user_id == request.user.id
    is_admin = request.user.is_superuser

    if not (is_seller or is_admin):
        raise PermissionDenied("Вы не можете редактировать этот ответ.")

    text = request.POST.get("text", "").strip()

    if not text:
        messages.error(request, "Ответ не может быть пустым.")
        return redirect(review.product.get_absolute_url())

    if len(text) > 2000:
        messages.error(request, "Ответ слишком длинный (макс. 2000).")
        return redirect(review.product.get_absolute_url())

    reply.text = text
    reply.save(update_fields=["text", "updated_at"])

    messages.success(request, "Ответ обновлён.")
    return redirect(review.product.get_absolute_url())