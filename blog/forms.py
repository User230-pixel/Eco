from django import forms
from .models import Post, Category, Tag, Comment
from main.img_validator import clean_any_image
from django import forms
from django.contrib.auth import get_user_model
from main.models import Profile

User = get_user_model()

class PostForm(forms.ModelForm):
    main_category = forms.ModelChoiceField(
        queryset=Category.objects.filter(available=True),
        label="Категория",
        empty_label="Выберите категорию",
        required=True,
    )

    class Meta:
        model = Post
        fields = ['title', 'text', 'slug', 'image', 'main_category', 'tags', 'is_published']

    def clean(self):
        cleaned = super().clean()
        main_category = cleaned.get('main_category')
        if main_category:
            cleaned['category'] = main_category   # ← перенос в clean
        return cleaned
    
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image
        return clean_any_image(image, max_size_mb=5.0)

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name', 'slug']

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text', 'parent']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Написать комментарий...',
                'class': 'w-full px-4 py-2.5 border border-gray-300 dark:border-edge bg-transparent text-sm text-gray-900 dark:text-white focus:outline-none focus:border-black dark:focus:border-volt resize-none',
            }),
            'parent': forms.HiddenInput(),
        }
        labels = {
            'text': '',
            'parent': '',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].required = False

class AccountForm(forms.ModelForm):
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': 'Расскажите о себе...',
            'class': 'w-full px-4 py-2.5 border border-gray-300 dark:border-edge bg-transparent text-sm text-gray-900 dark:text-white focus:outline-none focus:border-black dark:focus:border-volt resize-none',
        }),
        label='О себе',
    )

    class Meta:
        model = User
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.fields['bio'].initial = profile.bio

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.bio = self.cleaned_data.get('bio', '')
            profile.save()
        return user