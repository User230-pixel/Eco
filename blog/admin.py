from django.contrib import admin
from .models import Post, Category

from django.contrib import admin
from .models import Category, Post, Tag, Comment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'available')
    list_filter = ('available',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('available',)
    ordering = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'is_published', 'created_at')
    list_filter = ('is_published', 'author', 'category')
    search_fields = ('title', 'text')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('author', 'category')
    date_hierarchy = 'created_at'
    raw_id_fields = ('author',)
    filter_horizontal = ('tags',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('short_text', 'user', 'post', 'parent', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('text', 'user__username', 'post__title')
    readonly_fields = ('created_at',)
    list_select_related = ('user', 'post', 'parent')
    date_hierarchy = 'created_at'
    list_per_page = 30
    raw_id_fields = ('post', 'user', 'parent')

    @admin.display(description='Текст')
    def short_text(self, obj):
        return obj.text[:60] + ('…' if len(obj.text) > 60 else '')