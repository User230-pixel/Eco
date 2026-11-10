from django.db import models
from django.urls import reverse
from django.conf import settings

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("blog:tag_detail", kwargs={"slug": self.slug})
    
    

class Category(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    available = models.BooleanField(default=True)
    image = models.ImageField(
        'Изображение', upload_to="categories/", blank=True
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("blog:category_detail", kwargs={'slug': self.slug})

class Post(models.Model):
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts', verbose_name='Теги')
    title = models.CharField(max_length=255, default="Обход проверки...", verbose_name="Заголовок Поста")
    text = models.TextField(default="Каким-то образом обошли проверку... Стоит проверить кусок кода", verbose_name="Текст Поста")
    slug = models.SlugField(unique=True, verbose_name="URL")
    image = models.ImageField(upload_to="posts/", blank=True, verbose_name="Изображение")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts', verbose_name='Категория',)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="posts", verbose_name="Автор")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_published = models.BooleanField(default=True, verbose_name="Опубликован: Да/Нет")

    class Meta:
        verbose_name = "Пост"
        verbose_name_plural = "Посты"

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('blog:detail', kwargs={'slug': self.slug})

class Comment(models.Model):
    post = models.ForeignKey(
        "Post",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Пост",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_comments",
        verbose_name="Пользователь",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="Ответ на",
    )
    text = models.TextField(verbose_name="Текст", default="")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата публикации")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        indexes = [
            models.Index(fields=["post", "-created_at"]),
        ]

    def __str__(self):
        return f"Комментарий {self.user.username} к «{self.post.title}»"

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"pk": self.pk})


class CommentLike(models.Model):
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comment_likes_given",
    )
    to_comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_comment"],
                name="unique_user_comment_like",
            ),
        ]
        verbose_name = "Лайк"
        verbose_name_plural = "Лайки"

    def __str__(self):
        return f"{self.from_user.username} → comment#{self.to_comment_id}"