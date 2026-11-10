from django.shortcuts import render
from blog.models import Post, Category
from django.core.paginator import Paginator

def index(request):
    posts = Post.objects.filter(is_published=True).select_related('author', 'category').order_by('-created_at')
    categories = Category.objects.filter(available=True)
    latest_posts = posts[:4]

    paginator = Paginator(posts, 16)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {
        "posts": page_obj,
        "latest_posts": latest_posts,
        "categories": categories,
    }

    return render(request, "blog/dashboard.html", context)