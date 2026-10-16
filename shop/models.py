from django.db import models
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random
from django.conf import settings
from django.db.models import Sum

from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from PIL import Image
import os
import uuid
from phonenumber_field.modelfields import PhoneNumberField

from main.models import (
    CustomUser
)

import logging

class Category(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    available = models.BooleanField(default=True)
    image = models.ImageField(
        _("Изображение"), upload_to="products/%Y/%m/%d", blank=True
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product_list_by_category", args=[self.slug])


class Categories_from_Category_2nd(models.Model):
    category = models.ForeignKey(
        Category, related_name="category_2nd", on_delete=models.CASCADE
    )
    brand = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    available = models.BooleanField(default=True)
    image = models.ImageField(
        _("Изображение"), upload_to="products/%Y/%m/%d", blank=True
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("brand",)
        verbose_name = "Подкатегория"
        verbose_name_plural = "Подкатегории"

    def __str__(self):
        return self.brand

    def get_absolute_url(self):
        return reverse("shop:product_list_by_category", args=[self.slug])


class Product(models.Model):
    category2nd = models.ForeignKey(
        Categories_from_Category_2nd, related_name="products", on_delete=models.CASCADE
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    image = models.ImageField(
        _("Изображение"), upload_to="products/%Y/%m/%d", blank=True
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stock = models.PositiveIntegerField(default=10, verbose_name="Количество на складе")

    class Meta:
        ordering = ("name",)
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.id, self.slug])

    @property
    def category(self):
        """Возвращает главную категорию через category2nd"""
        return self.category2nd.category if self.category2nd else None

    def clean(self):
        super().clean()
        if hasattr(self, 'user') and self.user:
            if not (self.user.role_shopper or self.user.role_admin or self.user.is_superuser):
                raise ValidationError("Добавление товаров разрешено только продавцам или администраторам.")



User = get_user_model()

class Cart(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name="Владелец корзины",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"

    def __str__(self):
        return f"Корзина пользователя {self.user.username}"

    def get_total_price(self):
        return sum(item.get_cost() for item in self.items.filter(is_selected=True))

    def get_total_quantity(self):
        return sum(item.quantity for item in self.items.filter(is_selected=True))


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name="Корзина"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="Товар")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    is_selected = models.BooleanField(default=True, verbose_name="Отмечен для покупки")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Элемент корзины"
        verbose_name_plural = "Элементы корзины"
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.product.name} ({self.quantity} шт.)"

    def get_cost(self):
        return self.product.price * self.quantity


class OrderCounter(models.Model):
    last_number = models.PositiveIntegerField(
        default=0, verbose_name="Номер последнего заказа"
    )


class VerificationCode(models.Model):
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=22, blank=True, null=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def generate_code(self):
        """Генерирует случайный 6-значный код."""
        import random
        self.code = f"{random.randint(100000, 999999)}"
        self.save()
        return self.code

    def is_valid(self):
        """Проверяет, не истек ли код (активен 5 минут)."""
        expiry_time = self.created_at + timedelta(minutes=5)
        return not self.is_used and timezone.now() <= expiry_time

    def __str__(self):
        return f"Код для {self.email}: {self.code}"


class Order(models.Model):
    """Модель заказа"""

    STATUS_CHOICES = [
        ("awaiting_payment", "Ожидает оплаты"),
        ("pending", "В обработке"),
        ("processing", "Готовится к отправке"),
        ("shipped", "Отправлен"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменен"),
        ("failed", "Ошибка оплаты"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Пользователь",
    )
    created_at = models.DateTimeField(
        default=timezone.now, verbose_name="Дата создания"
    )
    delivery_address = models.TextField(verbose_name="Адрес доставки")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус"
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Общая сумма"
    )
    comment = models.TextField(
        blank=True, null=True, verbose_name="Комментарий к заказу"
    )
    yookassa_payment_id = models.CharField(
        max_length=100, blank=True, null=True, db_index=True, unique=True
    )

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ {self.id} - {self.user.username}"

    def get_total_quantity(self):
        """Общее количество товаров в заказе"""
        result = self.items.aggregate(total=Sum("quantity"))
        return result["total"] or 0


class OrderItem(models.Model):
    """Модель товара в заказе"""

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="items", verbose_name="Заказ"
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="order_items",
        verbose_name="Товар",
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Цена на момент покупки"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = "Товар в заказе"
        verbose_name_plural = "Товары в заказе"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    def get_total_price(self):
        return self.price * self.quantity


class Review(models.Model):
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Товар",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Пользователь",
    )
    text_0 = models.TextField(max_length=500, verbose_name="Недостатки")
    text_1 = models.TextField(max_length=500, verbose_name="Преимущества")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата публикации")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

    def __str__(self):
        return f"Отзыв от {self.user.username} на {self.product.name}"

class SellerReply(models.Model):
    review = models.OneToOneField(
        Review,
        related_name="seller_reply",
        on_delete=models.CASCADE,
    )
    seller = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
    )
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ответ продавца на отзыв #{self.review_id}"


class FavoriteProducts(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="Пользователь",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
        verbose_name="Товар",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]
        verbose_name = "Избранное"
        verbose_name_plural = "Избранное"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.product.name}"