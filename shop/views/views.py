from ..models import (
    Category,
)

from django.core.cache import cache

def get_cached_categories():
    """Возвращает категории из кеша или БД"""
    categories = cache.get('all_categories')
    if not categories:
        categories = Category.objects.filter(available=True)
        cache.set('all_categories', categories, 3600)
    return categories
