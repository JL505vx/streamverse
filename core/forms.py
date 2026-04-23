from pathlib import Path

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.conf import settings
from django.core.validators import URLValidator
from django.utils import timezone

from movies.models import Genre, Movie

from .local_media import delete_local_video, get_local_video_max_bytes, save_uploaded_video_locally
from .models import (
    ContentSuggestion,
    MovieRating,
    SuggestionMessage,
    UserCustomList,
    UserCustomListItem,
    UserProfile,
)
from .supabase_storage import delete_public_file, upload_uploaded_file


COMMON_GENRES = [
    'Accion',
    'Animacion',
    'Aventura',
    'Ciencia Ficcion',
    'Comedia',
    'Crimen',
    'Documental',
    'Drama',
    'Fantasia',
    'Romance',
    'Suspenso',
    'Terror',
    'Thriller',
]


def ensure_default_genres():
    existing = set(Genre.objects.values_list('name', flat=True))
    missing = [Genre(name=name) for name in COMMON_GENRES if name not in existing]
    if missing:
        Genre.objects.bulk_create(missing, ignore_conflicts=True)


def clean_media_or_remote_video_url(raw_value: str) -> str:
    value = (raw_value or '').strip()
    if not value:
        return ''
    if value.startswith(settings.MEDIA_URL):
        return value
    validator = URLValidator()
    validator(value)
    return value


def _coerce_non_negative_int(raw_value) -> int:
    try:
        parsed = int(raw_value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _apply_video_upload_metadata(movie, *, filename='', size_bytes=0, duration_ms=0):
    movie.video_upload_filename = (filename or '')[:255]
    movie.video_upload_size_bytes = _coerce_non_negative_int(size_bytes)
    movie.video_upload_duration_ms = _coerce_non_negative_int(duration_ms)
    movie.video_uploaded_at = timezone.now()


def _clear_video_upload_metadata(movie):
    movie.video_upload_filename = ''
    movie.video_upload_size_bytes = 0
    movie.video_upload_duration_ms = 0
    movie.video_uploaded_at = None


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-input', 'placeholder': 'Tu usuario'})
        self.fields['password'].widget.attrs.update({'class': 'form-input', 'placeholder': 'Tu contrasena'})


class UserSignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': 'Elige un usuario',
            'email': 'correo@ejemplo.com',
            'password1': 'Minimo 8 caracteres',
            'password2': 'Repite tu contrasena',
        }
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-input', 'placeholder': placeholders.get(name, '')})

        self.fields['username'].help_text = ''
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''


class UserSettingsForm(forms.ModelForm):
    avatar_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
    )
    parental_pin = forms.CharField(
        required=False,
        label='PIN parental',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': '4 digitos (opcional)'}),
    )
    parental_pin_confirm = forms.CharField(
        required=False,
        label='Confirmar PIN',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Repite el PIN'}),
    )

    class Meta:
        model = UserProfile
        fields = [
            'display_name',
            'bio',
            'avatar_url',
            'autoplay_enabled',
            'favorite_genres',
            'parental_lock_enabled',
            'parental_restricted_genres',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tu nombre visible'}),
            'bio': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Una frase sobre ti'}),
            'avatar_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'autoplay_enabled': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'favorite_genres': forms.SelectMultiple(attrs={'class': 'form-input', 'size': 6}),
            'parental_lock_enabled': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'parental_restricted_genres': forms.SelectMultiple(attrs={'class': 'form-input', 'size': 6}),
        }

    def clean(self):
        cleaned_data = super().clean()
        pin = (cleaned_data.get('parental_pin') or '').strip()
        pin_confirm = (cleaned_data.get('parental_pin_confirm') or '').strip()
        lock_enabled = cleaned_data.get('parental_lock_enabled')

        if lock_enabled and not (self.instance and self.instance.parental_pin_hash) and not pin:
            raise forms.ValidationError('Activa un PIN parental para usar el bloqueo por genero.')

        if pin:
            if not pin.isdigit() or len(pin) != 4:
                raise forms.ValidationError('El PIN debe tener exactamente 4 digitos numericos.')
            if pin != pin_confirm:
                raise forms.ValidationError('La confirmacion del PIN no coincide.')

        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        avatar_upload = self.cleaned_data.get('avatar_file')
        pin = (self.cleaned_data.get('parental_pin') or '').strip()

        if avatar_upload:
            profile.avatar_url = upload_uploaded_file(avatar_upload, folder='avatars', replace_url=profile.avatar_url)
        if pin:
            profile.set_parental_pin(pin)
        if commit:
            profile.save()
            self.save_m2m()
        return profile


class ContentSuggestionForm(forms.ModelForm):
    class Meta:
        model = ContentSuggestion
        fields = ['title', 'content_type', 'preferred_genre', 'details']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Spider-Man Beyond'}),
            'content_type': forms.Select(attrs={'class': 'form-input'}),
            'preferred_genre': forms.Select(attrs={'class': 'form-input'}),
            'details': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Por que te gustaria verla'}),
        }


class SuggestionMessageForm(forms.ModelForm):
    class Meta:
        model = SuggestionMessage
        fields = ['text']
        widgets = {
            'text': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Mensaje corto sobre la sugerencia...'}),
        }


class UserCustomListForm(forms.ModelForm):
    class Meta:
        model = UserCustomList
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Noche de accion'}),
        }


class UserCustomListAddForm(forms.Form):
    custom_list = forms.ModelChoiceField(
        queryset=UserCustomList.objects.none(),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Lista',
    )
    movie = forms.ModelChoiceField(
        queryset=Movie.objects.filter(is_published=True).order_by('title'),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Pelicula/Serie',
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields['custom_list'].queryset = UserCustomList.objects.filter(user=user).order_by('name')

    def save(self):
        return UserCustomListItem.objects.get_or_create(
            custom_list=self.cleaned_data['custom_list'],
            movie=self.cleaned_data['movie'],
        )


class MovieRatingForm(forms.ModelForm):
    score = forms.ChoiceField(
        choices=[(1, '1 estrella'), (2, '2 estrellas'), (3, '3 estrellas'), (4, '4 estrellas'), (5, '5 estrellas')],
        widget=forms.Select(attrs={'class': 'form-input'}),
    )

    class Meta:
        model = MovieRating
        fields = ['movie', 'score', 'note']
        widgets = {
            'movie': forms.Select(attrs={'class': 'form-input'}),
            'note': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Comentario opcional'}),
        }


class ParentalUnlockForm(forms.Form):
    pin = forms.CharField(
        label='PIN',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'PIN de 4 digitos'}),
    )


class UserAccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nombre'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Apellido'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'correo@ejemplo.com'}),
        }


class GenreAdminForm(forms.ModelForm):
    class Meta:
        model = Genre
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej. Accion'}),
        }


class MovieAdminForm(forms.ModelForm):
    video_url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'https://... o /media/... (opcional)'}),
    )
    cover_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
    )
    video_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'video/*'}),
    )
    chunk_upload_completed = forms.BooleanField(required=False, widget=forms.HiddenInput())
    chunk_upload_duration_ms = forms.IntegerField(required=False, widget=forms.HiddenInput())
    chunk_upload_filename = forms.CharField(required=False, widget=forms.HiddenInput())
    chunk_upload_size_bytes = forms.IntegerField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Movie
        fields = [
            'title',
            'content_type',
            'genre',
            'synopsis',
            'release_year',
            'cover_url',
            'video_url',
            'is_published',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Titulo de la pelicula o serie'}),
            'content_type': forms.Select(attrs={'class': 'form-input'}),
            'genre': forms.Select(attrs={'class': 'form-input'}),
            'synopsis': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Descripcion corta'}),
            'release_year': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '2026'}),
            'cover_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check'}),
        }

    def __init__(self, *args, **kwargs):
        ensure_default_genres()
        super().__init__(*args, **kwargs)
        self.original_video_url = self.instance.video_url if self.instance and self.instance.pk else ''
        video_storage_path = str(Path(settings.MEDIA_ROOT) / 'videos')
        self.fields['genre'].queryset = Genre.objects.order_by('name')
        self.fields['genre'].empty_label = 'Selecciona un genero'
        self.fields['cover_file'].help_text = 'Si subes una portada nueva, se guardara en Supabase Storage.'
        self.fields['video_file'].help_text = f'Si subes un video nuevo, se guardara en almacenamiento local ({video_storage_path}) y se enlazara desde video_url.'

    def clean_video_file(self):
        video_upload = self.cleaned_data.get('video_file')
        if not video_upload:
            return video_upload
        if video_upload.size > get_local_video_max_bytes():
            raise forms.ValidationError('Los videos grandes deben cargarse por URL o almacenamiento local')
        return video_upload

    def clean_video_url(self):
        return clean_media_or_remote_video_url(self.cleaned_data.get('video_url'))

    def save(self, commit=True):
        movie = super().save(commit=False)
        cover_upload = self.cleaned_data.get('cover_file')
        video_upload = self.cleaned_data.get('video_file')
        chunk_upload_completed = self.cleaned_data.get('chunk_upload_completed')
        chunk_upload_duration_ms = self.cleaned_data.get('chunk_upload_duration_ms')
        chunk_upload_filename = self.cleaned_data.get('chunk_upload_filename')
        chunk_upload_size_bytes = self.cleaned_data.get('chunk_upload_size_bytes')

        if cover_upload:
            movie.cover_url = upload_uploaded_file(cover_upload, folder='covers', replace_url=movie.cover_url)
        if video_upload:
            delete_local_video(self.original_video_url)
            delete_public_file(self.original_video_url)
            movie.video_url = save_uploaded_video_locally(video_upload)
            _apply_video_upload_metadata(
                movie,
                filename=getattr(video_upload, 'name', ''),
                size_bytes=getattr(video_upload, 'size', 0),
            )
        elif chunk_upload_completed and movie.video_url:
            if movie.video_url != self.original_video_url:
                delete_local_video(self.original_video_url)
                delete_public_file(self.original_video_url)
            _apply_video_upload_metadata(
                movie,
                filename=chunk_upload_filename,
                size_bytes=chunk_upload_size_bytes,
                duration_ms=chunk_upload_duration_ms,
            )
        elif movie.video_url != self.original_video_url:
            delete_local_video(self.original_video_url)
            delete_public_file(self.original_video_url)
            _clear_video_upload_metadata(movie)

        if commit:
            movie.save()
        return movie


class MovieMediaForm(forms.ModelForm):
    video_url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'https://... o /media/... (opcional)'}),
    )
    cover_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
    )
    video_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'video/*'}),
    )
    remove_cover_file = forms.BooleanField(
        required=False,
        label='Quitar portada actual',
        widget=forms.CheckboxInput(attrs={'class': 'form-check'}),
    )
    remove_video_file = forms.BooleanField(
        required=False,
        label='Quitar video actual',
        widget=forms.CheckboxInput(attrs={'class': 'form-check'}),
    )
    chunk_upload_completed = forms.BooleanField(required=False, widget=forms.HiddenInput())
    chunk_upload_duration_ms = forms.IntegerField(required=False, widget=forms.HiddenInput())
    chunk_upload_filename = forms.CharField(required=False, widget=forms.HiddenInput())
    chunk_upload_size_bytes = forms.IntegerField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Movie
        fields = ['cover_url', 'video_url']
        widgets = {
            'cover_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_video_url = self.instance.video_url if self.instance and self.instance.pk else ''
        video_storage_path = str(Path(settings.MEDIA_ROOT) / 'videos')
        self.fields['cover_file'].help_text = 'Sube otra portada y se reemplazara la URL actual.'
        self.fields['video_file'].help_text = f'Sube otro video y se reemplazara la URL actual en almacenamiento local ({video_storage_path}).'

    def clean_video_file(self):
        video_upload = self.cleaned_data.get('video_file')
        if not video_upload:
            return video_upload
        if video_upload.size > get_local_video_max_bytes():
            raise forms.ValidationError('Los videos grandes deben cargarse por URL o almacenamiento local')
        return video_upload

    def clean_video_url(self):
        return clean_media_or_remote_video_url(self.cleaned_data.get('video_url'))

    def save(self, commit=True):
        movie = super().save(commit=False)
        cover_upload = self.cleaned_data.get('cover_file')
        video_upload = self.cleaned_data.get('video_file')
        chunk_upload_completed = self.cleaned_data.get('chunk_upload_completed')
        chunk_upload_duration_ms = self.cleaned_data.get('chunk_upload_duration_ms')
        chunk_upload_filename = self.cleaned_data.get('chunk_upload_filename')
        chunk_upload_size_bytes = self.cleaned_data.get('chunk_upload_size_bytes')

        if self.cleaned_data.get('remove_cover_file'):
            delete_public_file(movie.cover_url)
            movie.cover_url = ''

        if self.cleaned_data.get('remove_video_file'):
            delete_local_video(movie.video_url)
            delete_public_file(movie.video_url)
            movie.video_url = ''
            _clear_video_upload_metadata(movie)

        if cover_upload:
            movie.cover_url = upload_uploaded_file(cover_upload, folder='covers', replace_url=movie.cover_url)

        if video_upload:
            delete_local_video(self.original_video_url)
            delete_public_file(self.original_video_url)
            movie.video_url = save_uploaded_video_locally(video_upload)
            _apply_video_upload_metadata(
                movie,
                filename=getattr(video_upload, 'name', ''),
                size_bytes=getattr(video_upload, 'size', 0),
            )
        elif chunk_upload_completed and movie.video_url:
            if movie.video_url != self.original_video_url:
                delete_local_video(self.original_video_url)
                delete_public_file(self.original_video_url)
            _apply_video_upload_metadata(
                movie,
                filename=chunk_upload_filename,
                size_bytes=chunk_upload_size_bytes,
                duration_ms=chunk_upload_duration_ms,
            )
        elif movie.video_url != self.original_video_url:
            delete_local_video(self.original_video_url)
            delete_public_file(self.original_video_url)
            _clear_video_upload_metadata(movie)

        if commit:
            movie.save()
        return movie


class BulkCatalogImportForm(forms.Form):
    entries = forms.CharField(
        label='Titulos a crear',
        widget=forms.Textarea(
            attrs={
                'class': 'form-input',
                'rows': 12,
                'placeholder': 'Que Paso Ayer\nSangre por sangre|1993|Drama\nTarzan|1999|Animacion|movie',
            }
        ),
        help_text='Un titulo por linea. Formatos permitidos: titulo, titulo|ano, titulo|ano|genero, titulo|ano|genero|tipo.',
    )
    default_genre = forms.CharField(
        label='Genero por defecto',
        initial='Pendiente',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Pendiente'}),
    )
    default_release_year = forms.IntegerField(
        label='Ano por defecto',
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '2024'}),
    )
    default_content_type = forms.ChoiceField(
        label='Tipo por defecto',
        choices=Movie.ContentType.choices,
        initial=Movie.ContentType.MOVIE,
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    is_published = forms.BooleanField(
        label='Publicar al crear',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check'}),
    )


class AdminUserCreateForm(UserCreationForm):
    email = forms.EmailField(required=True)
    is_staff = forms.BooleanField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'is_staff', 'is_active', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name.startswith('password'):
                field.widget.attrs.update({'class': 'form-input', 'placeholder': 'Contrasena'})
            elif name in ('is_staff', 'is_active'):
                field.widget.attrs.update({'class': 'form-check'})
            else:
                field.widget.attrs.update({'class': 'form-input'})


class AdminUserUpdateForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Nueva contrasena (opcional)'}),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'is_staff', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('new_password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
