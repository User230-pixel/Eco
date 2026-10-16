import logging
import threading
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.contrib.auth.signals import user_logged_in
from django.db.models import F
from django.contrib.auth import logout
from django.contrib import messages

User = get_user_model()
logger = logging.getLogger(__name__)


def _async_welcome_email(username, email):
    """Внутренняя функция для отправки письма в фоновом потоке"""
    try:
        send_mail(
            subject="Аккаунт успешно создается, просто дальше подтвердите email!",
            message=f"Привет, {username}! Твой аккаунт на нашем сайте успешно зарегистрирован.",
            from_email="your_email@gmail.com",
            recipient_list=[email],
            fail_silently=True, 
        )
    except Exception as e:
        logger.error(f"Ошибка фоновой отправки welcome-письма: {e}")


@receiver(post_save, sender=User)
def send_welcome_email(sender, instance, created, **kwargs):
    if created and instance.email:  
        thread = threading.Thread(
            target=_async_welcome_email, 
            args=(instance.username, instance.email)
        )
        thread.start()


@receiver(user_logged_in)
def penalty_on_login(sender, request, user, **kwargs):
    """Списание баллов при входе (защита от ботов)"""
    if user and hasattr(user, "action_points"):
        if user.action_points > 0:
            sender.objects.filter(pk=user.pk).update(action_points=F('action_points') - 1)
        else:
            logout(request)
            messages.error(request, "Лимит действий исчерпан!")
