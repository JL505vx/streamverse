from urllib.parse import urlparse


ADMIN_PATH_PREFIXES = ('/admin', '/cuenta/panel-admin', '/cuenta/upload-chunk')


def is_admin_path(path: str) -> bool:
    normalized = (path or '').strip()
    return any(normalized.startswith(prefix) for prefix in ADMIN_PATH_PREFIXES)


def resolve_auth_scope(request) -> str:
    for source in (getattr(request, 'POST', None), getattr(request, 'GET', None)):
        if not source:
            continue
        scope = source.get('auth_scope')
        if scope in {'admin', 'user'}:
            return scope

    path = getattr(request, 'path_info', '') or getattr(request, 'path', '')
    if is_admin_path(path):
        return 'admin'

    next_url = ''
    if hasattr(request, 'POST'):
        next_url = request.POST.get('next', '') or next_url
    if not next_url and hasattr(request, 'GET'):
        next_url = request.GET.get('next', '') or next_url
    next_path = urlparse(next_url).path or next_url
    if is_admin_path(next_path):
        return 'admin'

    referer = request.META.get('HTTP_REFERER', '')
    referer_path = urlparse(referer).path
    if is_admin_path(referer_path):
        return 'admin'

    return 'user'
