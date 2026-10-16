from django.db import models
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone

class VerificationCode(models.Model):
    PURPOSE_CHOICES = [
        ("register", "Регистрация"),
        ("reset", "Сброс пароля"),
        ("change_phone", "Смена телефона"),
        ("change_email", "Смена email"),
    ]

    user = models.ForeignKey(
        "main.CustomUser",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="verification_codes",
    )
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=22, blank=True, null=True)

    code_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "is_used"]),
            models.Index(fields=["phone_number", "purpose", "is_used"]),
            models.Index(fields=["email", "purpose", "is_used"]),
        ]

    def set_code(self, raw_code):
        self.code_hash = make_password(raw_code)
        if self.pk:
            self.save(update_fields=["code_hash"])
        else:
            self.save()
        return raw_code

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at

    @classmethod
    def generate(cls, purpose, user=None, email=None, phone_number=None, ttl_minutes=5):
        raw_code = str(secrets.randbelow(900000) + 100000)
        obj = cls.objects.create(
            user=user,
            email=email,
            phone_number=phone_number,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )
        obj.set_code(raw_code)
        return obj, raw_code

    def __str__(self):
        target = self.email or self.phone_number or (self.user.username if self.user else "?")
        return f"Код ({self.purpose}) для {target}"