from django.urls import path

from settings_app.views import (
    views, verify, secure
)

app_name = "settings_app"

urlpatterns = [
    path('', views.settings_dashboard, name='dashboard'),

    path('password-reset/', secure.smart_password_reset, name='smart_password_reset'),
    path('password-reset/resend/', secure.resend_password_reset_code, name='resend_password_reset_code'),

    path("edit-phone/", secure.change_phone_view, name="change_phone"),
    path("edit-phone/resend/", verify.resend_phone_verification_code, name="change_phone_resend"),

    path("edit-email/", secure.change_email_view, name="edit-email"),
    path("edit-email/resend", secure.resend_email_code, name="edit-email-resend"),

    path("logout/", secure.logout_view, name="logout"),
    path("logout/all", secure.logout_all, name="logout_all"),

    path("delete-account/", secure.delete_account, name="delete_account"),
]
