from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import FavoriteProducts, Product
from shop.views.views import get_cached_categories


@login_required(login_url="main:get_login_form")
@require_POST
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, id=product_id, available=True)
    favorite = FavoriteProducts.objects.filter(user=request.user, product=product).first()

    if favorite:
        favorite.delete()
        is_favorite = False
    else:
        FavoriteProducts.objects.create(user=request.user, product=product)
        is_favorite = True

    if request.headers.get("HX-Request"):
        return render(request, "shop/partials/_favorite_button.html", {
            "product": product,
            "is_favorite": is_favorite,
        })

    return_to = request.POST.get("return_to", "")
    if return_to and url_has_allowed_host_and_scheme(
        return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(return_to)
    return redirect(product.get_absolute_url())


@login_required(login_url="main:get_login_form")
def favorites_list(request):
    favorites = FavoriteProducts.objects.filter(
        user=request.user,
        product__available=True,
    ).select_related("product__category2nd__category", "product__user")

    return render(
        request,
        "shop/favorites.html",
        {
            "favorites": favorites,
            "categories": get_cached_categories(),
        },
    )

@login_required
@require_POST
def clear_favorites(request):
    FavoriteProducts.objects.filter(user=request.user).delete()
    return redirect("shop:favorites_list")