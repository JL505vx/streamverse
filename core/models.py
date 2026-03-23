from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=80, blank=True)
    avatar_file = models.FileField(upload_to='avatars/', blank=True, null=True)
    avatar_url = models.URLField(blank=True)
    bio = models.CharField(max_length=180, blank=True)
    autoplay_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f'Perfil de {self.user.username}'
