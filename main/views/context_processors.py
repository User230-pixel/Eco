from ..models import Notification

BASE_TEMPLATES = {
    'shop': 'shop/base.html',
    'blog': 'blog/base.html',
}

def base_template(request):
    app_name = 'main'

    referer = request.META.get('HTTP_REFERER', '')

    if 'shop' in referer:
        app_name = 'shop'
    elif 'blog' in referer:
        app_name = 'blog'

    if app_name == 'main':
        if 'shop' in request.path:
            app_name = 'shop'
        elif 'blog' in request.path:
            app_name = 'blog'

    return {
        'base_template': BASE_TEMPLATES.get(app_name, 'main/base.html'),
    }


def unread_notifications_processor(request):
    """
    Globally injects the unread notifications count into all templates.
    """
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    count = request.user.notifications.filter(is_read=False).count()
    
    return {'unread_notifications_count': count}
