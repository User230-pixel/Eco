from django.urls import path
from .views import (views, posts, add_posts, search_, comments, profiles_and_cabinet,)

app_name = "blog"

urlpatterns = [
    path("", views.index, name="dashboard"),

    path("posts/", posts.post_list, name="post_list"),
    path("posts/create/", add_posts.post_create, name="add_post"),
    path("posts/my_posts/", profiles_and_cabinet.my_posts, name="my_posts"),
    path("posts/<str:slug>/" , posts.post_detail, name="detail"),

    path("categories/", posts.category_list, name="category_list"),
    path("category/<str:slug>/" , posts.category_detail, name="category_detail"),

    path("tags/", posts.tag_list, name="tag_list"),
    path("tags/<str:slug>/", posts.tag_detail, name="tag_detail"),

    path("search/htmx/", search_.global_search_htmx, name="global_search_htmx"),
    path("search/", search_.search_results, name="search_results"),

    path("posts/<str:slug>/comment/", comments.add_comment, name="comment_create"),
    path('comments/<int:comment_id>/delete/', comments.delete_comment, name='comment_delete'),
    path('comments/<int:comment_id>/like/', comments.comment_like_toggle, name='comment_like_toggle'),

    path("cabinet/", profiles_and_cabinet.cabinet, name="cabinet"),
    path("cabinet/edit/", profiles_and_cabinet.cabinet_edit, name="cabinet_edit"),
    path("profiles/<int:pk>/", profiles_and_cabinet.profile, name="profile"),
]
