from django.urls import path

from .views import (
    create_watch_party_view,
    home_view,
    join_watch_party_view,
    leave_watch_party_view,
    movie_detail_view,
    movie_watch_view,
    toggle_favorite_view,
    update_progress_view,
    watch_party_state_view,
    watch_party_sync_view,
)

urlpatterns = [
    path('', home_view, name='home'),
    path('pelicula/<slug:slug>/', movie_detail_view, name='movie_detail'),
    path('pelicula/<slug:slug>/ver/', movie_watch_view, name='movie_watch'),
    path('pelicula/<slug:slug>/favorito/', toggle_favorite_view, name='toggle_favorite'),
    path('pelicula/<slug:slug>/progreso/', update_progress_view, name='update_progress'),
    path('pelicula/<slug:slug>/watch-party/create/', create_watch_party_view, name='watch_party_create'),
    path('pelicula/<slug:slug>/watch-party/join/', join_watch_party_view, name='watch_party_join'),
    path('pelicula/<slug:slug>/watch-party/<str:code>/', watch_party_state_view, name='watch_party_state'),
    path('pelicula/<slug:slug>/watch-party/<str:code>/sync/', watch_party_sync_view, name='watch_party_sync'),
    path('pelicula/<slug:slug>/watch-party/<str:code>/leave/', leave_watch_party_view, name='watch_party_leave'),
]
