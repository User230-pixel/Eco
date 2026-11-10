from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import escape

from blog.models import Post, Category, Tag
from main.views.views import rate_limit


@rate_limit('search', 20, 60)
def search_results(request):
    query = request.GET.get("search", "").strip()
    is_htmx = request.headers.get("HX-Request") == "true" or request.headers.get("HX-Request")

    posts = Post.objects.none()
    found_categories = Category.objects.none()
    found_tags = Tag.objects.none()

    if query:
        base_posts = (
            Post.objects
            .filter(is_published=True)
            .select_related("author", "category")
            .prefetch_related("tags")
        )

        posts = base_posts.filter(
            Q(title__icontains=query) | Q(text__icontains=query)
        ).distinct().order_by("-created_at")

        found_categories = (
            Category.objects
            .filter(Q(name__icontains=query), available=True)
            .annotate(
                post_count=Count(
                    "posts",
                    filter=Q(posts__is_published=True),
                )
            )
        )

        found_tags = (
            Tag.objects
            .filter(Q(name__icontains=query) | Q(slug__icontains=query))
            .annotate(
                post_count=Count(
                    "posts",
                    filter=Q(posts__is_published=True),
                )
            )
        )

        if not (posts or found_categories or found_tags):
            posts = base_posts.filter(Q(author__username__icontains=query)).distinct().order_by("-created_at")

    paginator = Paginator(posts, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    total_results = paginator.count + len(found_categories) + len(found_tags) if query else 0

    context = {
        "query": escape(query),
        "posts": page_obj,
        "categories": found_categories,
        "tags": found_tags,
        "total_results": total_results,
        "now": timezone.now(),
    }

    if is_htmx:
        return render(request, "blog/partials/_search_post_items.html", context)

    context.update({
        "all_categories": (
            Category.objects
            .filter(available=True)
            .annotate(post_count=Count("posts", filter=Q(posts__is_published=True)))[:8]
        ),
        "all_tags": Tag.objects.annotate(
            post_count=Count("posts", filter=Q(posts__is_published=True))
        ).order_by("name")[:8],
    })

    return render(request, "blog/search_results.html", context)


def global_search_htmx(request):
    query = request.GET.get("search", "").strip()

    if len(query) < 2:
        return render(request, "blog/partials/search_dropdown.html", {"results": {}, "query": query})

    posts = (
        Post.objects
        .filter(Q(title__icontains=query) | Q(text__icontains=query), is_published=True) 
        .select_related("author", "category")
        .distinct()[:5]
    )

    categories = Category.objects.filter(Q(name__icontains=query), available=True)[:3]

    tags = Tag.objects.filter(Q(name__icontains=query) | Q(slug__icontains=query))[:3]

    return render(
        request,
        "blog/partials/_search_dropdown.html",
        {
            "results": {
                "posts": posts,
                "categories": categories,
                "tags": tags,
            },
            "query": query,
            "has_results": bool(posts or categories or tags),
        },
    )