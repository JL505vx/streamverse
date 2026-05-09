from .settings import *  # noqa: F403


APP_ROLE = 'client'
ROOT_URLCONF = 'config.urls_client'
SESSION_COOKIE_NAME = USER_SESSION_COOKIE_NAME  # noqa: F405
CSRF_COOKIE_NAME = USER_CSRF_COOKIE_NAME  # noqa: F405
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'user_dashboard'
LOGOUT_REDIRECT_URL = 'home'

CLIENT_BASE_URL = os.getenv('CLIENT_BASE_URL', 'https://app.projectgp.online').strip().rstrip('/')  # noqa: F405
ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'https://admin.projectgp.online').strip().rstrip('/')  # noqa: F405

for host in ('app.projectgp.online',):
    if host not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(host)  # noqa: F405

for origin in (CLIENT_BASE_URL,):
    if origin and origin not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
        CSRF_TRUSTED_ORIGINS.append(origin)  # noqa: F405
