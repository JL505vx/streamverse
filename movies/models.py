import secrets

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from core.local_media import local_media_exists, resolve_local_media_path


WATCH_PARTY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _generate_watch_party_code():
    return ''.join(secrets.choice(WATCH_PARTY_ALPHABET) for _ in range(6))


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

    class ProcessingStatus(models.TextChoices):
        UPLOADING = 'subiendo', 'Subiendo'
        PROCESSING = 'procesando', 'Procesando'
        READY = 'listo', 'Listo'
        ERROR = 'error', 'Error'

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    content_type = models.CharField(max_length=10, choices=ContentType.choices, default=ContentType.MOVIE)
    genre = models.ForeignKey(Genre, on_delete=models.PROTECT, related_name='movies')
    synopsis = models.TextField(blank=True)
    release_year = models.PositiveIntegerField()
    cover_url = models.URLField(blank=True)
    video_url = models.CharField(max_length=200, blank=True, help_text='URL publica o ruta local publicada del video')
    video_upload_filename = models.CharField(max_length=255, blank=True)
    video_upload_size_bytes = models.PositiveBigIntegerField(default=0)
    video_upload_duration_ms = models.PositiveIntegerField(default=0)
    video_uploaded_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.UPLOADING)
    processing_step = models.CharField(max_length=50, blank=True, null=True)
    processing_stage = models.CharField(max_length=100, default='pendiente')
    processing_progress = models.IntegerField(default=0)
    processing_started_at = models.DateTimeField(blank=True, null=True)
    processing_finished_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
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

    @property
    def has_video_upload_history(self):
        return bool(
            self.video_upload_filename
            or self.video_upload_size_bytes
            or self.video_upload_duration_ms
            or self.video_uploaded_at
        )

    @property
    def video_upload_duration_label(self):
        total_ms = int(self.video_upload_duration_ms or 0)
        if total_ms <= 0:
            return ''

        total_seconds, milliseconds = divmod(total_ms, 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if hours:
            parts.append(f'{hours} h')
        if minutes:
            parts.append(f'{minutes} min')
        if seconds:
            parts.append(f'{seconds} s')
        if not parts and milliseconds:
            parts.append(f'{milliseconds} ms')
        return ' '.join(parts)


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


class WatchParty(models.Model):
    class ControlMode(models.TextChoices):
        HOST = 'host', 'Solo host'
        SHARED = 'shared', 'Control compartido'

    class PlaybackState(models.TextChoices):
        PAUSED = 'paused', 'Pausada'
        PLAYING = 'playing', 'Reproduciendo'

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='watch_parties')
    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hosted_watch_parties')
    code = models.CharField(max_length=12, unique=True, blank=True)
    control_mode = models.CharField(max_length=12, choices=ControlMode.choices, default=ControlMode.HOST)
    playback_state = models.CharField(max_length=12, choices=PlaybackState.choices, default=PlaybackState.PAUSED)
    current_time_seconds = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_action_at = models.DateTimeField(auto_now=True)
    last_action_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='watch_party_actions',
    )

    class Meta:
        ordering = ['-last_action_at']

    def save(self, *args, **kwargs):
        if not self.code:
            candidate = _generate_watch_party_code()
            while WatchParty.objects.filter(code=candidate).exclude(pk=self.pk).exists():
                candidate = _generate_watch_party_code()
            self.code = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.movie.title} - {self.code}'


class WatchPartyMember(models.Model):
    party = models.ForeignKey(WatchParty, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_party_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_connected = models.BooleanField(default=False)

    class Meta:
        ordering = ['joined_at']
        constraints = [
            models.UniqueConstraint(fields=['party', 'user'], name='unique_watch_party_member')
        ]

    def __str__(self):
        return f'{self.user} en {self.party.code}'


class WatchPartyMessage(models.Model):
    party = models.ForeignKey(WatchParty, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_party_messages')
    text = models.CharField(max_length=400)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user} en {self.party.code}: {self.text[:40]}'
