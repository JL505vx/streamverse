from django.conf import settings


def deployment_links(_request):
    return {
        'app_role': getattr(settings, 'APP_ROLE', 'monolith'),
        'admin_base_url': getattr(settings, 'ADMIN_BASE_URL', '').rstrip('/'),
        'client_base_url': getattr(settings, 'CLIENT_BASE_URL', '').rstrip('/'),
    }
