from django.urls import path
from .views import (cart, payments, products, reviews, search_, views, profile, add_products, favorites)
from main.views import (auth)
from main.views.views import shopper_required

@shopper_required
def create_product_dispatcher(request, *args, **kwargs):
    if request.method == "POST":
        return add_products.create_product_post(request, *args, **kwargs)
    return add_products.create_product_get(request, *args, **kwargs)

app_name = "shop"

urlpatterns = [
    path("", products.product_list, name="product_list"),
    
    path("categories/", products.category_list, name="category_list"),
    path("category/<str:category_slug>/", products.category_products, name="product_list_by_category"),
    
    path("product/<int:id>/<str:slug>/", products.product_detail, name="product_detail"),
    path("product/<int:product_id>/review/", reviews.add_review_htmx, name="add_review_htmx"),
    path("product/add/", create_product_dispatcher, name="create_product"),  
    
    path("cart/", cart.cart_detail, name="cart_detail"),
    path("cart/add/<int:id>/<str:slug>/", cart.add_to_cart, name="add_to_cart"),
    path("cart/increase/<int:item_id>/", cart.increase_cart_item, name="increase_cart_item"),
    path("cart/decrease/<int:item_id>/", cart.decrease_cart_item, name="decrease_cart_item"),
    path("cart/remove/<int:item_id>/", cart.remove_from_cart, name="remove_from_cart"),
    path("cart/clear/", cart.clear_cart, name="clear_cart"),
    path("cart/checkout/", cart.checkout, name="checkout"),
    
    path("payment/webhook/", payments.yookassa_webhook, name="yookassa_webhook"),
    path("payment/success/", payments.payment_success, name="payment_success"),
    path("cart/payment/fail/", payments.payment_fail, name="payment_fail"),

    path("search/htmx/", search_.global_search_htmx, name="global_search_htmx"),
    path("search/", search_.search_results, name="search_results"),

    path("profile/", profile.profile_view, name="profile"),
    path("profile/update/", profile.profile_update, name="profile_update"),

    path("product/<int:id>/<str:slug>/review/", reviews.add_review_htmx, name="add_review"),
    path(
        "review/<int:review_id>/reply/",
        reviews.add_seller_reply,
        name="add_seller_reply",
    ),
    path(
        "review/<int:review_id>/reply/edit/",
        reviews.edit_seller_reply,
        name="edit_seller_reply",
    ),
    path("favorite/<int:product_id>/toggle/", favorites.toggle_favorite, name="toggle_favorite"),
    path("favorites/", favorites.favorites_list, name="favorites_list"),
    path("favorites/clear/", favorites.clear_favorites, name="clear_favorites"),
]