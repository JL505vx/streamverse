from django.conf import settings
from django.db import models
from django.utils.text import slugify

from core.local_media import local_media_exists, resolve_local_media_path


class Genre(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Movie(models.Model):
    class ContentType(models.TextChoices):
        MOVIE = 'movie', 'Pelicula'
        SERIES = 'series', 'Serie'

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    content_type = models.CharField(max_length=10, choices=ContentType.choices, default=ContentType.MOVIE)
    genre = models.ForeignKey(Genre, on_delete=models.PROTECT, related_name='movies')
    synopsis = models.TextField(blank=True)
    release_year = models.PositiveIntegerField()
    cover_url = models.URLField(blank=True)
    video_url = models.CharField(max_length=200, blank=True, help_text='URL publica o ruta local publicada del video')
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or 'pelicula'
            slug = base_slug
            count = 2
            while Movie.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{count}'
                count += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def has_cover(self):
        return bool(self.cover_url)

    @property
    def has_video(self):
        return bool(self.video_url)

    @property
    def video_is_local(self):
        return bool(resolve_local_media_path(self.video_url))

    @property
    def local_video_path(self):
        file_path = resolve_local_media_path(self.video_url)
        return str(file_path) if file_path else ''

    @property
    def video_file_exists(self):
        if not self.video_url:
            return False
        if self.video_is_local:
            return local_media_exists(self.video_url)
        return True

    @property
    def video_storage_label(self):
        if not self.video_url:
            return 'Sin video'
        if self.video_is_local:
            return 'Archivo local' if self.video_file_exists else 'Archivo local faltante'
        return 'URL externa'


class WatchSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_sessions')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='watch_sessions')
    device_type = models.CharField(max_length=20)
    browser = models.CharField(max_length=30)
    operating_system = models.CharField(max_length=30)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    views_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_seen']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'movie', 'device_type', 'browser', 'operating_system'],
                name='unique_watch_session_per_device_movie',
            )
        ]

    def __str__(self):
        return f'{self.user} - {self.movie} ({self.device_type})'


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_user_favorite_movie')
        ]

    def __str__(self):
        return f'{self.user} likes {self.movie}'


class PlaybackProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='playback_progress')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='playback_progress')
    progress_seconds = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    last_watched = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_watched']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_user_playback_progress')
        ]

    def __str__(self):
        return f'{self.user} - {self.movie} ({self.progress_seconds}s)'

