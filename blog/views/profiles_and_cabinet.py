from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse, reverse_lazy

from blog.forms import AccountForm
from blog.models import Post, Comment
from main.models import Profile, ProfileLike, Subscription

from main.views.views import blogger_required
from django.db.models import Q

User = get_user_model()

@blogger_required
@login_required(login_url='main:get_login_form')
def profile(request, pk):
    profile_user = get_object_or_404(User, Q(role_blogger=True) | Q(is_superuser=True), pk=pk)
    profile_obj, _ = Profile.objects.get_or_create(user=profile_user)
    
    posts = (Post.objects.filter(is_published=True, author=profile_user)
             .select_related('category')
             .prefetch_related('tags')
             .order_by('-created_at'))

    
    paginator1 = Paginator(posts, 8)
    page_obj1 = paginator1.get_page(request.GET.get('page', 1))


    comments = Comment.objects.filter(user=profile_user).order_by('-created_at')

    is_auth = request.user.is_authenticated

    #from blog.models import CommentLike
    #comment_to_like_user = CommentLike.objects.filter(to_comment__author=profile_user)
    #comment_from_like_user = CommentLike.objects.filter(from_user=profile_user)

    user_is_subscribed = is_auth and Subscription.objects.filter(subscriber=request.user, to_profile=profile_obj).exists()
    user_has_liked = is_auth and ProfileLike.objects.filter(from_user=request.user, to_profile=profile_obj).exists()    



    paginator2 = Paginator(comments, 20)
    page_obj2 = paginator2.get_page(request.GET.get('c_page', 1))


    context = {
        'posts_count': posts.count(),
        'comments': page_obj2,
        'comments_count': comments.count(),
        'profile_user': profile_user,
        'profile_obj': profile_obj,
        'posts': page_obj1,
        'is_owner': request.user.is_authenticated and request.user.pk == profile_user.pk,
        'user_is_subscribed': user_is_subscribed,
        'user_has_liked': user_has_liked,
    }

    return render(request, "blog/profile.html", context)



@login_required(login_url='main:get_login_form')
def cabinet(request):
    profiles, _ = Profile.objects.get_or_create(user=request.user)

    posts_qs = Post.objects.filter(author=request.user)
    total_k = posts_qs.count()
    published_k = posts_qs.filter(is_published=True).count()

    return render(request, 'blog/cabinet.html', {
        'user_obj': request.user,
        'profile': profiles,
        'stats': {
            'posts_total': total_k,
            'posts_published': published_k,
            'posts_drafts': total_k - published_k,
            'comments_total': Comment.objects.filter(user=request.user).count(),
        },
    })

@login_required(login_url='main:get_login_form')
def cabinet_edit(request):
    profiles, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = AccountForm(request.POST, instance=request.user)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Изменено")
            return redirect("blog:cabinet")
    else:
        form = AccountForm(instance=request.user)

    context = {
        'form': form,
        'profile': profiles
    }

    return render(request, "blog/cabinet_edit.html", context)

@login_required(login_url='main:get_login_form')
def my_posts(request):
    posts = Post.objects.select_related('category').order_by('-created_at').filter(author=request.user)

    status = request.GET.get('status', 'all')

    if status == 'published':
        posts = posts.filter(is_published=True)
    elif status == 'drafts':
        posts = posts.filter(is_published=False)

    paginator = Paginator(posts, 16)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'posts': page_obj,
        'status': status,
    }

    return render(request, 'blog/my_posts.html', context)