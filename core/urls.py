from django.urls import path

from .forms import StyledAuthenticationForm
from .views import (
    AdminLogoutView,
    AdminLoginView,
    RoleLoginView,
    RoleLogoutView,
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
    admin_panel_view,
    admin_user_create_view,
    admin_user_edit_view,
    admin_user_list_view,
    signup_view,
    upload_chunk_view,
    user_dashboard_view,
    user_settings_view,
)

urlpatterns = [
    path(
        'login/',
        RoleLoginView.as_view(template_name='registration/login.html', authentication_form=StyledAuthenticationForm),
        name='login',
    ),
    path(
        'panel-admin/login/',
        AdminLoginView.as_view(template_name='registration/login.html', authentication_form=StyledAuthenticationForm),
        name='admin_login',
    ),
    path('logout/', RoleLogoutView.as_view(), name='logout'),
    path('panel-admin/logout/', AdminLogoutView.as_view(), name='admin_logout'),
    path('upload-chunk/', upload_chunk_view, name='upload_chunk'),
    path('registro/', signup_view, name='signup'),
    path('dashboard/', user_dashboard_view, name='user_dashboard'),
    path('ajustes/', user_settings_view, name='user_settings'),

    path('panel-admin/', admin_panel_view, name='admin_panel'),
    path('panel-admin/peliculas/', admin_movie_list_view, name='admin_movies'),
    path('panel-admin/peliculas/nuevo/', admin_movie_create_view, name='admin_movie_create'),
    path('panel-admin/peliculas/carga-rapida/', admin_movie_bulk_create_view, name='admin_movie_bulk_create'),
    path('panel-admin/peliculas/<int:pk>/editar/', admin_movie_edit_view, name='admin_movie_edit'),
    path('panel-admin/peliculas/<int:pk>/archivos/', admin_movie_media_view, name='admin_movie_media'),
    path('panel-admin/peliculas/<int:pk>/eliminar/', admin_movie_delete_view, name='admin_movie_delete'),

    path('panel-admin/generos/', admin_genre_list_view, name='admin_genres'),
    path('panel-admin/generos/nuevo/', admin_genre_create_view, name='admin_genre_create'),
    path('panel-admin/generos/<int:pk>/editar/', admin_genre_edit_view, name='admin_genre_edit'),
    path('panel-admin/generos/<int:pk>/eliminar/', admin_genre_delete_view, name='admin_genre_delete'),

    path('panel-admin/usuarios/', admin_user_list_view, name='admin_users'),
    path('panel-admin/usuarios/nuevo/', admin_user_create_view, name='admin_user_create'),
    path('panel-admin/usuarios/<int:pk>/editar/', admin_user_edit_view, name='admin_user_edit'),
]
