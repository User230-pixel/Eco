from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdminForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        
        role_user = cleaned_data.get('role_user', False)
        role_driver = cleaned_data.get('role_driver', False)
        role_blogger = cleaned_data.get('role_blogger', False)
        role_moderator = cleaned_data.get('role_moderator', False)
        role_admin = cleaned_data.get('role_admin', False)
        role_shopper = cleaned_data.get('role_shopper', False)

        selected_count = sum([role_user, role_driver, role_blogger, role_shopper, role_moderator, role_admin])

        if selected_count > 2:
            raise forms.ValidationError("Вы можете выбрать не более 2 ролей одновременно!")
        if selected_count == 0:
            raise forms.ValidationError("Необходимо выбрать минимум одну роль!")
        
        return cleaned_data


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    form = CustomUserAdminForm

    list_display = [
        "username",
        "email",
        "phone_number",
        "role_user",
        "role_driver",
        "role_blogger",
        "role_shopper",
        "role_moderator",
        "role_admin",
        "is_staff",
        "is_active",
        "action_points",
        "action_points_2",
    ]

    list_editable = (
        "action_points", 
        "action_points_2", 
        "role_user", 
        "role_driver", 
        "role_blogger", 
        "role_shopper",
        "role_moderator", 
        "role_admin",
    )
    
    list_filter = ("role_user", "role_driver", "role_blogger", "role_shopper", "role_moderator", "role_admin", "is_staff", "is_active")
    search_fields = ("username", "email", "phone_number")

    fieldsets = UserAdmin.fieldsets + (
        ("Роли и контакты", {
            "fields": ("role_user", "role_driver", "role_blogger", "role_shopper", "role_moderator", "role_admin", "phone_number")
        }),
        ("Бонусы", {"fields": ("action_points", "action_points_2")}),
        ("Данные водителя", {
            "fields": ("car_model", "car_number", "experience_years"),
            "classes": ("collapse",),
        }),
        ("Данные blogger", {
            "fields": ("instagram", "youtube", "followers_count"),
            "classes": ("collapse",),
        }),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "phone_number",
                    "role_user",
                    "role_driver",
                    "role_blogger",
                    "role_shopper",
                    "role_moderator",
                    "role_admin",
                    "password1",
                    "password2",
                    "action_points",
                    "action_points_2",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        from django.contrib.contenttypes.models import ContentType
        original_get_for_model = ContentType.objects.get_for_model
        ContentType.objects.get_for_model = lambda *args, **kwargs: None
        try:
            super().save_model(request, obj, form, change)
        finally:
            ContentType.objects.get_for_model = original_get_for_model

    def delete_model(self, request, obj):
        from django.contrib.contenttypes.models import ContentType
        original_get_for_model = ContentType.objects.get_for_model
        ContentType.objects.get_for_model = lambda *args, **kwargs: None
        try:
            super().delete_model(request, obj)
        finally:
            ContentType.objects.get_for_model = original_get_for_model

    def log_change(self, request, obj, message):
        return None

    def log_addition(self, request, obj, message):
        return None

    def log_deletions(self, request, queryset):
        return None

    def changelist_view(self, request, extra_context=None):
        from django.contrib.contenttypes.models import ContentType
        original_get_for_model = ContentType.objects.get_for_model
        ContentType.objects.get_for_model = lambda *args, **kwargs: None
        try:
            return super().changelist_view(request, extra_context=extra_context)
        finally:
            ContentType.objects.get_for_model = original_get_for_model

from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'message', 'notification_type', 'is_read', 'created_at')
    
    list_display_links = ('id', 'title')
    
    list_filter = ('notification_type', 'is_read', 'created_at')
    
    search_fields = ('user__username', 'title', 'message')
    
    ordering = ('-created_at',)
    
    list_per_page = 50

from django.contrib import admin
from django.utils.html import format_html
from main.models import Profile, ProfileLike, Subscription


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user_link",
        "bio_short",
        "avatar_preview",
        "likes_count",
        "subscribers_count",
    )
    list_filter = ("likes_count", "subscribers_count")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "bio")
    readonly_fields = ("likes_count", "subscribers_count", "avatar_preview_big")
    list_per_page = 50
    ordering = ("-likes_count",)
    list_select_related = ("user",)

    fieldsets = (
        ("Пользователь", {
            "fields": ("user",)
        }),
        ("Публичное", {
            "fields": ("bio", "avatar", "avatar_preview_big")
        }),
        ("Счётчики (только чтение)", {
            "fields": ("likes_count", "subscribers_count"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Пользователь", ordering="user__username")
    def user_link(self, obj):
        if not obj.user:
            return "—"
        url = f"/admin/{obj.user._meta.app_label}/{obj.user._meta.model_name}/{obj.user.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Био")
    def bio_short(self, obj):
        if not obj.bio:
            return "—"
        return obj.bio[:60] + ("…" if len(obj.bio) > 60 else "")

    @admin.display(description="Аватар")
    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:32px;height:32px;border-radius:4px;object-fit:cover;">',
                obj.avatar.url
            )
        return "—"

    @admin.display(description="Аватар (превью)")
    def avatar_preview_big(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="max-width:200px;border-radius:4px;">',
                obj.avatar.url
            )
        return "—"


@admin.register(ProfileLike)
class ProfileLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "from_user_link", "to_user_link", "created_at")
    list_filter = ("created_at",)
    search_fields = ("from_user__username", "to_profile__user__username")
    autocomplete_fields = ("from_user", "to_profile")
    list_select_related = ("from_user", "to_profile__user")
    date_hierarchy = "created_at"
    list_per_page = 100

    @admin.display(description="Кто лайкнул", ordering="from_user__username")
    def from_user_link(self, obj):
        url = f"/admin/{obj.from_user._meta.app_label}/{obj.from_user._meta.model_name}/{obj.from_user.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.from_user.username)

    @admin.display(description="Кого", ordering="to_profile__user__username")
    def to_user_link(self, obj):
        url = f"/admin/{obj.to_profile.user._meta.app_label}/{obj.to_profile.user._meta.model_name}/{obj.to_profile.user.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.to_profile.user.username)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "subscriber_link", "to_user_link", "created_at")
    list_filter = ("created_at",)
    search_fields = ("subscriber__username", "to_profile__user__username")
    autocomplete_fields = ("subscriber", "to_profile")
    list_select_related = ("subscriber", "to_profile__user")
    date_hierarchy = "created_at"
    list_per_page = 100

    @admin.display(description="Подписчик", ordering="subscriber__username")
    def subscriber_link(self, obj):
        url = f"/admin/{obj.subscriber._meta.app_label}/{obj.subscriber._meta.model_name}/{obj.subscriber.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.subscriber.username)

    @admin.display(description="На кого", ordering="to_profile__user__username")
    def to_user_link(self, obj):
        url = f"/admin/{obj.to_profile.user._meta.app_label}/{obj.to_profile.user._meta.model_name}/{obj.to_profile.user.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.to_profile.user.username)