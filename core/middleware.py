import time
from importlib import import_module

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import (
    CSRF_TOKEN_LENGTH,
    CsrfViewMiddleware,
    InvalidTokenFormat,
    _check_token_format,
    _unmask_cipher_token,
)
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date

from .session_scopes import resolve_auth_scope


class DualSessionCookieMiddleware(SessionMiddleware):
    def __init__(self, get_response):
        super().__init__(get_response)
        engine = import_module(settings.SESSION_ENGINE)
        self.SessionStore = engine.SessionStore

    def get_cookie_name(self, request):
        scope = resolve_auth_scope(request)
        request.auth_scope = scope
        if scope == 'admin':
            return settings.ADMIN_SESSION_COOKIE_NAME
        return settings.USER_SESSION_COOKIE_NAME

    def process_request(self, request):
        cookie_name = self.get_cookie_name(request)
        request.session_cookie_name = cookie_name
        session_key = request.COOKIES.get(cookie_name)
        request.session = self.SessionStore(session_key)

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        cookie_name = getattr(request, 'session_cookie_name', settings.USER_SESSION_COOKIE_NAME)

        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            patch_vary_headers(response, ('Cookie',))
        else:
            if accessed:
                patch_vary_headers(response, ('Cookie',))
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires = http_date(time.time() + max_age)

                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the request completed."
                        )
                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
        return response


class DualCsrfCookieMiddleware(CsrfViewMiddleware):
    def get_cookie_name(self, request):
        scope = getattr(request, 'auth_scope', resolve_auth_scope(request))
        request.auth_scope = scope
        if scope == 'admin':
            return settings.ADMIN_CSRF_COOKIE_NAME
        return settings.USER_CSRF_COOKIE_NAME

    def _get_secret(self, request):
        cookie_name = self.get_cookie_name(request)
        request.csrf_cookie_name = cookie_name
        try:
            csrf_secret = request.COOKIES[cookie_name]
        except KeyError:
            csrf_secret = None
        else:
            _check_token_format(csrf_secret)
        if csrf_secret is None:
            return None
        if len(csrf_secret) == CSRF_TOKEN_LENGTH:
            csrf_secret = _unmask_cipher_token(csrf_secret)
        return csrf_secret

    def _set_csrf_cookie(self, request, response):
        cookie_name = getattr(request, 'csrf_cookie_name', self.get_cookie_name(request))
        response.set_cookie(
            cookie_name,
            request.META['CSRF_COOKIE'],
            max_age=settings.CSRF_COOKIE_AGE,
            domain=settings.CSRF_COOKIE_DOMAIN,
            path=settings.CSRF_COOKIE_PATH,
            secure=settings.CSRF_COOKIE_SECURE,
            httponly=settings.CSRF_COOKIE_HTTPONLY,
            samesite=settings.CSRF_COOKIE_SAMESITE,
        )
        patch_vary_headers(response, ('Cookie',))
