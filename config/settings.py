from pathlib import Path
import os
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(env_path, override=True)
DB_DEBUG = os.getenv('DB_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
if DB_DEBUG:
    print(f'[DB DEBUG] dotenv path: {env_path}')
    print(f'[DB DEBUG] dotenv exists: {env_path.exists()}')

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
DEBUG = os.getenv('DEBUG', '1').strip().lower() in ('1', 'true', 'yes', 'on')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost').split(',')

INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'movies',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

MODE = os.getenv('DJANGO_MODE', os.getenv('APP_ROLE', 'monolith')).strip().lower() or 'monolith'
if MODE not in {'admin', 'client', 'monolith'}:
    MODE = 'monolith'

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.deployment_links',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


database_url = os.getenv('DATABASE_URL', '').strip()
if not database_url:
    raise ImproperlyConfigured('DATABASE_URL es obligatoria. Configura tu conexion PostgreSQL en .env.')

parsed_db_url = urlparse(database_url)
if parsed_db_url.hostname and parsed_db_url.hostname.endswith('supabase.com') and 'sslmode=' not in database_url:
    separator = '&' if '?' in database_url else '?'
    database_url = f'{database_url}{separator}sslmode=require'

DATABASES = {
    'default': dj_database_url.parse(database_url, conn_max_age=600)
}
if DB_DEBUG:
    print(f'[DB DEBUG] DATABASE_URL: {database_url}')
    print(f"[DB DEBUG] active engine: {DATABASES['default']['ENGINE']}")
    print(f"[DB DEBUG] active host: {DATABASES['default'].get('HOST')}")
    print(f"[DB DEBUG] active name: {DATABASES['default'].get('NAME')}")

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = (os.getenv('MEDIA_URL', '/media/').strip() or '/media/')
if not MEDIA_URL.startswith('/'):
    MEDIA_URL = f'/{MEDIA_URL}'
if not MEDIA_URL.endswith('/'):
    MEDIA_URL = f'{MEDIA_URL}/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media'))).expanduser()

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

APP_LOG_LEVEL = os.getenv('APP_LOG_LEVEL', 'INFO').strip().upper() or 'INFO'
REDIS_URL = os.getenv('REDIS_URL', '').strip()

if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

WATCH_PARTY_MEMBER_STALE_SECONDS = int(os.getenv('WATCH_PARTY_MEMBER_STALE_SECONDS', '120') or 120)
WATCH_PARTY_MESSAGE_HISTORY_LIMIT = int(os.getenv('WATCH_PARTY_MESSAGE_HISTORY_LIMIT', '24') or 24)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'core': {
            'handlers': ['console'],
            'level': APP_LOG_LEVEL,
            'propagate': False,
        },
        'movies': {
            'handlers': ['console'],
            'level': APP_LOG_LEVEL,
            'propagate': False,
        },
    },
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'user_dashboard'
LOGOUT_REDIRECT_URL = 'home'
CSRF_FAILURE_VIEW = 'core.views.csrf_failure_view'

APP_ROLE = MODE
ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', '').strip().rstrip('/')
CLIENT_BASE_URL = os.getenv('CLIENT_BASE_URL', '').strip().rstrip('/')

USER_SESSION_COOKIE_NAME = 'user_sessionid'
ADMIN_SESSION_COOKIE_NAME = 'admin_sessionid'

USER_CSRF_COOKIE_NAME = 'user_csrftoken'
ADMIN_CSRF_COOKIE_NAME = 'admin_csrftoken'
if MODE == 'admin':
    SESSION_COOKIE_NAME = ADMIN_SESSION_COOKIE_NAME
    CSRF_COOKIE_NAME = ADMIN_CSRF_COOKIE_NAME
    LOGIN_URL = 'admin_login'
    LOGIN_REDIRECT_URL = 'admin_panel'
    LOGOUT_REDIRECT_URL = 'admin_login'
    ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'https://admin.projectgp.online').strip().rstrip('/')
    CLIENT_BASE_URL = os.getenv('CLIENT_BASE_URL', 'https://app.projectgp.online').strip().rstrip('/')
else:
    SESSION_COOKIE_NAME = USER_SESSION_COOKIE_NAME
    CSRF_COOKIE_NAME = USER_CSRF_COOKIE_NAME
    if MODE == 'client':
        CLIENT_BASE_URL = os.getenv('CLIENT_BASE_URL', 'https://app.projectgp.online').strip().rstrip('/')
        ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'https://admin.projectgp.online').strip().rstrip('/')
