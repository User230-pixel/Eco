from django.contrib import admin
from .models import (
    Category,
    Categories_from_Category_2nd,
    Product,
    Cart,
    CartItem,
    OrderCounter,
    OrderItem,
    Order,
    Review,
)
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.contrib.auth import get_user_model


from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

User = get_user_model

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Categories_from_Category_2nd)
class Category2nd(admin.ModelAdmin):
    list_display = ["brand", "category", "slug", "available"]

    list_filter = ["category", "available"]

    prepopulated_fields = {"slug": ("brand",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "category2nd",
        "price",
        "available",
        "created_at",
        "updated_at",
        "stock",
        "user",
    ]
    list_filter = ["available", "created_at", "updated_at", "category2nd", "stock", "user"]
    list_editable = ["price", "available", "stock", "user"]
    prepopulated_fields = {"slug": ("name",)}


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ["product", "quantity", "get_cost_display"]
    readonly_fields = ["get_cost_display"]
    verbose_name = "Товар в корзине"
    verbose_name_plural = "Товары в этой корзине"

    def get_cost_display(self, obj):
        if obj.id:
            return f"{obj.get_cost()} руб."
        return "0 руб."

    get_cost_display.short_description = "Стоимость позиции"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "get_total_quantity_display",
        "get_total_price_display",
        "created_at",
        "updated_at",
    ]
    list_display_links = ["id", "user"]
    search_fields = [
        "user__username",
        "user__email",
    ]
    list_filter = ["created_at", "updated_at"]
    inlines = [CartItemInline]

    def get_total_quantity_display(self, obj):
        return f"{obj.get_total_quantity()} шт."

    get_total_quantity_display.short_description = "Всего товаров"

    def get_total_price_display(self, obj):
        return f"{obj.get_total_price()} руб."

    get_total_price_display.short_description = "Общая сумма"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "cart",
        "product",
        "quantity",
        "get_cost_display",
        "created_at",
    ]
    list_filter = ["created_at", "product"]
    search_fields = ["cart__user__username", "product__name"]

    def get_cost_display(self, obj):
        return f"{obj.get_cost()} руб."

    get_cost_display.short_description = "Стоимость"


@admin.register(OrderCounter)
class OrderCounterAdmin(admin.ModelAdmin):
    list_display = ["id", "last_number"]
    list_display_links = ["id", "last_number"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "price", "quantity"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "get_total_quantity_display",
        "total_price",
        "status",
        "created_at",
        "yookassa_payment_id",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "user__username", "user__email", "delivery_address"]
    list_editable = ["status"]
    inlines = [OrderItemInline]

    def get_total_quantity_display(self, obj):
        return obj.get_total_quantity()

    get_total_quantity_display.short_description = "Кол-во товаров"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "product_link",
        "short_advantages",
        "short_disadvantages",
        "created_at",
    )

    list_display_links = ("id", "short_advantages")

    list_filter = ("created_at",)

    search_fields = ("text_1", "text_0", "user__username", "product__name")

    list_per_page = 20

    def short_advantages(self, obj):
        if obj.text_1 and len(obj.text_1) > 40:
            return f"➕ {obj.text_1[:40]}..."
        return f"➕ {obj.text_1}" if obj.text_1 else "-"

    short_advantages.short_description = "Преимущества"

    def short_disadvantages(self, obj):
        if obj.text_0 and len(obj.text_0) > 40:
            return f"➖ {obj.text_0[:40]}..."
        return f"➖ {obj.text_0}" if obj.text_0 else "-"

    short_disadvantages.short_description = "Недостатки"

    def user_link(self, obj):
        if obj.user:
            url = f"/admin/auth/user/{obj.user.id}/change/"
            return format_html(
                '<a href="{}" style="font-weight: 600; color: 447e9b;">{}</a>',
                url,
                obj.user.username,
            )
        return "-"

    user_link.short_description = "Покупатель"

    def product_link(self, obj):
        if obj.product:
            url = f"/admin/shop/product/{obj.product.id}/change/"
            return format_html(
                '<a href="{}" style="color: 447e9b;">{}</a>', url, obj.product.name
            )
        return "-"

    product_link.short_description = "Товар"
