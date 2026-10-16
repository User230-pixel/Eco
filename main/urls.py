from django.urls import path
from .views import (auth, profile, send, main, views, vacan, notifications, driver)

app_name = "main"

urlpatterns = [
    path("", main.index, name="index"),
    path("jobs", main.jobs, name="jobs"),

    path("auth/login/", auth.get_login_form, name="get_login_form"),
    path("auth/register/", auth.get_register_form, name="get_register_form"),
    path("auth/login/submit/", auth.login_submit, name="login_submit"),
    path("auth/register/submit/", auth.register_submit, name="register_submit"),
    path("verify/", send.get_verify_form, name="get_verify_form"),
    path("verify/submit/", send.verify_code_page, name="verify_code_page"),
    path('verify/verify-phone/', auth.verify_phone_page, name='verify_phone_page'),
    path('resend-verification/', send.resend_verification_code, name='resend_verification'),

    path("users/<int:user_id>/", profile.profile, name="profile"),
    path("users/<int:user_id>/like/", profile.toggle_profile_like, name="toggle_profile_like"),
    path("users/<int:user_id>/subscribe/", profile.toggle_subscription, name="toggle_subscription"),

    
    path("cabinet/", profile.cabinet, name="cabinet"),
    path("cabinet/update/", profile.cabinet_update, name="cabinet_update"),

    #path("profile/update/", profile.profile_update, name="profile_update"),

    path("users", vacan.users_list_view, name="users"),

    path("notifications", notifications.notifications, name="notifications"),
    path("notifications/is-read", notifications.is_read_update, name="is_read_update"),
    path('notifications/delete/', notifications.delete_notification, name='delete_notification'),

    path("users/<int:user_id>/delete/", vacan.delete_user, name="delete_user"),

    path("driver/orders/", driver.driver_orders, name="driver_orders"),
    path("driver/orders/<int:order_id>/status/",
         driver.driver_update_order_status,
         name="driver_update_order_status"),
]
