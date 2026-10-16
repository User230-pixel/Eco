from ..models import Notification

def unread_notifications_processor(request):
    """
    Globally injects the unread notifications count into all templates.
    """
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    count = request.user.notifications.filter(is_read=False).count()
    
    return {'unread_notifications_count': count}
