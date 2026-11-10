import random
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from blog.models import Post, Category, Tag

User = get_user_model()

# ===== 1. Автор =====
author = User.objects.filter(is_superuser=True).first() or User.objects.first()
if not author:
    author = User.objects.create_user('author', password='12345')
    print(f'Создан автор: {author.username}')
else:
    print(f'Автор: {author.username}')

# ===== 2. Категории =====
categories_data = [
    ('Django', 'django'),
    ('Python', 'python'),
    ('JavaScript', 'javascript'),
    ('Базы данных', 'databases'),
    ('DevOps', 'devops'),
    ('Frontend', 'frontend'),
]
categories = []
for name, slug in categories_data:
    cat, created = Category.objects.get_or_create(slug=slug, defaults={'name': name, 'available': True})
    categories.append(cat)
    print(f'Категория: {cat.name} ({"создана" if created else "уже была"})')

# ===== 3. Теги =====
tags_data = [
    ('туториал', 'tutorial'),
    ('для новичков', 'beginners'),
    ('оптимизация', 'optimization'),
    ('безопасность', 'security'),
    ('ORM', 'orm'),
    ('асинхронность', 'async'),
    ('тестирование', 'testing'),
    ('деплой', 'deploy'),
]
tags = []
for name, slug in tags_data:
    tag, created = Tag.objects.get_or_create(slug=slug, defaults={'name': name})
    tags.append(tag)
    print(f'Тег: {tag.name} ({"создан" if created else "уже был"})')

# ===== 4. Данные для постов =====
titles = [
    'Как установить Django и создать первый проект',
    'Разбираемся с models.py: поля и связи',
    'QuerySet API: filter, exclude, get',
    'Что такое select_related и prefetch_related',
    'Транзакции и race conditions в Django',
    'Как работает atomic() и select_for_update',
    'Формы в Django: ModelForm от А до Я',
    'CBV vs FBV: что выбрать',
    'Шаблоны Django: теги и фильтры',
    'Аутентификация и права доступа',
    'Оптимизация запросов: N+1 проблема',
    'Миграции: как читать и откатывать',
    'Кастомные template tags',
    'Middleware: что это и зачем',
    'Сигналы Django: post_save и другие',
    'Как тестировать Django-проект',
    'Деплой на VPS: gunicorn + nginx',
    'Docker для Django: с чего начать',
    'PostgreSQL vs SQLite: что выбрать',
    'Redis и кэширование в Django',
    'Celery: фоновые задачи',
    'DRF: первые шаги с API',
    'JWT-аутентификация в DRF',
    'GraphQL vs REST',
    'HTMX: современный подход без JS',
    'Tailwind CSS в Django-проекте',
    'Как работает CSRF-защита',
    'XSS и санитизация HTML',
    'SQL-инъекции: как от них защититься',
    'Логирование в Django',
    'Настройка email через SMTP',
    'YooKassa: приём платежей',
    'Вебхуки: как обрабатывать',
    'Идемпотентность в платёжных системах',
    'Корзина в интернет-магазине',
    'Каталог товаров с фильтрами',
    'Пагинация: Paginator в Django',
    'Поиск по сайту через Q-объекты',
    'Кэширование страниц',
    'Оптимизация изображений',
    'Sitemap и RSS для SEO',
    'Структура проекта: apps vs one-file',
    'Settings: как разделить dev и prod',
    'Environment variables и python-dotenv',
    'Git workflow для одного разработчика',
    'Code review: что смотреть',
    'Рефакторинг: с чего начать',
    'Как читать чужой код',
    'Ошибки новичков в Django',
    'Что учить после Django',
]

bodies = [
    'Разбираем по шагам, с примерами кода и типичными ошибками. Статья для тех, кто хочет понять не только «как», но и «почему».',
    'В этой статье мы рассмотрим практические примеры использования и подводные камни, с которыми сталкиваются разработчики.',
    'Подробный гайд с примерами кода. Разберём как правильно делать и каких ошибок избегать.',
    'Краткая шпаргалка по теме — что запомнить, что использовать в работе, а что устарело.',
    'Глубокое погружение в тему с реальными кейсами из практики. Покажем, как это работает под капотом.',
]

# ===== 5. Генерация 50 постов =====
created_count = 0
skipped = 0

for i, title in enumerate(titles, start=1):
    slug = f'post-{i}-{title.lower().replace(" ", "-")[:40]}'
    slug = slug.replace(':', '').replace(',', '').replace('.', '').replace('(', '').replace(')', '')

    if Post.objects.filter(slug=slug).exists():
        skipped += 1
        continue

    # случайная дата за последние 60 дней
    days_ago = random.randint(0, 60)
    post = Post.objects.create(
        title=title,
        text=random.choice(bodies) + f'\n\nПост #{i}. ' + 'Текст для заполнения. ' * random.randint(5, 15),
        slug=slug,
        author=author,
        category=random.choice(categories),
        is_published=random.choice([True, True, True, False]),  # 75% опубликованных
    )

    # проставляем created_at вручную (auto_now_add игнорирует)
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(days=days_ago))

    # случайные теги (1-3)
    post.tags.set(random.sample(tags, k=random.randint(1, 3)))
    created_count += 1

print(f'\n✅ Создано постов: {created_count}')
print(f'⏭  Пропущено (уже были): {skipped}')
print(f'📊 Всего постов в БД: {Post.objects.count()}')
print(f'📊 Опубликованных: {Post.objects.filter(is_published=True).count()}')