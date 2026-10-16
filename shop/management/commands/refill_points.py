from django.core.management.base import BaseCommand
from django.db.models import F
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Начисляет +10 баллов всем активным пользователям одним запросом"

    def handle(self, *args, **kwargs):
        updated_count = get_user_model.objects.filter(is_active=True).update(
            action_points=F("action_points") + 10
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Успешно обновлено пользователей: {updated_count}. Начислено по +10 баллов в БД!"
            )
        )
