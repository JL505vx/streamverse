from datetime import timedelta
import json
import logging
import mimetypes
import os
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.db.models import Count, Max, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils._os import safe_join
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.views.decorators.http import require_POST

from movies.models import Favorite, Genre, Movie, PlaybackProgress, WatchSession

from .forms import (
    AdminUserCreateForm,
    AdminUserUpdateForm,
    BulkCatalogImportForm,
    ContentSuggestionForm,
    GenreAdminForm,
    MovieRatingForm,
    MovieAdminForm,
    MovieMediaForm,
    SuggestionMessageForm,
    UserAccountForm,
    UserCustomListAddForm,
    UserCustomListForm,
    UserSettingsForm,
    UserSignupForm,
)
from .models import (
    ContentSuggestion,
    MovieRating,
    SuggestionMessage,
    UserCustomList,
    UserCustomListItem,
    UserNotification,
    UserProfile,
)
from .session_scopes import resolve_auth_scope
from .local_media import append_chunk_to_upload, delete_local_video, finalize_chunk_upload
from .supabase_storage import delete_public_file


admin_required = user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
logger = logging.getLogger(__name__)


def _movie_has_missing_video(movie):
    return not movie.video_file_exists


def _describe_uploaded_file(uploaded_file):
    if not uploaded_file:
        return 'sin archivo'
    return (
        f"nombre={getattr(uploaded_file, 'name', '')!r} "
        f"size={getattr(uploaded_file, 'size', 0)} "
        f"content_type={getattr(uploaded_file, 'content_type', '')!r}"
    )


def _log_movie_upload_request(request, action_label, movie=None):
    video_upload = request.FILES.get('video_file')
    cover_upload = request.FILES.get('cover_file')
    logger.info(
        'Upload admin %s movie_id=%s content_type=%s content_length=%s files=%s video=(%s) portada=(%s) media_root=%s',
        action_label,
        getattr(movie, 'pk', None),
        request.META.get('CONTENT_TYPE', ''),
        request.META.get('CONTENT_LENGTH', ''),
        list(request.FILES.keys()),
        _describe_uploaded_file(video_upload),
        _describe_uploaded_file(cover_upload),
        settings.MEDIA_ROOT,
    )


def _log_movie_upload_result(action_label, movie):
    logger.info(
        'Upload admin %s resultado movie_id=%s title=%r video_url=%r local=%s existe=%s ruta=%s upload_file=%r upload_size=%s upload_duration_ms=%s upload_at=%s',
        action_label,
        movie.pk,
        movie.title,
        movie.video_url,
        movie.video_is_local,
        movie.video_file_exists,
        movie.local_video_path,
        movie.video_upload_filename,
        movie.video_upload_size_bytes,
        movie.video_upload_duration_ms,
        movie.video_uploaded_at,
    )


def _log_invalid_movie_form(action_label, form):
    logger.warning(
        'Upload admin %s invalido errors=%s',
        action_label,
        form.errors.as_json(),
    )


def _build_member_greeting(current_time):
    hour = current_time.hour
    if 5 <= hour < 12:
        return (
            'Buenos dias',
            'Luces suaves, algo rico para desayunar y una peli lista para arrancar sin prisas.',
        )
    if 12 <= hour < 19:
        return (
            'Buenas tardes',
            'Tu sala ya esta encendida para seguir donde te quedaste o descubrir algo nuevo.',
        )
    return (
        'Buenas noches',
        'Todo esta listo para una sesion larga: ambiente oscuro, atajos a mano y tu fila esperandote.',
    )


def _format_watch_runtime(total_seconds):
    total_seconds = max(int(total_seconds or 0), 0)
    if total_seconds <= 0:
        return 'Aun no hay tiempo acumulado'

    total_minutes, _ = divmod(total_seconds, 60)
    hours, minutes = divmod(total_minutes, 60)

    if hours and minutes:
        return f'{hours} h {minutes} min de avance guardado'
    if hours:
        return f'{hours} h de avance guardado'
    return f'{max(total_minutes, 1)} min de avance guardado'


def _format_relative_label(timestamp):
    if not timestamp:
        return 'Sin reproducciones recientes'

    delta = timezone.localtime() - timezone.localtime(timestamp)
    minutes = max(int(delta.total_seconds() // 60), 0)

    if minutes < 1:
        return 'Activo justo ahora'
    if minutes < 60:
        return f'Activo hace {minutes} min'

    hours = minutes // 60
    if hours < 24:
        return f'Activo hace {hours} h'

    days = hours // 24
    return f'Activo hace {days} dia{"s" if days != 1 else ""}'


def media_stream_view(request, path):
    file_path = safe_join(settings.MEDIA_ROOT, path)
    if not file_path or not os.path.exists(file_path):
        raise Http404('Archivo no encontrado.')

    file_size = os.path.getsize(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    range_header = request.headers.get('Range', '')

    if not range_header:
        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        return response

    match = re.match(r'bytes=(\d*)-(\d*)', range_header)
    if not match:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{file_size}'
        return response

    start_raw, end_raw = match.groups()
    start = int(start_raw) if start_raw else 0
    end = int(end_raw) if end_raw else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{file_size}'
        return response

    with open(file_path, 'rb') as source:
        source.seek(start)
        content = source.read(end - start + 1)

    response = HttpResponse(content, status=206, content_type=content_type)
    response['Content-Length'] = str(end - start + 1)
    response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    response['Accept-Ranges'] = 'bytes'
    return response


@require_POST
def upload_chunk_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'ok': False, 'error': 'No autorizado.'}, status=403)

    uploaded_chunk = request.FILES.get('file')
    filename = (request.POST.get('filename') or '').strip()
    upload_id = (request.POST.get('upload_id') or '').strip()

    try:
        chunk_index = int(request.POST.get('chunk', '0'))
        total_chunks = int(request.POST.get('total_chunks', '0'))
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Datos de chunk invalidos.'}, status=400)

    if not uploaded_chunk or not filename or not upload_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos del chunk.'}, status=400)
    if chunk_index < 0 or total_chunks <= 0:
        return JsonResponse({'ok': False, 'error': 'Configuracion de chunks invalida.'}, status=400)

    try:
        append_chunk_to_upload(upload_id, filename, uploaded_chunk, chunk_index)
        is_last_chunk = chunk_index >= total_chunks - 1
        video_url = finalize_chunk_upload(upload_id, filename) if is_last_chunk else ''
    except FileNotFoundError as exc:
        logger.warning('Upload chunk incompleto upload_id=%s chunk=%s error=%s', upload_id, chunk_index, exc)
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        logger.exception('Error procesando upload por chunks upload_id=%s chunk=%s', upload_id, chunk_index)
        return JsonResponse({'ok': False, 'error': f'No se pudo procesar el chunk: {exc}'}, status=500)

    logger.info(
        'Chunk procesado upload_id=%s chunk=%s/%s completo=%s video_url=%s',
        upload_id,
        chunk_index + 1,
        total_chunks,
        is_last_chunk,
        video_url,
    )
    return JsonResponse(
        {
            'ok': True,
            'chunk': chunk_index,
            'complete': is_last_chunk,
            'video_url': video_url,
        }
    )


class RoleLoginView(LoginView):
    """Redirect users to their proper area right after login."""

    redirect_authenticated_user = True
    forced_auth_scope = None

    def get_auth_scope(self):
        return self.forced_auth_scope or resolve_auth_scope(self.request)

    def dispatch(self, request, *args, **kwargs):
        request.auth_scope = self.get_auth_scope()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['auth_scope'] = getattr(self.request, 'auth_scope', self.get_auth_scope())
        return context

    def form_valid(self, form):
        scope = getattr(self.request, 'auth_scope', self.get_auth_scope())
        if scope == 'admin' and not form.get_user().is_staff:
            form.add_error(None, 'Necesitas una cuenta de administrador para entrar al panel.')
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to and url_has_allowed_host_and_scheme(
            redirect_to,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect_to

        scope = getattr(self.request, 'auth_scope', self.get_auth_scope())
        if scope == 'admin' or self.request.user.is_staff:
            return reverse('admin_panel')
        return reverse('user_dashboard')


class AdminLoginView(RoleLoginView):
    forced_auth_scope = 'admin'


class RoleLogoutView(LogoutView):
    forced_auth_scope = None

    def dispatch(self, request, *args, **kwargs):
        request.auth_scope = self.forced_auth_scope or resolve_auth_scope(request)
        return super().dispatch(request, *args, **kwargs)


class AdminLogoutView(RoleLogoutView):
    forced_auth_scope = 'admin'


def csrf_failure_view(request, reason='', template_name='errors/csrf_failure.html'):
    auth_scope = resolve_auth_scope(request)
    is_admin_scope = auth_scope == 'admin'
    user = getattr(request, 'user', None)
    is_authenticated = bool(user and user.is_authenticated)

    safe_referer = ''
    referer = request.META.get('HTTP_REFERER', '')
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        safe_referer = referer

    if is_admin_scope:
        primary_url = safe_referer or (reverse('admin_panel') if is_authenticated and user.is_staff else reverse('admin_login'))
        primary_label = 'Volver al panel' if is_authenticated and getattr(user, 'is_staff', False) else 'Entrar como admin'
        secondary_url = reverse('home')
        secondary_label = 'Ir al inicio'
    else:
        primary_url = safe_referer or (reverse('user_dashboard') if is_authenticated else reverse('login'))
        primary_label = 'Volver a mi espacio' if is_authenticated else 'Entrar de nuevo'
        secondary_url = reverse('home')
        secondary_label = 'Ir al inicio'

    context = {
        'auth_scope': auth_scope,
        'is_admin_scope': is_admin_scope,
        'primary_url': primary_url,
        'primary_label': primary_label,
        'secondary_url': secondary_url,
        'secondary_label': secondary_label,
        'debug_reason': reason if settings.DEBUG else '',
    }
    return render(request, template_name, context=context, status=403)


def get_user_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def create_user_notification(user, title, body='', *, kind=UserNotification.Kind.INFO, link_url=''):
    if not user:
        return None
    return UserNotification.objects.create(
        user=user,
        kind=kind,
        title=(title or '')[:120],
        body=(body or '')[:400],
        link_url=(link_url or '')[:240],
    )


def _get_parental_unlock_map(request):
    unlocked = request.session.get('parental_unlocked_genres', [])
    return set(int(value) for value in unlocked if str(value).isdigit())


def pwa_manifest_view(request):
    payload = {
        'name': 'StreamVerse',
        'short_name': 'StreamVerse',
        'id': '/',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#020509',
        'theme_color': '#020509',
        'description': 'StreamVerse local y free streaming.',
        'categories': ['entertainment', 'video'],
        'icons': [
            {
                'src': '/static/pwa/icon-192.png?v=2',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any maskable',
            },
            {
                'src': '/static/pwa/icon-512.png?v=2',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any maskable',
            },
        ],
    }
    return HttpResponse(json.dumps(payload), content_type='application/manifest+json')


def pwa_service_worker_view(request):
    js = """
const CACHE_NAME = 'streamverse-pwa-v2';
const OFFLINE_URL = '/offline/';
const ASSETS = [
  '/',
  OFFLINE_URL,
  '/static/css/main.css',
  '/static/js/cinema-bg.js',
  '/static/js/cinema-scene.js',
  '/static/js/rail-carousel.js',
  '/static/js/sv-effects.js',
  '/static/pwa/icon-192.png?v=2',
  '/static/pwa/icon-512.png?v=2'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((hit) => hit || caches.match(OFFLINE_URL)))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
      return res;
    }).catch(() => hit))
  );
});
"""
    return HttpResponse(js.strip(), content_type='application/javascript')


def offline_view(request):
    return render(request, 'errors/offline.html')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('user_dashboard')

    if request.method == 'POST':
        form = UserSignupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserSignupForm()

    return render(request, 'core/signup.html', {'form': form})


@login_required
def user_dashboard_view(request):
    profile = get_user_profile(request.user)
    unlocked_genres = _get_parental_unlock_map(request)
    restricted_genre_ids = set(profile.parental_restricted_genres.values_list('id', flat=True)) if profile.parental_lock_enabled else set()

    recent_movies = list(Movie.objects.filter(is_published=True).select_related('genre').order_by('-created_at')[:8])
    if restricted_genre_ids:
        recent_movies = [movie for movie in recent_movies if (movie.genre_id not in restricted_genre_ids or movie.genre_id in unlocked_genres)]

    favorites = list(Favorite.objects.filter(user=request.user).select_related('movie', 'movie__genre')[:10])
    continue_watching = list(
        PlaybackProgress.objects.filter(user=request.user, progress_seconds__gt=0, completed=False)
        .select_related('movie', 'movie__genre')
        .order_by('-last_watched')[:10]
    )
    if restricted_genre_ids:
        continue_watching = [
            item for item in continue_watching
            if (item.movie.genre_id not in restricted_genre_ids or item.movie.genre_id in unlocked_genres)
        ]

    watch_qs = WatchSession.objects.filter(user=request.user).select_related('movie')
    recent_sessions = list(watch_qs[:6])
    total_movies = Movie.objects.filter(is_published=True).count()
    favorites_count = Favorite.objects.filter(user=request.user).count()

    hero_recommendation = continue_watching[0].movie if continue_watching else (favorites[0].movie if favorites else (recent_movies[0] if recent_movies else None))
    greeting_title, greeting_copy = _build_member_greeting(timezone.localtime())
    display_name = profile.display_name or request.user.username
    total_progress_seconds = sum(item.progress_seconds for item in continue_watching)
    last_session = recent_sessions[0] if recent_sessions else None
    hero_progress = next(
        (item.progress_seconds for item in continue_watching if hero_recommendation and item.movie_id == hero_recommendation.id),
        0,
    )
    notifications = list(UserNotification.objects.filter(user=request.user).order_by('-created_at')[:8])
    unread_notifications = sum(1 for item in notifications if not item.is_read)
    open_suggestions = list(
        ContentSuggestion.objects.filter(user=request.user)
        .select_related('preferred_genre')
        .prefetch_related('messages')
        .order_by('-updated_at')[:6]
    )
    custom_lists = list(
        UserCustomList.objects.filter(user=request.user)
        .prefetch_related('items__movie')
        .order_by('name')[:8]
    )
    recent_ratings = list(
        MovieRating.objects.filter(user=request.user)
        .select_related('movie')
        .order_by('-updated_at')[:6]
    )

    suggestion_form = ContentSuggestionForm()
    suggestion_message_form = SuggestionMessageForm()
    custom_list_form = UserCustomListForm()
    custom_list_add_form = UserCustomListAddForm(user=request.user)
    rating_form = MovieRatingForm()

    context = {
        'profile': profile,
        'recent_movies': recent_movies,
        'favorites': favorites,
        'continue_watching': continue_watching,
        'recent_sessions': recent_sessions,
        'hero_recommendation': hero_recommendation,
        'hero_progress_label': f'{hero_progress}s guardados' if hero_progress else '',
        'greeting_title': greeting_title,
        'greeting_copy': greeting_copy,
        'display_name': display_name,
        'watch_runtime_label': _format_watch_runtime(total_progress_seconds),
        'recent_presence_label': _format_relative_label(last_session.last_seen if last_session else None),
        'recent_presence_device': (
            f'{last_session.device_type} · {last_session.browser}'
            if last_session
            else 'Cuando empieces a ver algo, aqui apareceran tus ultimas sesiones.'
        ),
        'member_energy_label': 'Maraton activo' if continue_watching else 'Catalogo listo',
        'member_energy_copy': (
            'Tu fila ya tiene reproducciones para continuar sin perder ritmo.'
            if continue_watching
            else 'Explora el catalogo y arma tu primera noche de cine.'
        ),
        'total_movies': total_movies,
        'favorites_count': favorites_count,
        'continue_count': len(continue_watching),
        'new_releases_count': len(recent_movies),
        'notifications': notifications,
        'unread_notifications': unread_notifications,
        'open_suggestions': open_suggestions,
        'custom_lists': custom_lists,
        'recent_ratings': recent_ratings,
        'suggestion_form': suggestion_form,
        'suggestion_message_form': suggestion_message_form,
        'custom_list_form': custom_list_form,
        'custom_list_add_form': custom_list_add_form,
        'rating_form': rating_form,
        'parental_lock_enabled': profile.parental_lock_enabled,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def user_settings_view(request):
    profile = get_user_profile(request.user)
    profile_form = UserSettingsForm(request.POST or None, request.FILES or None, instance=profile)
    account_form = UserAccountForm(request.POST or None, instance=request.user)
    watch_qs = WatchSession.objects.filter(user=request.user).select_related('movie')
    devices = list(watch_qs.values('device_type', 'browser', 'operating_system').distinct()[:8])
    recent_sessions = list(watch_qs[:8])

    if request.method == 'POST' and profile_form.is_valid() and account_form.is_valid():
        try:
            profile_form.save()
            account_form.save()
        except Exception as exc:
            profile_form.add_error(None, f'No se pudo subir el archivo a Supabase Storage: {exc}')
        else:
            messages.success(request, 'Ajustes guardados correctamente.')
            return redirect('user_settings')

    return render(
        request,
        'core/settings.html',
        {
            'profile': profile,
            'profile_form': profile_form,
            'account_form': account_form,
            'devices': devices,
            'recent_sessions': recent_sessions,
        },
    )


@login_required
@require_POST
def user_suggestion_create_view(request):
    form = ContentSuggestionForm(request.POST)
    if form.is_valid():
        suggestion = form.save(commit=False)
        suggestion.user = request.user
        suggestion.save()
        SuggestionMessage.objects.create(
            suggestion=suggestion,
            sender=request.user,
            text='Solicitud creada por el usuario.',
        )
        for admin in User.objects.filter(is_staff=True, is_active=True):
            create_user_notification(
                admin,
                'Nueva sugerencia de catalogo',
                f'{request.user.username} solicito: {suggestion.title}',
                kind=UserNotification.Kind.SUGGESTION,
                link_url=reverse('admin_panel'),
            )
        messages.success(request, 'Sugerencia enviada al admin.')
    else:
        messages.error(request, 'No se pudo enviar la sugerencia. Revisa los campos.')
    return redirect('user_dashboard')


@login_required
@require_POST
def user_suggestion_reply_view(request, suggestion_id):
    suggestion = get_object_or_404(ContentSuggestion, pk=suggestion_id)
    if not (suggestion.user_id == request.user.id or request.user.is_staff):
        messages.error(request, 'No tienes permiso para responder esta sugerencia.')
        return redirect('user_dashboard')

    form = SuggestionMessageForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'El mensaje no puede estar vacio.')
        return redirect('user_dashboard')

    msg = form.save(commit=False)
    msg.suggestion = suggestion
    msg.sender = request.user
    msg.save()

    suggestion.status = ContentSuggestion.Status.REVIEWING
    suggestion.save(update_fields=['status', 'updated_at'])

    target_user = suggestion.user if request.user.is_staff else User.objects.filter(is_staff=True, is_active=True).first()
    if target_user:
        create_user_notification(
            target_user,
            f'Nuevo mensaje en sugerencia: {suggestion.title}',
            msg.text[:180],
            kind=UserNotification.Kind.SUGGESTION,
            link_url=reverse('user_dashboard') if target_user == suggestion.user else reverse('admin_panel'),
        )

    messages.success(request, 'Mensaje enviado.')
    return redirect('admin_panel' if request.user.is_staff else 'user_dashboard')


@login_required
@require_POST
def user_custom_list_create_view(request):
    form = UserCustomListForm(request.POST)
    if form.is_valid():
        custom_list = form.save(commit=False)
        custom_list.user = request.user
        custom_list.save()
        messages.success(request, 'Lista creada correctamente.')
    else:
        messages.error(request, 'No se pudo crear la lista.')
    return redirect('user_dashboard')


@login_required
@require_POST
def user_custom_list_add_view(request):
    form = UserCustomListAddForm(request.POST, user=request.user)
    if form.is_valid():
        _, created = form.save()
        messages.success(
            request,
            'Titulo agregado a la lista.' if created else 'Ese titulo ya estaba en la lista.',
        )
    else:
        messages.error(request, 'No se pudo agregar el titulo.')
    return redirect('user_dashboard')


@login_required
@require_POST
def user_custom_list_remove_item_view(request, item_id):
    item = get_object_or_404(UserCustomListItem.objects.select_related('custom_list'), pk=item_id)
    if item.custom_list.user_id != request.user.id:
        messages.error(request, 'No tienes permiso para modificar esta lista.')
        return redirect('user_dashboard')
    item.delete()
    messages.success(request, 'Titulo removido de la lista.')
    return redirect('user_dashboard')


@login_required
@require_POST
def user_rate_movie_view(request):
    form = MovieRatingForm(request.POST)
    if form.is_valid():
        movie = form.cleaned_data['movie']
        score = int(form.cleaned_data['score'])
        note = form.cleaned_data.get('note', '')
        MovieRating.objects.update_or_create(
            user=request.user,
            movie=movie,
            defaults={'score': score, 'note': note},
        )
        messages.success(request, f'Guardaste tu calificacion para {movie.title}.')
    else:
        messages.error(request, 'No se pudo guardar la calificacion.')
    return redirect('user_dashboard')


@login_required
@require_POST
def user_notifications_read_view(request):
    UserNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('user_dashboard')


@login_required
@require_POST
def user_parental_unlock_view(request):
    profile = get_user_profile(request.user)
    pin = (request.POST.get('pin') or '').strip()
    genre_id_raw = (request.POST.get('genre_id') or '').strip()
    genre_id = int(genre_id_raw) if genre_id_raw.isdigit() else None

    if not profile.parental_lock_enabled:
        messages.info(request, 'El control parental no esta activo en tu perfil.')
        return redirect('user_settings')

    if not profile.check_parental_pin(pin):
        messages.error(request, 'PIN incorrecto.')
        return redirect('user_settings')

    unlocked = _get_parental_unlock_map(request)
    if genre_id:
        unlocked.add(genre_id)
    request.session['parental_unlocked_genres'] = sorted(unlocked)
    request.session.modified = True
    messages.success(request, 'Genero desbloqueado para esta sesion.')
    return redirect('user_settings')


@admin_required
@require_POST
def admin_suggestion_status_view(request, suggestion_id):
    suggestion = get_object_or_404(ContentSuggestion, pk=suggestion_id)
    status = (request.POST.get('status') or '').strip()
    response_text = (request.POST.get('admin_response') or '').strip()
    valid_statuses = {value for value, _ in ContentSuggestion.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Estado de sugerencia invalido.')
        return redirect('admin_panel')

    suggestion.status = status
    suggestion.admin_response = response_text
    suggestion.resolved_by = request.user
    suggestion.save(update_fields=['status', 'admin_response', 'resolved_by', 'updated_at'])

    if response_text:
        SuggestionMessage.objects.create(suggestion=suggestion, sender=request.user, text=response_text[:600])

    create_user_notification(
        suggestion.user,
        f'Actualizacion de sugerencia: {suggestion.title}',
        f'Estado: {suggestion.get_status_display()}',
        kind=UserNotification.Kind.SUGGESTION,
        link_url=reverse('user_dashboard'),
    )
    messages.success(request, 'Sugerencia actualizada.')
    return redirect('admin_panel')


@admin_required
def admin_panel_view(request):
    active_since = timezone.now() - timedelta(hours=24)
    watch_qs = WatchSession.objects.select_related('user', 'movie')
    catalog_movies = list(Movie.objects.select_related('genre').order_by('-created_at'))
    missing_video_movies = [movie for movie in catalog_movies if _movie_has_missing_video(movie)]
    missing_cover_movies = [movie for movie in catalog_movies if not movie.cover_url]
    draft_total = sum(1 for movie in catalog_movies if not movie.is_published)

    top_content = (
        Movie.objects.filter(is_published=True)
        .annotate(total_views=Coalesce(Sum('watch_sessions__views_count'), 0))
        .order_by('-total_views', '-created_at')[:6]
    )

    user_activity = (
        watch_qs.values('user__username')
        .annotate(
            total_sessions=Count('id'),
            total_views=Coalesce(Sum('views_count'), 0),
            devices=Count('device_type', distinct=True),
            last_seen=Max('last_seen'),
        )
        .order_by('-last_seen')[:6]
    )

    recent_streams = list(watch_qs[:18])
    histories_map = {}
    for session in recent_streams:
        username = session.user.username
        if username not in histories_map:
            histories_map[username] = {
                'username': username,
                'total_views': 0,
                'devices': set(),
                'last_seen': session.last_seen,
                'entries': [],
            }
        histories_map[username]['total_views'] += session.views_count or 0
        histories_map[username]['devices'].add(f'{session.device_type} / {session.operating_system}')
        histories_map[username]['entries'].append(session)

    user_histories = []
    for item in histories_map.values():
        item['device_count'] = len(item['devices'])
        item['devices'] = sorted(item['devices'])
        user_histories.append(item)
    user_histories.sort(key=lambda item: item['last_seen'], reverse=True)

    catalog_total = len(catalog_movies)
    missing_video_total = len(missing_video_movies)
    missing_cover_total = len(missing_cover_movies)
    complete_total = max(catalog_total - missing_video_total - missing_cover_total - draft_total, 0)

    def percent(value):
        if catalog_total <= 0:
            return 0
        return round((value / catalog_total) * 100)

    catalog_needs = [movie for movie in catalog_movies if _movie_has_missing_video(movie) or not movie.cover_url][:6]
    pending_suggestions = list(
        ContentSuggestion.objects.select_related('user', 'preferred_genre', 'resolved_by')
        .prefetch_related('messages__sender')
        .order_by('-updated_at')[:12]
    )

    context = {
        'movie_count': Movie.objects.filter(content_type=Movie.ContentType.MOVIE).count(),
        'series_count': Movie.objects.filter(content_type=Movie.ContentType.SERIES).count(),
        'genre_count': Genre.objects.count(),
        'user_count': User.objects.count(),
        'latest_movies': Movie.objects.select_related('genre').order_by('-created_at')[:5],
        'latest_users': User.objects.order_by('-date_joined')[:5],
        'active_users_24h': watch_qs.filter(last_seen__gte=active_since).values('user').distinct().count(),
        'active_devices_24h': watch_qs.filter(last_seen__gte=active_since)
        .values('device_type', 'browser', 'operating_system')
        .distinct()
        .count(),
        'total_plays': watch_qs.aggregate(total=Sum('views_count'))['total'] or 0,
        'top_content': top_content,
        'catalog_total': catalog_total,
        'missing_video_total': missing_video_total,
        'missing_cover_total': missing_cover_total,
        'draft_total': draft_total,
        'complete_total': complete_total,
        'complete_percent': percent(complete_total),
        'missing_video_percent': percent(missing_video_total),
        'missing_cover_percent': percent(missing_cover_total),
        'draft_percent': percent(draft_total),
        'user_activity': user_activity,
        'user_histories': user_histories[:6],
        'catalog_needs': catalog_needs,
        'pending_suggestions': pending_suggestions,
    }
    return render(request, 'core/admin_panel.html', context)


@admin_required
def admin_movie_list_view(request):
    missing_video_only = request.GET.get('missing_video') == '1'
    search_query = (request.GET.get('q') or '').strip()
    movie_qs = Movie.objects.select_related('genre').order_by('-created_at')

    if search_query:
        search_filters = Q(title__icontains=search_query) | Q(genre__name__icontains=search_query) | Q(synopsis__icontains=search_query)
        if search_query.isdigit():
            search_filters |= Q(release_year=int(search_query))
        movie_qs = movie_qs.filter(search_filters)

    movies = list(movie_qs)
    if missing_video_only:
        movies = [movie for movie in movies if _movie_has_missing_video(movie)]

    all_movies = list(Movie.objects.select_related('genre').all())
    missing_video_count = sum(1 for movie in all_movies if _movie_has_missing_video(movie))
    missing_cover_count = sum(1 for movie in all_movies if not movie.cover_url)

    context = {
        'movies': movies,
        'missing_video_only': missing_video_only,
        'search_query': search_query,
        'total_count': len(all_movies),
        'missing_video_count': missing_video_count,
        'missing_cover_count': missing_cover_count,
    }
    return render(request, 'core/admin/movies_list.html', context)


@admin_required
def admin_movie_bulk_create_view(request):
    form = BulkCatalogImportForm(request.POST or None)
    preview_lines = [
        'Que Paso Ayer|2009|Comedia',
        'Sangre por sangre|1993|Drama',
        'Tarzan|1999|Animacion',
        'Como entrenar a tu dragon 2|2014|Animacion',
    ]

    if request.method == 'POST' and form.is_valid():
        entries = [line.strip() for line in form.cleaned_data['entries'].splitlines() if line.strip()]
        default_genre_name = form.cleaned_data['default_genre'].strip() or 'Pendiente'
        default_year = form.cleaned_data.get('default_release_year')
        default_type = form.cleaned_data['default_content_type']
        publish_now = form.cleaned_data['is_published']
        default_genre, _ = Genre.objects.get_or_create(name=default_genre_name)

        created = 0
        skipped = 0
        errors = []

        for index, line in enumerate(entries, start=1):
            parts = [part.strip() for part in line.split('|')]
            title = parts[0] if parts else ''
            year = default_year
            genre = default_genre
            content_type = default_type

            if not title:
                errors.append(f'Linea {index}: falta el titulo.')
                continue

            if len(parts) >= 2 and parts[1]:
                if not parts[1].isdigit():
                    errors.append(f'Linea {index}: el ano debe ser numerico.')
                    continue
                year = int(parts[1])

            if len(parts) >= 3 and parts[2]:
                genre, _ = Genre.objects.get_or_create(name=parts[2])

            if len(parts) >= 4 and parts[3]:
                if parts[3] not in {Movie.ContentType.MOVIE, Movie.ContentType.SERIES}:
                    errors.append(f'Linea {index}: el tipo debe ser movie o series.')
                    continue
                content_type = parts[3]

            if not year:
                errors.append(f'Linea {index}: agrega ano o define uno por defecto.')
                continue

            duplicate_exists = Movie.objects.filter(
                title__iexact=title,
                release_year=year,
                content_type=content_type,
            ).exists()
            if duplicate_exists:
                skipped += 1
                continue

            Movie.objects.create(
                title=title,
                release_year=year,
                genre=genre,
                content_type=content_type,
                is_published=publish_now,
            )
            created += 1

        if created:
            messages.success(request, f'Se crearon {created} contenidos nuevos.')
        if skipped:
            messages.warning(request, f'Se omitieron {skipped} duplicados.')
        for error in errors[:6]:
            messages.error(request, error)

        if created and not errors:
            return redirect('admin_movies')

    return render(
        request,
        'core/admin/movie_bulk_form.html',
        {
            'form': form,
            'page_title': 'Carga rapida de catalogo',
            'preview_lines': preview_lines,
        },
    )


@admin_required
def admin_movie_create_view(request):
    form = MovieAdminForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        _log_movie_upload_request(request, 'crear')
    if request.method == 'POST' and form.is_valid():
        try:
            movie = form.save()
        except Exception as exc:
            logger.exception('Error guardando contenido nuevo en admin.')
            form.add_error(None, f'No se pudo subir el archivo a Supabase Storage: {exc}')
        else:
            _log_movie_upload_result('crear', movie)
            messages.success(request, 'Contenido creado correctamente.')
            return redirect('admin_movies')
    elif request.method == 'POST':
        _log_invalid_movie_form('crear', form)
    return render(request, 'core/admin/movie_form.html', {'form': form, 'page_title': 'Nuevo contenido'})


@admin_required
def admin_movie_edit_view(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    form = MovieAdminForm(request.POST or None, request.FILES or None, instance=movie)
    if request.method == 'POST':
        _log_movie_upload_request(request, 'editar', movie)
    if request.method == 'POST' and form.is_valid():
        try:
            movie = form.save()
        except Exception as exc:
            logger.exception('Error actualizando contenido en admin movie_id=%s.', movie.pk)
            form.add_error(None, f'No se pudo subir el archivo a Supabase Storage: {exc}')
        else:
            _log_movie_upload_result('editar', movie)
            messages.success(request, 'Contenido actualizado correctamente.')
            return redirect('admin_movies')
    elif request.method == 'POST':
        _log_invalid_movie_form('editar', form)
    return render(request, 'core/admin/movie_form.html', {'form': form, 'page_title': 'Editar contenido', 'movie': movie})


@admin_required
def admin_movie_media_view(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    form = MovieMediaForm(request.POST or None, request.FILES or None, instance=movie)
    if request.method == 'POST':
        _log_movie_upload_request(request, 'archivos', movie)
    if request.method == 'POST' and form.is_valid():
        try:
            movie = form.save()
        except Exception as exc:
            logger.exception('Error actualizando archivos de contenido movie_id=%s.', movie.pk)
            form.add_error(None, f'No se pudo subir el archivo a Supabase Storage: {exc}')
        else:
            _log_movie_upload_result('archivos', movie)
            messages.success(request, 'Archivos de contenido actualizados correctamente.')
            return redirect('admin_movies')
    elif request.method == 'POST':
        _log_invalid_movie_form('archivos', form)

    return render(request, 'core/admin/movie_media_form.html', {'form': form, 'movie': movie})


@admin_required
def admin_movie_delete_view(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    if request.method == 'POST':
        delete_public_file(movie.cover_url)
        delete_local_video(movie.video_url)
        delete_public_file(movie.video_url)
        movie.delete()
        messages.success(request, 'Contenido eliminado.')
        return redirect('admin_movies')
    return render(request, 'core/admin/movie_confirm_delete.html', {'movie': movie})


@admin_required
def admin_genre_list_view(request):
    genres = Genre.objects.order_by('name')
    return render(request, 'core/admin/genres_list.html', {'genres': genres})


@admin_required
def admin_genre_create_view(request):
    form = GenreAdminForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Genero creado correctamente.')
        return redirect('admin_genres')
    return render(request, 'core/admin/genre_form.html', {'form': form, 'page_title': 'Nuevo genero'})


@admin_required
def admin_genre_edit_view(request, pk):
    genre = get_object_or_404(Genre, pk=pk)
    form = GenreAdminForm(request.POST or None, instance=genre)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Genero actualizado correctamente.')
        return redirect('admin_genres')
    return render(request, 'core/admin/genre_form.html', {'form': form, 'page_title': 'Editar genero'})


@admin_required
def admin_genre_delete_view(request, pk):
    genre = get_object_or_404(Genre, pk=pk)
    if request.method == 'POST':
        try:
            genre.delete()
            messages.success(request, 'Genero eliminado.')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar: hay contenidos ligados a este genero.')
        return redirect('admin_genres')
    return render(request, 'core/admin/genre_confirm_delete.html', {'genre': genre})


@admin_required
def admin_user_list_view(request):
    users = User.objects.order_by('-date_joined')
    return render(request, 'core/admin/users_list.html', {'users': users})


@admin_required
def admin_user_create_view(request):
    form = AdminUserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Usuario creado correctamente.')
        return redirect('admin_users')
    return render(request, 'core/admin/user_form.html', {'form': form, 'page_title': 'Nuevo usuario'})


@admin_required
def admin_user_edit_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    form = AdminUserUpdateForm(request.POST or None, instance=target_user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Usuario actualizado correctamente.')
        return redirect('admin_users')
    return render(request, 'core/admin/user_form.html', {'form': form, 'page_title': 'Editar usuario'})
