import magic
from PIL import Image
from django.core.exceptions import ValidationError


def clean_any_image(image_file, max_size_mb=5.0):
    if not image_file:
        return image_file
        

    if image_file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Файл слишком тяжелый. Максимум {max_size_mb} МБ.")
        
    image_file.seek(0)
    file_mime = magic.from_buffer(image_file.read(2048), mime=True)
    image_file.seek(0)
    
    if file_mime not in ['image/jpeg', 'image/png', 'image/webp']:
        raise ValidationError("Файл не является изображением (разрешены только JPG, PNG, WEBP).")
        
    try:
        with Image.open(image_file) as img:
            img.verify()
        image_file.seek(0)
    except Exception:
        raise ValidationError("Файл поврежден или содержит вредоносный код.")
        
    return image_file