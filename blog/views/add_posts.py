from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.text import slugify
from ..forms import PostForm, TagForm
from ..models import Post, Tag
from main.views.views import blogger_required

@blogger_required
def post_create(request):
    
    #GET    
    post_form = PostForm()
    tag_form = TagForm(prefix="tag")

    #POST
    if request.method == "POST":
        post_form =PostForm(request.POST, request.FILES)
        tag_form = TagForm(request.POST, prefix="tag")

        if post_form.is_valid() and tag_form.is_valid():
            post = post_form.save(commit=False)
            post.author = request.user
            if not post.slug:
                post.slug = slugify(post.title)
            post.category = post_form.cleaned_data['main_category']
            post.save()
            post_form.save_m2m()

            tag, _ = Tag.objects.get_or_create(
                slug=tag_form.cleaned_data['slug'],
                defaults={'name': tag_form.cleaned_data['name']
                }
            )
            post.tags.add(tag)

            messages.success(request, "Пост опубликован")
            return redirect(post)

    context = {
        "post_form": post_form,
        "tag_form": tag_form,
    }

    return render(request, "blog/create_post.html", context)
