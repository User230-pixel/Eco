from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0007_favoriteproducts"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="stock_reserved",
            field=models.BooleanField(default=False),
        ),
    ]
