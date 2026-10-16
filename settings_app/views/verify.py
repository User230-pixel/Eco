from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from settings_app.views.views import send_verification_code_to_phone

from ..models import VerificationCode

NOTIFY_COOLDOWN_HOUR = 3600
CODE_ATTEMPT_WINDOW = 3600

@login_required
@require_POST
def resend_phone_verification_code(request):
    pending_phone = request.session.get("pending_phone")

    if not pending_phone:
        messages.error(request, "Сессия истекла. Начните смену номера заново.")
        request.session["change_phone_flow"] = False
        return redirect("main:change_phone")

    resend_key = f"resend_phone_code_{request.user.id}"
    resend_count = cache.get(resend_key, 0)

    if resend_count >= 3:
        messages.error(request, "Вы исчерпали лимит повторных отправок. Попробуйте через час.")
    else:
        VerificationCode.objects.filter(
            phone_number=pending_phone,
            purpose="change_phone",
            is_used=False,
        ).update(is_used=True)

        send_verification_code_to_phone(pending_phone, purpose="change_phone", user=request.user)

        cache.delete(f"change_phone_attempts_user:{request.user.id}")

        cache.set(resend_key, resend_count + 1, NOTIFY_COOLDOWN_HOUR)
        messages.success(request, "Новый код успешно отправлен по СМС!")

    return redirect("main:change_phone")
