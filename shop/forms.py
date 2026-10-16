from django import forms
from .models import Product, Category
from main.img_validator import clean_any_image

class ProductForm(forms.ModelForm):
    main_category = forms.ModelChoiceField(
        queryset = Category.objects.all(),
        label="Категория",
        empty_label="Выберите категорию",
        required=True
    )

    class Meta:
        model = Product
        fields = ['main_category', 'category2nd', 'name', 'description', 'price', 'image', 'stock']

    def clean_image(self):
        image = self.cleaned_data.get('image')
        return clean_any_image(image, max_size_mb=5.0)