from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView

from .forms import StyledAuthenticationForm
from .views import (
    AdminLogoutView,
    AdminLoginView,
    admin_genre_create_view,
    admin_genre_delete_view,
    admin_genre_edit_view,
    admin_genre_list_view,
    admin_movie_bulk_create_view,
    admin_movie_create_view,
    admin_movie_delete_view,
    admin_movie_edit_view,
    admin_movie_list_view,
    admin_movie_media_view,
    admin_movie_processing_detail_view,
    admin_panel_view,
    admin_suggestion_status_view,
    admin_user_create_view,
    admin_user_edit_view,
    admin_user_list_view,
    upload_chunk_view,
)


def _client_url(path=''):
    base_url = getattr(settings, 'CLIENT_BASE_URL', '').rstrip('/') or '/'
    if base_url == '/':
        return '/'
    return f'{base_url}/{path.lstrip("/")}'


urlpatterns = [
    path('', admin_panel_view, name='admin_panel'),
    path('login/', AdminLoginView.as_view(template_name='registration/login.html', authentication_form=StyledAuthenticationForm), name='admin_login'),
    path('logout/', AdminLogoutView.as_view(), name='admin_logout'),
    path('upload-chunk/', upload_chunk_view, name='upload_chunk'),
    path('sugerencias/<int:suggestion_id>/estado/', admin_suggestion_status_view, name='admin_suggestion_status'),
    path('peliculas/', admin_movie_list_view, name='admin_movies'),
    path('peliculas/nuevo/', admin_movie_create_view, name='admin_movie_create'),
    path('peliculas/carga-rapida/', admin_movie_bulk_create_view, name='admin_movie_bulk_create'),
    path('peliculas/<int:pk>/editar/', admin_movie_edit_view, name='admin_movie_edit'),
    path('peliculas/<int:pk>/archivos/', admin_movie_media_view, name='admin_movie_media'),
    path('peliculas/<int:pk>/procesamiento/', admin_movie_processing_detail_view, name='admin_movie_processing_detail'),
    path('peliculas/<int:pk>/eliminar/', admin_movie_delete_view, name='admin_movie_delete'),
    path('generos/', admin_genre_list_view, name='admin_genres'),
    path('generos/nuevo/', admin_genre_create_view, name='admin_genre_create'),
    path('generos/<int:pk>/editar/', admin_genre_edit_view, name='admin_genre_edit'),
    path('generos/<int:pk>/eliminar/', admin_genre_delete_view, name='admin_genre_delete'),
    path('usuarios/', admin_user_list_view, name='admin_users'),
    path('usuarios/nuevo/', admin_user_create_view, name='admin_user_create'),
    path('usuarios/<int:pk>/editar/', admin_user_edit_view, name='admin_user_edit'),
    path('cliente/', RedirectView.as_view(url=_client_url(), permanent=False), name='home'),
    path('cliente/login/', RedirectView.as_view(url=_client_url('cuenta/login/'), permanent=False), name='login'),

    # Compatibilidad temporal con URLs del monolito anterior.
    path('cuenta/logout/', AdminLogoutView.as_view(), name='legacy_admin_logout'),
    path('cuenta/panel-admin/logout/', AdminLogoutView.as_view(), name='legacy_panel_admin_logout'),
    path('cuenta/panel-admin/login/', AdminLoginView.as_view(template_name='registration/login.html', authentication_form=StyledAuthenticationForm), name='legacy_admin_login'),
    path('cuenta/upload-chunk/', upload_chunk_view, name='legacy_upload_chunk'),
    path('cuenta/panel-admin/', admin_panel_view, name='legacy_admin_panel'),
    path('cuenta/panel-admin/sugerencias/<int:suggestion_id>/estado/', admin_suggestion_status_view, name='legacy_admin_suggestion_status'),
    path('cuenta/panel-admin/peliculas/', admin_movie_list_view, name='legacy_admin_movies'),
    path('cuenta/panel-admin/peliculas/nuevo/', admin_movie_create_view, name='legacy_admin_movie_create'),
    path('cuenta/panel-admin/peliculas/carga-rapida/', admin_movie_bulk_create_view, name='legacy_admin_movie_bulk_create'),
    path('cuenta/panel-admin/peliculas/<int:pk>/editar/', admin_movie_edit_view, name='legacy_admin_movie_edit'),
    path('cuenta/panel-admin/peliculas/<int:pk>/archivos/', admin_movie_media_view, name='legacy_admin_movie_media'),
    path('cuenta/panel-admin/peliculas/<int:pk>/procesamiento/', admin_movie_processing_detail_view, name='legacy_admin_movie_processing_detail'),
    path('cuenta/panel-admin/peliculas/<int:pk>/eliminar/', admin_movie_delete_view, name='legacy_admin_movie_delete'),
    path('cuenta/panel-admin/generos/', admin_genre_list_view, name='legacy_admin_genres'),
    path('cuenta/panel-admin/generos/nuevo/', admin_genre_create_view, name='legacy_admin_genre_create'),
    path('cuenta/panel-admin/generos/<int:pk>/editar/', admin_genre_edit_view, name='legacy_admin_genre_edit'),
    path('cuenta/panel-admin/generos/<int:pk>/eliminar/', admin_genre_delete_view, name='legacy_admin_genre_delete'),
    path('cuenta/panel-admin/usuarios/', admin_user_list_view, name='legacy_admin_users'),
    path('cuenta/panel-admin/usuarios/nuevo/', admin_user_create_view, name='legacy_admin_user_create'),
    path('cuenta/panel-admin/usuarios/<int:pk>/editar/', admin_user_edit_view, name='legacy_admin_user_edit'),
]
