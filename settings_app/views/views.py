import logging
import threading

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import render

from ..models import VerificationCode
from main.views.send import _async_send_code_sms

NOTIFY_COOLDOWN_HOUR = 3600
SMS_MAX_PER_HOUR = 5

logger = logging.getLogger(__name__)

@login_required
def settings_dashboard(request):
    """Представление для персональной панели настроек текущего пользователя."""
    context = {
        "user": request.user,
    }
    return render(request, "settings_app/dashboard.html", context)

def send_verification_code_to_phone(phone_number, purpose="change_phone", user=None):
    limit_key = f"sms_limit:{phone_number}"
    cache.add(limit_key, 0, NOTIFY_COOLDOWN_HOUR)
    count = cache.incr(limit_key)
    if count > SMS_MAX_PER_HOUR:
        logger.warning("SMS limit exceeded for %s (purpose=%s)", phone_number, purpose)
        return False

    VerificationCode.objects.filter(
        phone_number=phone_number,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    verification, raw_code = VerificationCode.generate(
        purpose=purpose,
        user=user,
        phone_number=phone_number,
    )

    thread = threading.Thread(
        target=_async_send_code_sms,
        args=(phone_number, raw_code),
    )
    thread.start()
    return True
