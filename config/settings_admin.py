from .settings import *  # noqa: F403


APP_ROLE = 'admin'
ROOT_URLCONF = 'config.urls_admin'
SESSION_COOKIE_NAME = ADMIN_SESSION_COOKIE_NAME  # noqa: F405
CSRF_COOKIE_NAME = ADMIN_CSRF_COOKIE_NAME  # noqa: F405
LOGIN_URL = 'admin_login'
LOGIN_REDIRECT_URL = 'admin_panel'
LOGOUT_REDIRECT_URL = 'admin_login'

ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'https://admin.projectgp.online').strip().rstrip('/')  # noqa: F405
CLIENT_BASE_URL = os.getenv('CLIENT_BASE_URL', 'https://app.projectgp.online').strip().rstrip('/')  # noqa: F405

for host in ('admin.projectgp.online',):
    if host not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(host)  # noqa: F405

for origin in (ADMIN_BASE_URL,):
    if origin and origin not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
        CSRF_TRUSTED_ORIGINS.append(origin)  # noqa: F405
