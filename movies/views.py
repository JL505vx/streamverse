import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Favorite, Movie, PlaybackProgress, WatchSession


def _detect_device_info(user_agent: str):
    ua = (user_agent or '').lower()

    if any(k in ua for k in ('smart-tv', 'smarttv', 'tizen', 'webos', 'roku', 'aft', 'android tv')):
        device_type = 'TV'
    elif any(k in ua for k in ('ipad', 'tablet')):
        device_type = 'Tablet'
    elif any(k in ua for k in ('mobile', 'android', 'iphone')):
        device_type = 'Movil'
    else:
        device_type = 'PC'

    if 'edg/' in ua:
        browser = 'Edge'
    elif 'opr/' in ua or 'opera' in ua:
        browser = 'Opera'
    elif 'firefox/' in ua:
        browser = 'Firefox'
    elif 'chrome/' in ua and 'edg/' not in ua:
        browser = 'Chrome'
    elif 'safari/' in ua and 'chrome/' not in ua:
        browser = 'Safari'
    else:
        browser = 'Otro'

    if 'windows' in ua:
        operating_system = 'Windows'
    elif 'android' in ua:
        operating_system = 'Android'
    elif any(k in ua for k in ('iphone', 'ipad', 'ios')):
        operating_system = 'iOS'
    elif any(k in ua for k in ('mac os', 'macintosh')):
        operating_system = 'macOS'
    elif 'linux' in ua:
        operating_system = 'Linux'
    else:
        operating_system = 'Otro'

    return device_type, browser, operating_system


def _get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _track_watch_session(request, movie):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    device_type, browser, operating_system = _detect_device_info(user_agent)
    ip_address = _get_client_ip(request)

    session, created = WatchSession.objects.get_or_create(
        user=request.user,
        movie=movie,
        device_type=device_type,
        browser=browser,
        operating_system=operating_system,
        defaults={'ip_address': ip_address, 'user_agent': user_agent},
    )

    if created:
        return

    session.views_count += 1
    session.ip_address = ip_address
    session.user_agent = user_agent
    session.save(update_fields=['views_count', 'ip_address', 'user_agent', 'last_seen'])


def _format_clock(seconds):
    seconds = max(int(seconds or 0), 0)
    mins = seconds // 60
    secs = seconds % 60
    return f'{mins:02d}:{secs:02d}'


def _build_latest_movie_card(movie):
    if not movie:
        return {
            'title': 'Tu proximo estreno',
            'meta': 'Sube una pelicula al catalogo para destacarla aqui',
            'synopsis': 'Esta portada se llenara automaticamente cuando agregues tu siguiente contenido.',
            'detail_url': reverse('admin_movie_create'),
            'background_style': '',
        }

    background_style = ''
    if movie.cover_file:
        background_style = (
            "background-image:linear-gradient(180deg, rgba(8, 10, 18, 0.18), rgba(8, 10, 18, 0.92)), "
            f"url('{movie.cover_file.url}');"
        )
    elif movie.cover_url:
        background_style = (
            "background-image:linear-gradient(180deg, rgba(8, 10, 18, 0.18), rgba(8, 10, 18, 0.92)), "
            f"url('{movie.cover_url}');"
        )

    return {
        'title': movie.title,
        'meta': f'{movie.get_content_type_display()} | {movie.genre.name} | {movie.release_year}',
        'synopsis': (movie.synopsis or 'Lista para convertirse en la portada principal de tu streaming personal.')[:150],
        'detail_url': reverse('movie_detail', args=[movie.slug]),
        'background_style': background_style,
    }


def home_view(request):
    published_movies = Movie.objects.filter(is_published=True).select_related('genre')
    query = (request.GET.get('q') or '').strip()
    selected_type = (request.GET.get('type') or '').strip()

    latest_movies = published_movies.order_by('-created_at')
    movies = latest_movies
    ranked_movies = published_movies.annotate(total_views=Coalesce(Sum('watch_sessions__views_count'), 0))

    if selected_type in ('movie', 'series'):
        movies = movies.filter(content_type=selected_type)
        ranked_movies = ranked_movies.filter(content_type=selected_type)

    if query:
        filters = Q(title__icontains=query) | Q(genre__name__icontains=query) | Q(synopsis__icontains=query)
        if query.isdigit():
            filters |= Q(release_year=int(query))
        movies = movies.filter(filters)
        ranked_movies = ranked_movies.filter(filters)

    top_trending = ranked_movies.filter(total_views__gt=0).order_by('-total_views', '-created_at')[:10]
    latest_movie = latest_movies.first()
    latest_additions = list(latest_movies[:8])

    genre_rows = []
    genre_sources = (
        movies.values('genre_id', 'genre__name')
        .annotate(total=Count('id'))
        .order_by('-total', 'genre__name')[:5]
    )
    for row in genre_sources:
        items = list(movies.filter(genre_id=row['genre_id']).order_by('-created_at')[:10])
        if items:
            genre_rows.append({'name': row['genre__name'], 'items': items})

    continue_watching = []
    if request.user.is_authenticated:
        continue_watching = (
            PlaybackProgress.objects.filter(user=request.user, progress_seconds__gt=0, completed=False)
            .select_related('movie')
            .order_by('-last_watched')[:8]
        )

    context = {
        'latest_movie_card': _build_latest_movie_card(latest_movie),
        'latest_additions': latest_additions,
        'genre_rows': genre_rows,
        'search_results': movies[:18] if query else [],
        'top_trending': top_trending,
        'continue_watching': continue_watching,
        'search_query': query,
        'results_count': movies.count() if query else None,
        'selected_type': selected_type,
    }
    return render(request, 'movies/home.html', context)


@login_required
def movie_detail_view(request, slug):
    movie = get_object_or_404(Movie.objects.select_related('genre'), slug=slug, is_published=True)
    _track_watch_session(request, movie)

    progress = PlaybackProgress.objects.filter(user=request.user, movie=movie).first()
    resume_seconds = progress.progress_seconds if progress else 0

    related_movies = (
        Movie.objects.filter(is_published=True, genre=movie.genre)
        .exclude(pk=movie.pk)
        .order_by('-created_at')[:6]
    )

    is_favorite = Favorite.objects.filter(user=request.user, movie=movie).exists()

    context = {
        'movie': movie,
        'related_movies': related_movies,
        'is_favorite': is_favorite,
        'resume_seconds': resume_seconds,
        'resume_label': _format_clock(resume_seconds),
    }
    return render(request, 'movies/movie_detail.html', context)


@login_required
def toggle_favorite_view(request, slug):
    if request.method != 'POST':
        return redirect('movie_detail', slug=slug)

    movie = get_object_or_404(Movie, slug=slug, is_published=True)
    favorite = Favorite.objects.filter(user=request.user, movie=movie)

    if favorite.exists():
        favorite.delete()
        action = 'removed'
    else:
        Favorite.objects.create(user=request.user, movie=movie)
        action = 'added'

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'action': action})

    return redirect('movie_detail', slug=slug)


@login_required
def update_progress_view(request, slug):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'invalid_method'}, status=405)

    movie = get_object_or_404(Movie, slug=slug, is_published=True)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    try:
        progress_seconds = max(0, int(float(payload.get('progress_seconds', 0))))
        duration_seconds = max(0, int(float(payload.get('duration_seconds', 0))))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'invalid_payload'}, status=400)

    completed = False
    if duration_seconds > 0 and progress_seconds >= int(duration_seconds * 0.92):
        completed = True
        progress_seconds = 0

    progress, _ = PlaybackProgress.objects.get_or_create(user=request.user, movie=movie)
    progress.progress_seconds = progress_seconds
    progress.duration_seconds = duration_seconds
    progress.completed = completed
    progress.save(update_fields=['progress_seconds', 'duration_seconds', 'completed', 'last_watched'])

    return JsonResponse({'ok': True, 'completed': completed, 'resume_label': _format_clock(progress_seconds)})
