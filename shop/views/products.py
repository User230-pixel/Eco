from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.contrib.messages import get_messages

from ..models import (
    Category,
    Product,
    Categories_from_Category_2nd,
    Cart,
    OrderItem,
    FavoriteProducts
)

from shop.views.views import (
    get_cached_categories
)

from django.core.paginator import Paginator
from django.contrib.auth import get_user_model

User = get_user_model()

def product_list(request):
    storage = get_messages(request)
    for _ in storage:
        pass
    """Главная страница каталога с поддержкой живого поиска HTMX и бесконечного скролла"""
    products = Product.objects.filter(available=True).select_related('category2nd', 'user')

    search_query = request.GET.get("search", "").strip()
    if search_query:
        products = products.filter(name__icontains=search_query)

    subcat_id = None
    subcat_raw = request.GET.get("subcategory", "").strip()
    if subcat_raw:
        try:
            subcat_id = int(subcat_raw)
        except ValueError:
            subcat_id = None
    if subcat_id:
        products = products.filter(category2nd_id=subcat_id)

    seller_id = None
    seller_raw = request.GET.get("filtered_user_id", "").strip()

    if seller_raw:
        try:
            seller_id = int(seller_raw)
        except ValueError:
            seller_id = None
    if seller_id:
        products = products.filter(user_id=seller_id)


    sort_by = request.GET.get("sort", "default")
    ALLOWED_SORTS = ['default', 'price_asc', 'price_desc', 'name_asc']
    if sort_by not in ALLOWED_SORTS:
        sort_by = 'default'

    if sort_by == "price_asc":
        products = products.order_by("price", "id")
    elif sort_by == "price_desc":
        products = products.order_by("-price", "id")
    elif sort_by == "name_asc":
        products = products.order_by("name", "id")
    else:
        products = products.order_by("id")

    paginator = Paginator(products, 16)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "products": page_obj,
        "selected_subcat": subcat_id,
        "search_query": search_query,
        "sort_by": sort_by,
        "selection_mode": request.GET.get("mode") == "select",
        "current_seller_id": seller_id,
    }

    if request.headers.get("HX-Request"):
        if request.GET.get("page"):
            return render(request, "shop/product/_product_items.html", context)
        return render(request, "shop/product/table.html", context)


    context.update({
        "categories": get_cached_categories(),
        "subcategories": Categories_from_Category_2nd.objects.filter(available=True),
        "sellers_list": User.objects.filter(is_active=True),  
        "related_products": Product.objects.filter(available=True).order_by('-id')[:4], 
        "now": timezone.now(),
    })

    return render(request, "shop/product/list.html", context)

def category_list(request):
    """Страница всех категорий"""
    categories = get_cached_categories()
    return render(
        request,
        "shop/product/categories.html",
        {
            "categories": categories,
        },
    )

def category_products(request, category_slug):
    """Товары конкретной категории с поддержкой живого поиска HTMX и фильтрации брендов"""
    category = get_object_or_404(Category, slug=category_slug, available=True)
    
    products = Product.objects.filter(category2nd__category=category, available=True).select_related('category2nd')

    subcat_id = None
    subcat_raw = request.GET.get("subcategory", "").strip()
    if subcat_raw:
        try:
            subcat_id = int(subcat_raw)
        except ValueError:
            subcat_id = None
    if subcat_id:
        products = products.filter(category2nd_id=subcat_id)

    seller_id = None
    seller_raw = request.GET.get("filtered_user_id", "").strip()

    if seller_raw:
        try:
            seller_id = int(seller_raw)
        except ValueError:
            seller_id = None
    if seller_id:
        products = products.filter(user_id=seller_id)

    search_query = request.GET.get("search", "").strip()
    if search_query:
        products = products.filter(name__icontains=search_query)

    sort_by = request.GET.get("sort", "default")
    ALLOWED_SORTS = ['default', 'price_asc', 'price_desc', 'name_asc']
    if sort_by not in ALLOWED_SORTS:
        sort_by = 'default'
    
    if sort_by == "price_asc":
        products = products.order_by("price", "id")
    elif sort_by == "price_desc":
        products = products.order_by("-price", "id")
    elif sort_by == "name_asc":
        products = products.order_by("name", "id")
    else:
        products = products.order_by("id")

    paginator = Paginator(products, 16)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "category": category,
        "products": page_obj,
        "selected_subcat": subcat_id,
        "sellers_list": User.objects.filter(is_active=True),
        "search_query": search_query,
        "sort_by": sort_by,
        "selection_mode": request.GET.get("mode") == "select",
    }

    if request.headers.get("HX-Request"):
        return render(request, "shop/product/table.html", context)

    context.update({
        "categories": get_cached_categories(),
        "subcategories": Categories_from_Category_2nd.objects.filter(category=category, available=True),
        "now": timezone.now(),
    })

    return render(request, "shop/product/category_detail.html", context)

def product_detail(request, id, slug):
    """Детальная страница товара"""
    product = get_object_or_404(Product, id=id, slug=slug, available=True)

    orders = False
    if request.user.is_authenticated:
        orders = OrderItem.objects.filter(order__user=request.user, product=product).exists()

    quantity = 0
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            quantity = getattr(cart.items.filter(product=product).first(), "quantity", 0)

    category = product.category  
    subcategory = product.category2nd  

    is_favorite = False
    if request.user.is_authenticated:
        is_favorite = FavoriteProducts.objects.filter(
            user=request.user, product=product
        ).exists()

    product_recommendations = Product.objects.filter(
        category2nd=product.category2nd, available=True
    ).exclude(id=product.id).order_by('id')[:4]

    return render(
        request,
        "shop/product/detail.html",
        {
            "product": product,
            "product_recommendations": product_recommendations,
            "categories": get_cached_categories(),
            "category": category,  
            "subcategory": subcategory,  
            "quantity": quantity,  
            "orders": orders,
            "is_favorite": is_favorite,
        },
    )