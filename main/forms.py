import re

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import CustomUser, Profile
from shop.models import Product

EMAIL_TYPO_MAP = {
    "gmal.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmal.ru": "gmail.com",
    "yandx.ru": "yandex.ru",
    "yandeks.ru": "yandex.ru",
    "yadnex.ru": "yandex.ru",
    "yandx.com": "yandex.ru",
    "mial.ru": "mail.ru",
    "maill.ru": "mail.ru",
    "mal.ru": "mail.ru",
    "inbox.ruu": "inbox.ru",
    "bk.ruu": "bk.ru",
    "rambler.ruu": "rambler.ru",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "10minutemail.com",
    "tempmail.com",
    "yopmail.com",
    "guerrillamail.com",
    "sharklasers.com",
    "dispostable.com",
    "getairmail.com",
}


def _normalize_phone(raw_phone: str) -> str:
    """Приводит российский номер к формату +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", raw_phone or "")
    if not digits:
        raise ValidationError("Номер телефона должен содержать цифры.")

    if len(digits) == 11:
        if digits.startswith("8"):
            digits = "7" + digits[1:]
        return f"+{digits}"
    if len(digits) == 10 and digits.startswith("9"):
        return f"+7{digits}"
    if len(digits) == 12 and digits.startswith("7"):
        return f"+{digits[:11]}"
    raise ValidationError("Неверный формат номера. Введите 11-значный мобильный номер.")


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text="Обязательное поле. Введите действующий email.",
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "phone_number")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "Пользователь с такой электронной почтой уже зарегистрирован!"
            )
        return email
    def clean_phone_number(self):
        phone_obj = self.cleaned_data.get("phone_number")
        phone_str = phone_obj.as_e164 if phone_obj else ""
        phone = _normalize_phone(phone_str)
        
        if CustomUser.objects.filter(phone_number=phone).exists():
            raise ValidationError("Этот номер телефона уже привязан к другому аккаунту.")
        return phone


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Имя пользователя")
    password = forms.CharField(label="Пароль")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["bio", "avatar", "address"]
        widgets = {
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "maxlength": 500,
                    "placeholder": "Расскажите о себе...",
                }
            ),
        }

    def clean_bio(self):
        bio = self.cleaned_data.get("bio", "").strip()
        if len(bio) > 500:
            raise ValidationError("Био не должно превышать 500 символов")
        return bio


class VerificationForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "000000",
                "class": "form-control text-center fs-2",
                "style": "letter-spacing: 5px;",
                "autocomplete": "off",
            }
        ),
        label="Введите 6-значный код из письма",
    )


class ChangePhoneForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["phone_number"]
        widgets = {
            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+7 (928) 075-74-01",
                    "required": True,
                }
            )
        }

    def clean_phone_number(self):
        phone = _normalize_phone(self.cleaned_data.get("phone_number", ""))

        qs = CustomUser.objects.filter(phone_number=phone)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Этот номер телефона уже привязан к другому аккаунту.")

        return phone


class ChangeEmailForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        error_messages={
            "required": "Поле электронной почты не может быть пустым.",
            "invalid": "Введите корректный адрес электронной почты (например, name@domain.com).",
        },
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "example@mail.com",
            }
        ),
    )

    class Meta:
        model = CustomUser
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if email.count("@") != 1:
            raise ValidationError(
                "Адрес электронной почты должен содержать ровно один символ '@'."
            )

        local_part, domain_part = email.rsplit("@", 1)

        if any(not char.isascii() for char in local_part):
            raise ValidationError(
                "Имя почтового ящика (до знака @) должно содержать только английские буквы, цифры и точки."
            )
        
        if domain_part in EMAIL_TYPO_MAP:
            domain_part = EMAIL_TYPO_MAP[domain_part]
            email = f"{local_part}@{domain_part}"

        if domain_part in DISPOSABLE_DOMAINS:
            raise ValidationError(
                "Регистрация через одноразовые почтовые службы запрещена."
            )

        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError(
                "Неверная структура домена. Убедитесь, что адрес написан правильно."
            )

        if "." not in domain_part or len(domain_part.split(".")[-1]) < 2:
            raise ValidationError(
                "Некорректная доменная зона (например, должно заканчиваться на .ru или .com)."
            )

        qs = CustomUser.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "Этот адрес электронной почты уже используется другим аккаунтом."
            )

        return email