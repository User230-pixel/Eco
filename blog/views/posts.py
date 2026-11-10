from django.urls import reverse
from django.shortcuts import render
from ..models import Post, Category, Tag, Comment, CommentLike
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch

def category_list(request):
    categories = Category.objects.filter(available=True)

    return render(request, "blog/categories.html", {"categories": categories})

def category_detail(request, slug):

    category = get_object_or_404(Category, slug=slug, available=True)

    posts = Post.objects.filter(
        category=category, 
        is_published=True
    ).select_related('author', 'category').order_by('-created_at')

    categories = Category.objects.filter(available=True)

    paginator = Paginator(posts, 16)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "category": category,
        "posts": page_obj,
        "categories": categories,
    }

    return render(request, "blog/category_detail.html", context)

def post_list(request):
    posts = Post.objects.filter(is_published=True).select_related('author', 'category').order_by('-created_at')
    categories = Category.objects.filter(available=True)

    paginator = Paginator(posts, 16)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {
        "posts": page_obj,
        "categories": categories,
    }

    return render(request, "blog/posts.html", context)

def post_detail(request, slug):
    post = get_object_or_404(
        Post.objects
        .select_related('author', 'category')
        .prefetch_related('tags'),
        slug=slug,
        is_published=True,
    )

    comments = (
        post.comments
        .filter(parent__isnull=True)
        .select_related("user")
        .prefetch_related(
            Prefetch("replies", queryset=Comment.objects.select_related("user")),
            "likes",
        )
        .order_by("-created_at")
    )

    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(CommentLike.objects.filter(
            from_user=request.user,
            to_comment__post=post,
        ).values_list("to_comment_id", flat=True))

    similar_posts = (
        Post.objects
        .filter(is_published=True, category=post.category)
        .exclude(pk=post.pk)
        .select_related('author', 'category')
        .order_by('-created_at')[:3]
    ) if post.category else Post.objects.none()

    context = {
        'post': post,
        'similar_posts': similar_posts,
        "comments": comments,
        "liked_comment_ids": liked_ids,
    }
    return render(request, 'blog/post_detail.html', context)

def tag_list(request):
    tags = Tag.objects.all()
    context = {
        "tags": tags
    }
    return render(request, "blog/tag_list.html", context)

def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)

    posts = (
        tag.posts
        .filter(is_published=True)
        .select_related('author', 'category')
        .prefetch_related('tags')
        .order_by('-created_at')
    )

    context = {
        'tag': tag,
        'posts': posts,
    }

    return render(request, "blog/tag_detail.html", context)
