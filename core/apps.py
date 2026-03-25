from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.middleware.csrf import CsrfViewMiddleware

        from .middleware import DualCsrfCookieMiddleware, DualSessionCookieMiddleware

        SessionMiddleware.get_cookie_name = DualSessionCookieMiddleware.get_cookie_name
        SessionMiddleware.process_request = DualSessionCookieMiddleware.process_request
        SessionMiddleware.process_response = DualSessionCookieMiddleware.process_response

        CsrfViewMiddleware.get_cookie_name = DualCsrfCookieMiddleware.get_cookie_name
        CsrfViewMiddleware._get_secret = DualCsrfCookieMiddleware._get_secret
        CsrfViewMiddleware._set_csrf_cookie = DualCsrfCookieMiddleware._set_csrf_cookie
