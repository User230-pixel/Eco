import os
import requests
from django.db import migrations
from django.core.files.base import ContentFile
from django.utils.text import slugify

# Данные для технологического магазина с реальными брендами, моделями и заглушками для фото
TECH_STORE_DATA = [
    {
        "category_name": "Смартфоны и гаджеты",
        "category_image": "https://unsplash.com",
        "brand_name": "Apple",
        "brand_image": "https://unsplash.com",
        "products": [
            {
                "name": "iPhone 16 Pro Max",
                "price": 145000.00,
                "stock": 12,
                "image_url": "https://unsplash.com",
                "description": "Флагманский смартфон с титановым корпусом и продвинутой камерой."
            },
            {
                "name": "Apple Watch Series 10",
                "price": 48000.00,
                "stock": 25,
                "image_url": "https://unsplash.com",
                "description": "Умные часы с обновленным дисплеем и датчиками здоровья."
            }
        ]
    },
    {
        "category_name": "Смартфоны и гаджеты",
        "category_image": "https://unsplash.com",
        "brand_name": "Samsung",
        "brand_image": "https://unsplash.com",
        "products": [
            {
                "name": "Samsung Galaxy S24 Ultra",
                "price": 120000.00,
                "stock": 8,
                "image_url": "https://unsplash.com",
                "description": "Смартфон со встроенным ИИ Galaxy AI и экраном 120 Гц."
            }
        ]
    },
    {
        "category_name": "Ноутбуки и ПК",
        "category_image": "https://unsplash.com",
        "brand_name": "ASUS",
        "brand_image": "https://unsplash.com",
        "products": [
            {
                "name": "ASUS ROG Zephyrus G16",
                "price": 195000.00,
                "stock": 5,
                "image_url": "https://unsplash.com",
                "description": "Мощный игровой ноутбук с видеокартой RTX 40-й серии."
            }
        ]
    },
    {
        "category_name": "Аудио и Звук",
        "category_image": "https://unsplash.com",
        "brand_name": "Sony",
        "brand_image": "https://unsplash.com",
        "products": [
            {
                "name": "Sony WH-1000XM5",
                "price": 35000.00,
                "stock": 15,
                "image_url": "https://unsplash.com",
                "description": "Полноразмерные беспроводные наушники с лучшим шумоподавлением."
            }
        ]
    }
]

def generate_slug(text):
    """Безопасная генерация слага с поддержкой кириллицы при наличии библиотеки"""
    try:
        from slugify import slugify as cyrillic_slugify
        return cyrillic_slugify(text)
    except ImportError:
        return slugify(text)

def download_and_save_image(instance, field_name, url, filename_prefix):
    
    return

def populate_data(apps, schema_editor):
    # Получаем модели через исторический контекст Django приложений
    Category = apps.get_model('shop', 'Category')
    Categories_from_Category_2nd = apps.get_model('shop', 'Categories_from_Category_2nd')
    Product = apps.get_model('shop', 'Product')

    for item in TECH_STORE_DATA:
        cat_name = item["category_name"]
        cat_slug = generate_slug(cat_name)

        # 1. Создаем/получаем главную категорию
        category, created = Category.objects.get_or_create(
            slug=cat_slug,
            defaults={"name": cat_name, "available": True}
        )
        if created and item.get("category_image"):
            download_and_save_image(category, "image", item["category_image"], cat_slug)

        # 2. Создаем/получаем подкатегорию (Бренд)
        brand_name = item["brand_name"]
        sub_slug = generate_slug(f"{cat_name}-{brand_name}")
        
        subcategory, created = Categories_from_Category_2nd.objects.get_or_create(
            slug=sub_slug,
            defaults={
                "category": category,
                "brand": brand_name,
                "available": True
            }
        )
        if created and item.get("brand_image"):
            download_and_save_image(subcategory, "image", item["brand_image"], sub_slug)

        # 3. Добавляем товары
        for prod_data in item["products"]:
            prod_slug = generate_slug(prod_data["name"])

            product, created = Product.objects.get_or_create(
                slug=prod_slug,
                defaults={
                    "category2nd": subcategory,
                    "name": prod_data["name"],
                    "price": prod_data["price"],
                    "stock": prod_data["stock"],
                    "description": prod_data["description"],
                    "available": True
                }
            )
            if created and prod_data.get("image_url"):
                download_and_save_image(product, "image", prod_data["image_url"], prod_slug)

def unload_data(apps, schema_editor):
    """Откат миграции (удаляет созданные данные)"""
    Category = apps.get_model('shop', 'Category')
    Category.objects.filter(slug__in=[generate_slug(item["category_name"]) for item in TECH_STORE_DATA]).delete()

class Migration(migrations.Migration):

    dependencies = [
        # Убедитесь, что здесь указана последняя миграция вашего приложения shop
        ('shop', '0001_initial'), 
    ]

    operations = [
        migrations.RunPython(populate_data, unload_data),
    ]
