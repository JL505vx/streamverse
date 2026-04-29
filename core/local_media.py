import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from uuid import uuid4

from django.conf import settings
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import close_old_connections
from django.utils import timezone
from django.utils.text import slugify


DEFAULT_LOCAL_VIDEO_MAX_MB = 2048
logger = logging.getLogger(__name__)
# HLS multi-bitrate (master.m3u8 + sub-playlists 360p/480p/720p)
PROCESSING_STAGES = {
    'upload': 10,
    'analisis': 20,
    'transcode': 40,
    'hls_360p': 60,
    'hls_480p': 75,
    'hls_720p': 90,
    'finalizado': 100,
}

HLS_RENDITIONS = [
    {
        'stage': 'hls_360p',
        'label': '360p',
        'width': 640,
        'height': 360,
        'bitrate': '800k',
        'maxrate': '900k',
        'bufsize': '1200k',
        'bandwidth': 1000000,
    },
    {
        'stage': 'hls_480p',
        'label': '480p',
        'width': 854,
        'height': 480,
        'bitrate': '1400k',
        'maxrate': '1600k',
        'bufsize': '2100k',
        'bandwidth': 1700000,
    },
    {
        'stage': 'hls_720p',
        'label': '720p',
        'width': 1280,
        'height': 720,
        'bitrate': '2800k',
        'maxrate': '3100k',
        'bufsize': '4200k',
        'bandwidth': 3300000,
    },
]


def _ffmpeg_binary() -> str:
    return os.getenv('FFMPEG_BINARY', 'ffmpeg').strip() or 'ffmpeg'


def _ffprobe_binary() -> str:
    return os.getenv('FFPROBE_BINARY', 'ffprobe').strip() or 'ffprobe'


def _select_renditions_for_height(original_height: int):
    """
    Filtra HLS_RENDITIONS para no escalar hacia arriba.
    Si la fuente es 480p, devuelve [360p, 480p] sin tocar 720p.
    """
    if not original_height or original_height <= 0:
        return list(HLS_RENDITIONS)
    selected = [r for r in HLS_RENDITIONS if r['height'] <= original_height + 30]
    return selected or [HLS_RENDITIONS[0]]


def _probe_video_resolution(video_path):
    """Devuelve (width, height) del primer stream de video usando ffprobe, o (0, 0) si falla."""
    command = [
        _ffprobe_binary(),
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0:s=x',
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        logger.info('ffprobe no disponible; no se puede detectar resolucion path=%s', video_path)
        return (0, 0)
    except subprocess.CalledProcessError as exc:
        logger.error('ffprobe fallo detectando resolucion path=%s stderr=%s', video_path, (exc.stderr or '').strip())
        return (0, 0)

    raw = (result.stdout or '').strip().splitlines()
    if not raw:
        return (0, 0)
    parts = raw[0].split('x')
    if len(parts) != 2:
        return (0, 0)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (0, 0)


def _safe_filename(filename: str, fallback: str = 'video') -> str:
    source = Path(filename or fallback)
    stem = slugify(source.stem) or fallback
    suffix = source.suffix.lower()
    return f'{stem}{suffix}'


def get_local_video_max_bytes() -> int:
    raw_value = os.getenv('LOCAL_VIDEO_UPLOAD_MAX_MB', '').strip()
    if not raw_value:
        return DEFAULT_LOCAL_VIDEO_MAX_MB * 1024 * 1024
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ImproperlyConfigured('LOCAL_VIDEO_UPLOAD_MAX_MB debe ser un entero en MB.') from exc
    if parsed <= 0:
        raise ImproperlyConfigured('LOCAL_VIDEO_UPLOAD_MAX_MB debe ser mayor que 0.')
    return parsed * 1024 * 1024


def get_local_media_prefix() -> str:
    return settings.MEDIA_URL.rstrip('/') + '/'


def get_local_videos_dir() -> Path:
    videos_dir = Path(settings.MEDIA_ROOT) / 'videos'
    videos_dir.mkdir(parents=True, exist_ok=True)
    return videos_dir


def get_local_hls_dir() -> Path:
    hls_dir = get_local_videos_dir() / 'hls'
    hls_dir.mkdir(parents=True, exist_ok=True)
    return hls_dir


def _build_local_video_destination(filename: str):
    safe_name = _safe_filename(filename, 'video')
    safe_stem = Path(safe_name).stem or 'video'
    final_name = f'{uuid4().hex[:12]}-{safe_stem}.mp4'
    destination = get_local_videos_dir() / final_name
    public_url = f"{settings.MEDIA_URL.rstrip('/')}/videos/{final_name}"
    return destination, public_url


def resolve_local_media_path(public_url: str):
    if not public_url:
        return None
    media_prefix = get_local_media_prefix()
    if not public_url.startswith(media_prefix):
        return None
    relative_path = public_url[len(media_prefix):].lstrip('/')
    return Path(settings.MEDIA_ROOT) / relative_path


def is_local_media_url(public_url: str) -> bool:
    return resolve_local_media_path(public_url) is not None


def local_media_exists(public_url: str) -> bool:
    file_path = resolve_local_media_path(public_url)
    return bool(file_path and file_path.exists())


def get_chunk_uploads_dir() -> Path:
    chunk_dir = Path(settings.MEDIA_ROOT) / '.chunk_uploads'
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir


def _normalize_upload_id(upload_id: str) -> str:
    normalized = re.sub(r'[^a-zA-Z0-9_-]', '', (upload_id or '').strip())
    return normalized or uuid4().hex


def get_chunk_upload_temp_path(upload_id: str, filename: str) -> Path:
    safe_upload_id = _normalize_upload_id(upload_id)
    suffix = Path(filename or 'video').suffix.lower() or '.part'
    return get_chunk_uploads_dir() / f'{safe_upload_id}{suffix}.part'


def append_chunk_to_upload(upload_id: str, filename: str, uploaded_chunk, chunk_index: int) -> Path:
    chunk_index = max(int(chunk_index or 0), 0)
    temp_path = get_chunk_upload_temp_path(upload_id, filename)
    if chunk_index > 0 and not temp_path.exists():
        raise FileNotFoundError('No existe una carga temporal activa para continuar.')

    mode = 'wb' if chunk_index == 0 else 'ab'
    written_bytes = 0
    with temp_path.open(mode) as output:
        for piece in uploaded_chunk.chunks():
            written_bytes += len(piece)
            output.write(piece)

    logger.info(
        'Chunk recibido upload_id=%s chunk=%s bytes=%s temporal=%s',
        upload_id, chunk_index, written_bytes, temp_path,
    )
    return temp_path


def _count_audio_streams(video_path):
    command = [
        _ffprobe_binary(),
        '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=index',
        '-of', 'csv=p=0',
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        logger.info('ffprobe no esta disponible; se omite validacion de pistas de audio path=%s', video_path)
        return None
    except subprocess.CalledProcessError as exc:
        logger.error('ffprobe no pudo inspeccionar pistas de audio path=%s stderr=%s', video_path, (exc.stderr or '').strip())
        return None

    return len([line for line in result.stdout.splitlines() if line.strip()])


def _public_url_for_media_path(media_path):
    relative_path = media_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    return f"{settings.MEDIA_URL.rstrip('/')}/{relative_path}"


def _build_hls_output(movie_id=None):
    folder_name = str(movie_id) if movie_id else uuid4().hex
    output_dir = get_local_hls_dir() / folder_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist_path = output_dir / 'master.m3u8'
    playlist_url = _public_url_for_media_path(playlist_path)
    return output_dir, playlist_path, playlist_url


def _update_movie_processing_state(
    movie_id, *, status=None, step=None, stage=None, progress=None,
    started_at=None, finished_at=None, clear_finished_at=False,
    error_message=None, clear_error=False,
):
    if not movie_id:
        return

    Movie = apps.get_model('movies', 'Movie')
    updates = {}
    if status is not None:
        updates['status'] = status
    if step is not None:
        updates['processing_step'] = step
    if stage is not None:
        updates['processing_stage'] = stage
        if progress is None and stage in PROCESSING_STAGES:
            updates['processing_progress'] = PROCESSING_STAGES[stage]
    if progress is not None:
        updates['processing_progress'] = max(0, min(100, int(progress)))
    if started_at is not None:
        updates['processing_started_at'] = started_at
    if finished_at is not None:
        updates['processing_finished_at'] = finished_at
    elif clear_finished_at:
        updates['processing_finished_at'] = None
    if error_message is not None:
        updates['error_message'] = str(error_message)
    elif clear_error:
        updates['error_message'] = ''
    if updates:
        Movie.objects.filter(pk=movie_id).update(**updates)


def _ensure_browser_compatible_audio(video_path, movie_id=None) -> bool:
    _update_movie_processing_state(movie_id, step='analizando audio', stage='analisis')
    input_audio_count = _count_audio_streams(video_path)
    processed_path = video_path.with_name(f'{video_path.stem}_processed.mp4')
    command = [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'error',
        '-i', str(video_path),
        '-map', '0:v:0',
        '-map', '0:a?',
        '-c:v', 'libx264',
        '-preset', os.getenv('FFMPEG_HLS_PRESET', 'veryfast').strip() or 'veryfast',
        '-crf', os.getenv('FFMPEG_HLS_CRF', '23').strip() or '23',
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', os.getenv('FFMPEG_HLS_AUDIO_BITRATE', '128k').strip() or '128k',
        '-ac', '2',
        '-movflags', '+faststart',
        str(processed_path),
    ]

    logger.info('Iniciando conversion MP4 compatible con ffmpeg input=%s output=%s', video_path, processed_path)
    _update_movie_processing_state(movie_id, step='convirtiendo a mp4', stage='transcode')

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        output_audio_count = _count_audio_streams(processed_path)
        if input_audio_count != 0 and not output_audio_count:
            logger.error(
                'ffmpeg genero un archivo sin audio; se conserva el original path=%s audio_entrada=%s stdout=%s stderr=%s',
                video_path, input_audio_count, (result.stdout or '').strip(), (result.stderr or '').strip(),
            )
            processed_path.unlink(missing_ok=True)
            return False
        processed_path.replace(video_path)
    except subprocess.CalledProcessError as exc:
        if processed_path.exists():
            processed_path.unlink()
        logger.error('ffmpeg fallo; se conserva el archivo original path=%s stderr=%s', video_path, (exc.stderr or '').strip(), exc_info=True)
        return False
    except Exception as exc:
        if processed_path.exists():
            processed_path.unlink()
        logger.error('No se pudo convertir audio a AAC con ffmpeg; se conserva el archivo original path=%s error=%s', video_path, exc, exc_info=True)
        return False

    logger.info(
        'Conversion ffmpeg completada y archivo reemplazado path=%s audio_entrada=%s audio_salida=%s stdout=%s stderr=%s',
        video_path, input_audio_count, output_audio_count, (result.stdout or '').strip(), (result.stderr or '').strip(),
    )
    return True


def _write_master_playlist(master_path, renditions=None):
    """Escribe el master.m3u8 con multiples #EXT-X-STREAM-INF."""
    if renditions is None:
        renditions = HLS_RENDITIONS
    lines = ['#EXTM3U', '#EXT-X-VERSION:3']
    for rendition in renditions:
        lines.append(
            '#EXT-X-STREAM-INF:'
            f'BANDWIDTH={rendition["bandwidth"]},'
            f'RESOLUTION={rendition["width"]}x{rendition["height"]},'
            f'NAME="{rendition["label"]}",'
            'CODECS="avc1.4d401f,mp4a.40.2"'
        )
        lines.append(f'{rendition["label"]}/index.m3u8')
    master_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _generate_hls_rendition(video_path, output_dir, rendition: dict, movie_id=None) -> bool:
    label = rendition['label']
    rendition_dir = output_dir / label
    rendition_dir.mkdir(parents=True, exist_ok=True)
    playlist_path = rendition_dir / 'index.m3u8'
    segment_pattern = rendition_dir / 'segment_%03d.ts'
    scale_filter = (
        f'scale=w={rendition["width"]}:h={rendition["height"]}:force_original_aspect_ratio=decrease,'
        f'pad={rendition["width"]}:{rendition["height"]}:(ow-iw)/2:(oh-ih)/2'
    )
    command = [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'error',
        '-i', str(video_path),
        '-map', '0:v:0',
        '-map', '0:a?',
        '-c:v', 'libx264',
        '-preset', os.getenv('FFMPEG_HLS_PRESET', 'veryfast').strip() or 'veryfast',
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p',
        '-vf', scale_filter,
        '-b:v', rendition['bitrate'],
        '-maxrate', rendition['maxrate'],
        '-bufsize', rendition['bufsize'],
        '-g', '48',
        '-keyint_min', '48',
        '-sc_threshold', '0',
        '-c:a', 'aac',
        '-b:a', os.getenv('FFMPEG_HLS_AUDIO_BITRATE', '128k').strip() or '128k',
        '-ac', '2',
        '-f', 'hls',
        '-hls_time', os.getenv('FFMPEG_HLS_TIME', '6').strip() or '6',
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', str(segment_pattern),
        str(playlist_path),
    ]

    logger.info('Iniciando rendicion HLS %s movie_id=%s input=%s playlist=%s', label, movie_id, video_path, playlist_path)

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        logger.error('ffmpeg no esta disponible; no se pudo generar HLS movie_id=%s input=%s', movie_id, video_path)
        return False
    except subprocess.CalledProcessError as exc:
        logger.error('ffmpeg fallo generando HLS %s movie_id=%s input=%s stderr=%s', label, movie_id, video_path, (exc.stderr or '').strip(), exc_info=True)
        return False

    has_playlist = playlist_path.exists() and playlist_path.stat().st_size > 0
    has_segments = any(rendition_dir.glob('*.ts'))
    if not has_playlist or not has_segments:
        logger.error(
            'HLS incompleto %s movie_id=%s playlist=%s has_playlist=%s has_segments=%s stdout=%s stderr=%s',
            label, movie_id, playlist_path, has_playlist, has_segments, (result.stdout or '').strip(), (result.stderr or '').strip(),
        )
        return False

    logger.info('Rendicion HLS generada movie_id=%s label=%s output_dir=%s', movie_id, label, rendition_dir)
    return True


def _generate_hls_playlist(video_path, movie_id=None, renditions=None):
    """Genera HLS multi-bitrate. Devuelve dict {'playlist_url', 'renditions'} o None."""
    if renditions is None:
        renditions = list(HLS_RENDITIONS)
    if not renditions:
        logger.error('No hay renditions para generar HLS movie_id=%s', movie_id)
        return None

    output_dir, playlist_path, playlist_url = _build_hls_output(movie_id=movie_id)

    for rendition in renditions:
        _update_movie_processing_state(
            movie_id, step=f'generando hls {rendition["label"]}', stage=rendition['stage'],
        )
        if not _generate_hls_rendition(video_path, output_dir, rendition, movie_id=movie_id):
            shutil.rmtree(output_dir, ignore_errors=True)
            return None

    _write_master_playlist(playlist_path, renditions=renditions)
    has_master = playlist_path.exists() and playlist_path.stat().st_size > 0
    has_playlists = all((output_dir / r['label'] / 'index.m3u8').exists() for r in renditions)
    if not has_master or not has_playlists:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.error('Master HLS incompleto movie_id=%s master=%s', movie_id, playlist_path)
        return None

    logger.info(
        'HLS multi-bitrate generado movie_id=%s playlist_url=%s output_dir=%s renditions=%s',
        movie_id, playlist_url, output_dir, [r['label'] for r in renditions],
    )
    return {'playlist_url': playlist_url, 'renditions': renditions}


def _mark_movie_hls_ready(movie_id, playlist_url: str, renditions=None, original_size=None):
    """Marca la pelicula como lista y guarda metadata HLS (calidades, original)."""
    if not movie_id:
        return

    Movie = apps.get_model('movies', 'Movie')
    updates = {
        'video_url': playlist_url,
        'status': 'listo',
        'processing_step': 'hls finalizado',
        'processing_stage': 'finalizado',
        'processing_progress': PROCESSING_STAGES['finalizado'],
        'processing_finished_at': timezone.now(),
        'error_message': '',
    }
    if renditions:
        labels = [r['label'] for r in renditions]
        updates['video_available_qualities'] = ','.join(labels)
        updates['video_default_quality'] = labels[-1]
    if original_size:
        width, height = original_size
        if width:
            updates['video_original_width'] = int(width)
        if height:
            updates['video_original_height'] = int(height)
    Movie.objects.filter(pk=movie_id).update(**updates)


def procesar_video_background(public_url: str, movie_id=None) -> None:
    close_old_connections()
    try:
        _update_movie_processing_state(
            movie_id, status='procesando', step='recibido', stage='upload',
            started_at=timezone.now(), clear_finished_at=True, clear_error=True,
        )
        video_path = resolve_local_media_path(public_url)
        if not video_path or not video_path.exists():
            error = f'Archivo local no existe: {public_url}'
            logger.error(
                'No se pudo procesar video en background; archivo local no existe movie_id=%s public_url=%s path=%s',
                movie_id, public_url, video_path,
            )
            _update_movie_processing_state(
                movie_id, status='error', step='error', stage='error',
                progress=0, finished_at=timezone.now(), error_message=error,
            )
            return

        if video_path.suffix.lower() == '.m3u8':
            _update_movie_processing_state(
                movie_id, status='listo', step='hls finalizado', stage='finalizado',
                finished_at=timezone.now(), clear_error=True,
            )
            logger.info('Video ya esta en HLS; se omite procesamiento movie_id=%s public_url=%s', movie_id, public_url)
            return

        processed_ok = _ensure_browser_compatible_audio(video_path, movie_id=movie_id)
        if not processed_ok:
            _update_movie_processing_state(
                movie_id, status='error', step='error', stage='error',
                progress=0, finished_at=timezone.now(),
                error_message='No se pudo convertir el video a MP4 compatible.',
            )
            return

        # Detectar resolucion original tras la normalizacion: asi sabemos que calidades
        # tiene sentido generar (no escalar 480p a 720p innecesariamente).
        original_size = _probe_video_resolution(video_path)
        original_height = original_size[1] if original_size else 0
        renditions = _select_renditions_for_height(original_height)
        logger.info(
            'Resolucion original detectada movie_id=%s width=%s height=%s renditions=%s',
            movie_id,
            original_size[0] if original_size else 0,
            original_height,
            [r['label'] for r in renditions],
        )

        result = _generate_hls_playlist(video_path, movie_id=movie_id, renditions=renditions)
        if not result:
            _update_movie_processing_state(
                movie_id, status='error', step='error', stage='error',
                progress=0, finished_at=timezone.now(),
                error_message='No se pudo generar HLS para el video.',
            )
            return

        playlist_url = result['playlist_url']
        used_renditions = result['renditions']
        _mark_movie_hls_ready(
            movie_id, playlist_url,
            renditions=used_renditions, original_size=original_size,
        )
        if video_path.exists() and resolve_local_media_path(playlist_url) != video_path:
            video_path.unlink(missing_ok=True)
        logger.info(
            'Procesamiento HLS finalizado movie_id=%s playlist_url=%s qualities=%s',
            movie_id, playlist_url, ','.join(r['label'] for r in used_renditions),
        )
    except Exception as exc:
        logger.exception('Error inesperado procesando video en background movie_id=%s public_url=%s', movie_id, public_url)
        _update_movie_processing_state(
            movie_id, status='error', step='error', stage='error',
            progress=0, finished_at=timezone.now(), error_message=str(exc),
        )
    finally:
        close_old_connections()


def start_video_processing_background(public_url: str, movie_id=None) -> None:
    thread = threading.Thread(
        target=procesar_video_background,
        args=(public_url, movie_id),
        daemon=True,
        name=f'video-processing-{movie_id or "pending"}',
    )
    thread.start()


def finalize_chunk_upload(upload_id: str, filename: str) -> str:
    temp_path = get_chunk_upload_temp_path(upload_id, filename)
    if not temp_path.exists():
        raise FileNotFoundError('No existe el archivo temporal para finalizar la carga.')

    destination, public_url = _build_local_video_destination(filename)
    temp_path.replace(destination)
    logger.info(
        'Video ensamblado desde chunks upload_id=%s origen=%s destino=%s',
        upload_id, temp_path, destination,
    )
    return public_url


def save_uploaded_video_locally(uploaded_file) -> str:
    destination, public_url = _build_local_video_destination(getattr(uploaded_file, 'name', ''))

    written_bytes = 0
    with destination.open('wb+') as output:
        for chunk in uploaded_file.chunks():
            written_bytes += len(chunk)
            output.write(chunk)

    logger.info(
        'Video guardado localmente nombre=%s bytes=%s destino=%s',
        getattr(uploaded_file, 'name', ''), written_bytes, destination,
    )

    return public_url


def delete_local_video(public_url: str) -> None:
    file_path = resolve_local_media_path(public_url)
    if not file_path or not file_path.exists():
        return
    hls_root = get_local_hls_dir().resolve()
    resolved_path = file_path.resolve()
    if file_path.suffix.lower() == '.m3u8':
        parent_dir = resolved_path.parent
        if hls_root in parent_dir.parents or parent_dir == hls_root:
            shutil.rmtree(parent_dir, ignore_errors=True)
            return
    file_path.unlink()
