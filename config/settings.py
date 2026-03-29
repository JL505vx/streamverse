from pathlib import Path
import os
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(env_path, override=True)
print(f'[DB DEBUG] dotenv path: {env_path}')
print(f'[DB DEBUG] dotenv exists: {env_path.exists()}')

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
DEBUG = os.getenv('DEBUG', '1').strip().lower() in ('1', 'true', 'yes', 'on')
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if h.strip()]
if DEBUG and '*' not in ALLOWED_HOSTS:
    # En desarrollo permitimos IPs de la red local para probar desde celular.
    ALLOWED_HOSTS.append('*')

INSTALLED_APPS = [
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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


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
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'user_dashboard'
LOGOUT_REDIRECT_URL = 'home'

USER_SESSION_COOKIE_NAME = 'user_sessionid'
ADMIN_SESSION_COOKIE_NAME = 'admin_sessionid'
SESSION_COOKIE_NAME = USER_SESSION_COOKIE_NAME

USER_CSRF_COOKIE_NAME = 'user_csrftoken'
ADMIN_CSRF_COOKIE_NAME = 'admin_csrftoken'
CSRF_COOKIE_NAME = USER_CSRF_COOKIE_NAME
