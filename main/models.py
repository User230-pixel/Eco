import logging

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from phonenumber_field.modelfields import PhoneNumberField


logger = logging.getLogger(__name__)


class CustomUser(AbstractUser):
    """Кастомный пользователь.

    Роли:
      - role_user      — потребитель (по умолчанию True)
      - role_driver    — водитель
      - role_blogger   — блогер
      - role_moderator — модератор
      - role_admin     — администратор
      - role_shopper   — продавец
    """
    role_user = models.BooleanField(default=True, verbose_name="Потребитель")
    role_driver = models.BooleanField(default=False, verbose_name="Водитель")
    role_blogger = models.BooleanField(default=False, verbose_name="Блогер")
    role_moderator = models.BooleanField(default=False, verbose_name="Модератор")
    role_admin = models.BooleanField(default=False, verbose_name="Администратор")
    role_shopper = models.BooleanField(default=False, verbose_name="Продавец")

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to.",
        related_name="shop_user_groups_set",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="shop_user_permissions_set",
    )

    phone_number = PhoneNumberField(
        unique=True,
        null=True,
        blank=True,
        region="RU",
        verbose_name="Номер телефона",
    )

    action_points = models.IntegerField(default=30000, verbose_name="Баллы действий")
    action_points_2 = models.IntegerField(default=10, verbose_name="Доп. баллы")

    car_model = models.CharField(max_length=100, blank=True, null=True, verbose_name="Модель авто")
    car_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Госномер")
    experience_years = models.IntegerField(default=0, verbose_name="Стаж (лет)")

    instagram = models.CharField(max_length=100, blank=True, null=True, verbose_name="Instagram")
    youtube = models.CharField(max_length=100, blank=True, null=True, verbose_name="YouTube")
    followers_count = models.IntegerField(default=0, verbose_name="Количество подписчиков")

    class Meta:
        db_table = "app_customuser"

    def clean(self):
        super().clean()
        selected_roles_count = sum([
            self.role_user,
            self.role_driver,
            self.role_blogger,
            self.role_moderator,
            self.role_admin,
            self.role_shopper,
        ])
        if selected_roles_count > 2:
            raise ValidationError("Пользователь не может иметь более 2 ролей одновременно.")
        if selected_roles_count == 0:
            raise ValidationError("У пользователя должна быть выбрана хотя бы одна роль.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def is_driver(self):
        return self.role_driver

    def is_blogger(self):
        return self.role_blogger

    def is_moderator(self):
        return self.role_moderator or self.role_admin

    def is_admin(self):
        return self.role_admin

    def __str__(self):
        roles_list = []
        if self.role_user:
            roles_list.append("Потребитель")
        if self.role_driver:
            roles_list.append("Водитель")
        if self.role_blogger:
            roles_list.append("Блогер")
        if self.role_moderator:
            roles_list.append("Модератор")
        if self.role_admin:
            roles_list.append("Администратор")
        if self.role_shopper:
            roles_list.append("Продавец")
        return f"{self.username} ({', '.join(roles_list)})"


class Profile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    bio = models.TextField(max_length=500, blank=True, verbose_name="О себе")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    likes_count = models.PositiveIntegerField(default=0)
    subscribers_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Профиль {self.user.username}"


class Notification(models.Model):
    TYPE_INFO = "info"
    TYPE_SUCCESS = "success"
    TYPE_ERROR = "error"
    TYPE_WARNING = "warning"

    NOTIFICATION_TYPES = [
        (TYPE_INFO, "Information"),
        (TYPE_SUCCESS, "Success"),
        (TYPE_ERROR, "Error"),
        (TYPE_WARNING, "Warning"),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()

    notification_type = models.CharField(
        max_length=10,
        choices=NOTIFICATION_TYPES,
        default=TYPE_INFO,
    )

    url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Ссылка",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.notification_type.upper()} | {self.title} for {self.user.username}"


class ProfileLike(models.Model):
    """Лайк профиля. Один юзер — один лайк на профиль."""
    from_user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="given_likes",
    )
    to_profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("from_user", "to_profile")
        verbose_name = "Лайк"
        verbose_name_plural = "Лайки"

    def __str__(self):
        return f"{self.from_user} → {self.to_profile.user}"


class Subscription(models.Model):
    """Подписка: кто → на кого."""
    subscriber = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    to_profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="subscribers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("subscriber", "to_profile")
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"{self.subscriber} → {self.to_profile.user}"