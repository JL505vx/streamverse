from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from movies.models import Genre, Movie

from .models import UserProfile


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
    class Meta:
        model = UserProfile
        fields = ['display_name', 'bio', 'avatar_url', 'avatar_file', 'autoplay_enabled']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tu nombre visible'}),
            'bio': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Una frase sobre ti'}),
            'avatar_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'avatar_file': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'autoplay_enabled': forms.CheckboxInput(attrs={'class': 'form-check'}),
        }


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
    class Meta:
        model = Movie
        fields = [
            'title',
            'content_type',
            'genre',
            'synopsis',
            'release_year',
            'cover_url',
            'cover_file',
            'video_url',
            'video_file',
            'is_published',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Titulo de la pelicula o serie'}),
            'content_type': forms.Select(attrs={'class': 'form-input'}),
            'genre': forms.Select(attrs={'class': 'form-input'}),
            'synopsis': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Descripcion corta'}),
            'release_year': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '2026'}),
            'cover_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'cover_file': forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
            'video_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'video_file': forms.FileInput(attrs={'class': 'form-input', 'accept': 'video/*'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check'}),
        }

    def __init__(self, *args, **kwargs):
        ensure_default_genres()
        super().__init__(*args, **kwargs)
        self.fields['genre'].queryset = Genre.objects.order_by('name')
        self.fields['genre'].empty_label = 'Selecciona un genero'
        self.fields['cover_file'].help_text = 'Si subes una portada nueva, reemplaza la actual.'
        self.fields['video_file'].help_text = 'Si subes un video nuevo, reemplaza el actual.'


class MovieMediaForm(forms.ModelForm):
    remove_cover_file = forms.BooleanField(
        required=False,
        label='Quitar portada local actual',
        widget=forms.CheckboxInput(attrs={'class': 'form-check'}),
    )
    remove_video_file = forms.BooleanField(
        required=False,
        label='Quitar video local actual',
        widget=forms.CheckboxInput(attrs={'class': 'form-check'}),
    )

    class Meta:
        model = Movie
        fields = ['cover_url', 'cover_file', 'video_url', 'video_file']
        widgets = {
            'cover_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'cover_file': forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
            'video_url': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://... (opcional)'}),
            'video_file': forms.FileInput(attrs={'class': 'form-input', 'accept': 'video/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cover_file'].help_text = 'Sube otra portada para reemplazar la actual.'
        self.fields['video_file'].help_text = 'Sube otro video para reemplazar el actual.'

    def save(self, commit=True):
        movie = super().save(commit=False)

        if self.cleaned_data.get('remove_cover_file'):
            if movie.cover_file:
                movie.cover_file.delete(save=False)
            movie.cover_file = ''

        if self.cleaned_data.get('remove_video_file'):
            if movie.video_file:
                movie.video_file.delete(save=False)
            movie.video_file = ''

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
