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
from django.utils.text import slugify


DEFAULT_LOCAL_VIDEO_MAX_MB = 2048
logger = logging.getLogger(__name__)


def _ffmpeg_binary() -> str:
    return os.getenv('FFMPEG_BINARY', 'ffmpeg').strip() or 'ffmpeg'


def _ffprobe_binary() -> str:
    return os.getenv('FFPROBE_BINARY', 'ffprobe').strip() or 'ffprobe'


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
        upload_id,
        chunk_index,
        written_bytes,
        temp_path,
    )
    return temp_path


def _count_audio_streams(video_path: Path):
    command = [
        _ffprobe_binary(),
        '-v',
        'error',
        '-select_streams',
        'a',
        '-show_entries',
        'stream=index',
        '-of',
        'csv=p=0',
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        logger.info('ffprobe no esta disponible; se omite validacion de pistas de audio path=%s', video_path)
        return None
    except subprocess.CalledProcessError as exc:
        logger.error(
            'ffprobe no pudo inspeccionar pistas de audio path=%s stderr=%s',
            video_path,
            (exc.stderr or '').strip(),
        )
        return None

    return len([line for line in result.stdout.splitlines() if line.strip()])


def _public_url_for_media_path(media_path: Path) -> str:
    relative_path = media_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    return f"{settings.MEDIA_URL.rstrip('/')}/{relative_path}"


def _build_hls_output(public_url: str, movie_id=None):
    source_path = resolve_local_media_path(public_url)
    source_stem = slugify(source_path.stem if source_path else '') or 'video'
    folder_name = f'{movie_id or uuid4().hex}-{uuid4().hex[:8]}-{source_stem}'
    output_dir = get_local_hls_dir() / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist_path = output_dir / 'index.m3u8'
    playlist_url = _public_url_for_media_path(playlist_path)
    return output_dir, playlist_path, playlist_url


def _update_movie_processing_state(movie_id, *, status=None, step=None):
    if not movie_id:
        return

    Movie = apps.get_model('movies', 'Movie')
    updates = {}
    if status is not None:
        updates['status'] = status
    if step is not None:
        updates['processing_step'] = step
    if updates:
        Movie.objects.filter(pk=movie_id).update(**updates)


def _ensure_browser_compatible_audio(video_path: Path, movie_id=None) -> bool:
    _update_movie_processing_state(movie_id, step='analizando audio')
    input_audio_count = _count_audio_streams(video_path)
    processed_path = video_path.with_name(f'{video_path.stem}_processed.mp4')
    command = [
        _ffmpeg_binary(),
        '-y',
        '-nostdin',
        '-hide_banner',
        '-loglevel',
        'error',
        '-i',
        str(video_path),
        '-map',
        '0:v:0',
        '-map',
        '0:a?',
        '-c:v',
        'libx264',
        '-preset',
        os.getenv('FFMPEG_HLS_PRESET', 'veryfast').strip() or 'veryfast',
        '-crf',
        os.getenv('FFMPEG_HLS_CRF', '23').strip() or '23',
        '-profile:v',
        'main',
        '-pix_fmt',
        'yuv420p',
        '-c:a',
        'aac',
        '-b:a',
        os.getenv('FFMPEG_HLS_AUDIO_BITRATE', '128k').strip() or '128k',
        '-ac',
        '2',
        '-movflags',
        '+faststart',
        str(processed_path),
    ]

    logger.info(
        'Iniciando conversion MP4 compatible con ffmpeg input=%s output=%s',
        video_path,
        processed_path,
    )
    _update_movie_processing_state(movie_id, step='convirtiendo a mp4')

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        output_audio_count = _count_audio_streams(processed_path)
        if input_audio_count != 0 and not output_audio_count:
            logger.error(
                'ffmpeg genero un archivo sin audio; se conserva el original path=%s audio_entrada=%s stdout=%s stderr=%s',
                video_path,
                input_audio_count,
                (result.stdout or '').strip(),
                (result.stderr or '').strip(),
            )
            processed_path.unlink(missing_ok=True)
            return False
        processed_path.replace(video_path)
    except subprocess.CalledProcessError as exc:
        if processed_path.exists():
            processed_path.unlink()
        logger.error(
            'ffmpeg fallo; se conserva el archivo original path=%s stderr=%s',
            video_path,
            (exc.stderr or '').strip(),
            exc_info=True,
        )
        return False
    except Exception as exc:
        if processed_path.exists():
            processed_path.unlink()
        logger.error(
            'No se pudo convertir audio a AAC con ffmpeg; se conserva el archivo original path=%s error=%s',
            video_path,
            exc,
            exc_info=True,
        )
        return False

    logger.info(
        'Conversion ffmpeg completada y archivo reemplazado path=%s audio_entrada=%s audio_salida=%s stdout=%s stderr=%s',
        video_path,
        input_audio_count,
        output_audio_count,
        (result.stdout or '').strip(),
        (result.stderr or '').strip(),
    )
    return True


def _generate_hls_playlist(video_path: Path, public_url: str, movie_id=None):
    _update_movie_processing_state(movie_id, step='generando hls')
    output_dir, playlist_path, playlist_url = _build_hls_output(public_url, movie_id=movie_id)
    segment_pattern = output_dir / 'segment_%05d.ts'
    command = [
        _ffmpeg_binary(),
        '-y',
        '-nostdin',
        '-hide_banner',
        '-loglevel',
        'error',
        '-i',
        str(video_path),
        '-map',
        '0:v:0',
        '-map',
        '0:a?',
        '-c:v',
        'copy',
        '-c:a',
        'copy',
        '-f',
        'hls',
        '-hls_time',
        os.getenv('FFMPEG_HLS_TIME', '6').strip() or '6',
        '-hls_playlist_type',
        'vod',
        '-hls_segment_filename',
        str(segment_pattern),
        str(playlist_path),
    ]

    logger.info(
        'Iniciando generacion HLS con ffmpeg movie_id=%s input=%s playlist=%s',
        movie_id,
        video_path,
        playlist_path,
    )

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.error('ffmpeg no esta disponible; no se pudo generar HLS movie_id=%s input=%s', movie_id, video_path)
        return None
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.error(
            'ffmpeg fallo generando HLS movie_id=%s input=%s stderr=%s',
            movie_id,
            video_path,
            (exc.stderr or '').strip(),
            exc_info=True,
        )
        return None

    has_playlist = playlist_path.exists() and playlist_path.stat().st_size > 0
    has_segments = any(output_dir.glob('*.ts'))
    if not has_playlist or not has_segments:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.error(
            'HLS incompleto movie_id=%s playlist=%s has_playlist=%s has_segments=%s stdout=%s stderr=%s',
            movie_id,
            playlist_path,
            has_playlist,
            has_segments,
            (result.stdout or '').strip(),
            (result.stderr or '').strip(),
        )
        return None

    logger.info('HLS generado movie_id=%s playlist_url=%s output_dir=%s', movie_id, playlist_url, output_dir)
    return playlist_url


def _mark_movie_hls_ready(movie_id, playlist_url: str):
    if not movie_id:
        return

    Movie = apps.get_model('movies', 'Movie')
    Movie.objects.filter(pk=movie_id).update(
        video_url=playlist_url,
        status='listo',
        processing_step='hls finalizado',
    )


def procesar_video_background(public_url: str, movie_id=None) -> None:
    close_old_connections()
    try:
        _update_movie_processing_state(movie_id, status='procesando', step='recibido')
        video_path = resolve_local_media_path(public_url)
        if not video_path or not video_path.exists():
            logger.error(
                'No se pudo procesar video en background; archivo local no existe movie_id=%s public_url=%s path=%s',
                movie_id,
                public_url,
                video_path,
            )
            _update_movie_processing_state(movie_id, status='error')
            return

        if video_path.suffix.lower() == '.m3u8':
            _update_movie_processing_state(movie_id, status='listo', step='hls finalizado')
            logger.info('Video ya esta en HLS; se omite procesamiento movie_id=%s public_url=%s', movie_id, public_url)
            return

        processed_ok = _ensure_browser_compatible_audio(video_path, movie_id=movie_id)
        if not processed_ok:
            _update_movie_processing_state(movie_id, status='error')
            return

        playlist_url = _generate_hls_playlist(video_path, public_url, movie_id=movie_id)
        if not playlist_url:
            _update_movie_processing_state(movie_id, status='error')
            return

        _mark_movie_hls_ready(movie_id, playlist_url)
        if video_path.exists() and resolve_local_media_path(playlist_url) != video_path:
            video_path.unlink(missing_ok=True)
        logger.info('Procesamiento HLS finalizado movie_id=%s playlist_url=%s', movie_id, playlist_url)
    except Exception:
        logger.exception('Error inesperado procesando video en background movie_id=%s public_url=%s', movie_id, public_url)
        _update_movie_processing_state(movie_id, status='error')
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
        upload_id,
        temp_path,
        destination,
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
        getattr(uploaded_file, 'name', ''),
        written_bytes,
        destination,
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
