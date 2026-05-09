from django.urls import path

from .forms import StyledAuthenticationForm
from .views import (
    RoleLoginView,
    RoleLogoutView,
    signup_view,
    user_custom_list_add_view,
    user_custom_list_create_view,
    user_custom_list_remove_item_view,
    user_dashboard_view,
    user_notifications_read_view,
    user_parental_unlock_view,
    user_rate_movie_view,
    user_settings_view,
    user_suggestion_create_view,
    user_suggestion_reply_view,
)


urlpatterns = [
    path(
        'login/',
        RoleLoginView.as_view(template_name='registration/login.html', authentication_form=StyledAuthenticationForm),
        name='login',
    ),
    path('logout/', RoleLogoutView.as_view(), name='logout'),
    path('registro/', signup_view, name='signup'),
    path('dashboard/', user_dashboard_view, name='user_dashboard'),
    path('ajustes/', user_settings_view, name='user_settings'),
    path('dashboard/sugerencias/nueva/', user_suggestion_create_view, name='user_suggestion_create'),
    path('dashboard/sugerencias/<int:suggestion_id>/responder/', user_suggestion_reply_view, name='user_suggestion_reply'),
    path('dashboard/listas/nueva/', user_custom_list_create_view, name='user_custom_list_create'),
    path('dashboard/listas/agregar/', user_custom_list_add_view, name='user_custom_list_add'),
    path('dashboard/listas/items/<int:item_id>/quitar/', user_custom_list_remove_item_view, name='user_custom_list_remove_item'),
    path('dashboard/calificar/', user_rate_movie_view, name='user_rate_movie'),
    path('dashboard/notificaciones/leer/', user_notifications_read_view, name='user_notifications_read'),
    path('ajustes/parental/desbloquear/', user_parental_unlock_view, name='user_parental_unlock'),
]
