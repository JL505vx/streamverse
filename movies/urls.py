from django.urls import path

from .views import home_view, movie_detail_view, toggle_favorite_view, update_progress_view

urlpatterns = [
    path('', home_view, name='home'),
    path('pelicula/<slug:slug>/', movie_detail_view, name='movie_detail'),
    path('pelicula/<slug:slug>/favorito/', toggle_favorite_view, name='toggle_favorite'),
    path('pelicula/<slug:slug>/progreso/', update_progress_view, name='update_progress'),
]
