from django.contrib import admin

from .models import Favorite, Genre, Movie, PlaybackProgress, WatchSession


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'genre', 'release_year', 'is_published')
    list_filter = ('genre', 'is_published', 'release_year')
    search_fields = ('title', 'synopsis')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(WatchSession)
class WatchSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'device_type', 'browser', 'operating_system', 'views_count', 'last_seen')
    list_filter = ('device_type', 'browser', 'operating_system')
    search_fields = ('user__username', 'movie__title', 'ip_address')


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'created_at')
    search_fields = ('user__username', 'movie__title')


@admin.register(PlaybackProgress)
class PlaybackProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'movie', 'progress_seconds', 'duration_seconds', 'completed', 'last_watched')
    list_filter = ('completed',)
    search_fields = ('user__username', 'movie__title')
