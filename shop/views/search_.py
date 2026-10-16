from django.shortcuts import render
from django.utils import timezone

from ..models import (
    Category,
    Product,
    Categories_from_Category_2nd,
)
from shop.views.views import (
    get_cached_categories
)

from main.views.views import(
    rate_limit
)

from django.core.paginator import Paginator
from django.db.models import Q, Count

from django.utils.html import escape




@rate_limit('search', 20, 60)
def search_results(request):
    """Страница результатов поиска с товарами (бесконечный скролл HTMX) и сайдбаром"""
    query = request.GET.get("search", "").strip()
    is_htmx = request.headers.get("HX-Request") == "true" or request.headers.get("HX-Request")

    products = Product.objects.none()
    found_categories = Category.objects.none()
    found_subcategories = Categories_from_Category_2nd.objects.none()

    if query:
        base_products = Product.objects.filter(available=True).select_related("category2nd")

        products = base_products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        ).distinct().order_by("id")

        found_categories = Category.objects.filter(
            Q(name__icontains=query), available=True
        ).annotate(
            product_count=Count(
                "category_2nd__products",
                filter=Q(category_2nd__products__available=True),
            )
        )

        found_subcategories = Categories_from_Category_2nd.objects.filter(
            Q(brand__icontains=query) | Q(slug__icontains=query), available=True
        ).select_related("category")

        if not (products or found_categories or found_subcategories):
            products = base_products.filter(Q(category2nd__brand__icontains=query)).distinct().order_by("id")

    paginator = Paginator(products, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    total_results = paginator.count + len(found_categories) + len(found_subcategories) if query else 0

    context = {
        "query": escape(query),
        "products": page_obj,
        "categories": found_categories,
        "subcategories": found_subcategories,
        "total_results": total_results,
        "now": timezone.now(),
    }

    if is_htmx:
        return render(request, "shop/search_product_items.html", context)

    context.update({
        "all_categories": get_cached_categories().annotate(
            product_count=Count("category_2nd__products", filter=Q(category_2nd__products__available=True))
        )[:8],
        "all_subcategories": Categories_from_Category_2nd.objects.filter(available=True).select_related("category")[:8],
    })

    return render(request, "shop/search_results.html", context)

def global_search_htmx(request):
    """Быстрый живой поиск для HTMX с группировкой результатов"""
    query = request.GET.get("search", "").strip()

    if len(query) < 2:
        return render(request, "shop/partials/search_dropdown.html", {"results": {}, "query": query})

    products = Product.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query), available=True
    ).distinct()[:5]

    categories = Category.objects.filter(Q(name__icontains=query), available=True)[:3]

    subcategories = Categories_from_Category_2nd.objects.filter(
        Q(brand__icontains=query) | Q(slug__icontains=query), available=True
    )[:3]

    return render(
        request,
        "shop/partials/search_dropdown.html",
        {
            "results": {
                "products": products,
                "categories": categories,
                "subcategories": subcategories,
            },
            "query": query,
            "has_results": bool(products or categories or subcategories),
        },
    )