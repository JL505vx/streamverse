from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=80, blank=True)
    avatar_url = models.URLField(blank=True)
    bio = models.CharField(max_length=180, blank=True)
    autoplay_enabled = models.BooleanField(default=True)
    favorite_genres = models.ManyToManyField('movies.Genre', blank=True, related_name='preferred_by_profiles')
    parental_lock_enabled = models.BooleanField(default=False)
    parental_pin_hash = models.CharField(max_length=128, blank=True)
    parental_restricted_genres = models.ManyToManyField('movies.Genre', blank=True, related_name='restricted_by_profiles')

    def __str__(self):
        return f'Perfil de {self.user.username}'

    @property
    def has_avatar(self):
        return bool(self.avatar_url)

    def set_parental_pin(self, raw_pin: str):
        pin = (raw_pin or '').strip()
        self.parental_pin_hash = make_password(pin) if pin else ''

    def check_parental_pin(self, raw_pin: str) -> bool:
        if not self.parental_pin_hash:
            return False
        return check_password((raw_pin or '').strip(), self.parental_pin_hash)


class ContentSuggestion(models.Model):
    class ContentType(models.TextChoices):
        MOVIE = 'movie', 'Pelicula'
        SERIES = 'series', 'Serie'
        ANY = 'any', 'Indistinto'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        REVIEWING = 'reviewing', 'En revision'
        APPROVED = 'approved', 'Aprobada'
        REJECTED = 'rejected', 'Rechazada'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='content_suggestions')
    title = models.CharField(max_length=180)
    content_type = models.CharField(max_length=10, choices=ContentType.choices, default=ContentType.ANY)
    preferred_genre = models.ForeignKey('movies.Genre', on_delete=models.SET_NULL, null=True, blank=True, related_name='suggestions')
    details = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    admin_response = models.TextField(blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_suggestions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.title} ({self.user.username})'


class SuggestionMessage(models.Model):
    suggestion = models.ForeignKey(ContentSuggestion, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suggestion_messages')
    text = models.CharField(max_length=600)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Msg {self.suggestion_id} by {self.sender.username}'


class UserNotification(models.Model):
    class Kind(models.TextChoices):
        INFO = 'info', 'Info'
        SUGGESTION = 'suggestion', 'Sugerencia'
        SYSTEM = 'system', 'Sistema'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=400, blank=True)
    link_url = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Notificacion {self.user.username}: {self.title}'


class UserCustomList(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='custom_lists')
    name = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_user_custom_list_name')
        ]

    def __str__(self):
        return f'{self.user.username}: {self.name}'


class UserCustomListItem(models.Model):
    custom_list = models.ForeignKey(UserCustomList, on_delete=models.CASCADE, related_name='items')
    movie = models.ForeignKey('movies.Movie', on_delete=models.CASCADE, related_name='custom_list_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_at']
        constraints = [
            models.UniqueConstraint(fields=['custom_list', 'movie'], name='unique_custom_list_item')
        ]

    def __str__(self):
        return f'{self.custom_list.name}: {self.movie.title}'


class MovieRating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movie_ratings')
    movie = models.ForeignKey('movies.Movie', on_delete=models.CASCADE, related_name='ratings')
    score = models.PositiveSmallIntegerField(default=3)
    note = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], name='unique_user_movie_rating')
        ]

    def __str__(self):
        return f'{self.user.username} -> {self.movie.title} ({self.score})'
