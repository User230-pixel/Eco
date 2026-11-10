from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError

from blog.models import Post, Comment, CommentLike
from blog.forms import CommentForm
from main.models import CustomUser

@login_required(login_url='main:get_login_form')
@require_POST
def add_comment(request, slug):
    post = get_object_or_404(Post, slug=slug, is_published=True)
    is_htmx = bool(request.headers.get("HX-Request"))

    comment_form = CommentForm(request.POST)

    if comment_form.is_valid == False:
        if is_htmx:
            return render(request, "blog/partials/_comment_form.html", {"form": comment_form, "post": post}, status=400)
        messages.error("Ошибка отправки комментария")
        return redirect(post.get_absolute_url())

    comment = comment_form.save(commit=False)
    comment.post = post
    comment.user = request.user

    if comment.parent_id and comment.parent.post_id != post.id:
        if is_htmx:
            return HttpResponseBadRequest("Родительский комментарий из другого поста.")
        messages.error("Родительский комментарий из другого поста.")
        return redirect(post.get_absolute_url())

    comment.save()

    if is_htmx:
        return render(request, "blog/partials/_comment.html", {"comment": comment, "post": post,})
    
    messages.success(request, "Комментарий добавлен.")
    return redirect(post.get_absolute_url() + f"#comment-{comment.id}")

@login_required(login_url='main:get_login_form')
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    is_htmx = bool(request.headers.get("HX-Request"))

    if comment.user_id == request.user.id or request.user.is_superuser or request.user.role_moderator:
        comment.delete()

        if is_htmx:

            return render(request, "blog/partials/_comment_deleted.html")
        messages.success("Вы удалили комментарий.")
        return redirect(comment.get_absolute_url)
    
    if is_htmx:
        return HttpResponseBadRequest("У ван нет полномочий.")
    
    messages.error("У вас нет полномочий")
    return redirect(comment.get_absolute_url)

@login_required(login_url='main:get_login_form')
@require_POST
def comment_like_toggle(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    is_htmx = bool(request.headers.get("HX-Request"))

    like, created = CommentLike.objects.get_or_create(from_user = request.user, to_comment=comment)

    if not created:
        like.delete()
        liked = False
    liked = True

    likes_count = comment.likes.count()
    context = {
        "comment": comment,
        "liked": liked,
        "likes_count": likes_count,
    }
    if is_htmx:
        return render(request, "blog/partials/_comment_like_button.html", context)
    return JsonResponse({"liked": liked, "likes_count": likes_count})