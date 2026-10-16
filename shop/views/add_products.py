from django.shortcuts import render, redirect
from pytils.translit import slugify
from ..forms import ProductForm
from main.views.views import shopper_required
from ..models import Categories_from_Category_2nd

@shopper_required
def create_product_get(request):
    form = ProductForm()
    return render(request, 'shop/create_product.html', {'form': form})

@shopper_required
def create_product_post(request):
    form = ProductForm(request.POST, request.FILES or None)
    
    if form.is_valid():
        product = form.save(commit=False)
        product.user = request.user
        product.slug = slugify(form.cleaned_data['name'])
        product.save()
        return redirect('shop:product_list')
        
    return render(request, 'shop/create_product.html', {'form': form})

def load_subcategories_htmx(request):
    main_category_id = request.GET.get('main_category')
    
    if main_category_id:
        subcategories = Categories_from_Category_2nd.objects.filter(category_id=main_category_id).order_by('name')
    else:
        subcategories = Categories_from_Category_2nd.objects.none()
        
    return render(request, 'shop/partials/subcategory_options.html', {'subcategories': subcategories})
