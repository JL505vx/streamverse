import logging
import os
from pathlib import Path
import re
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify


DEFAULT_LOCAL_VIDEO_MAX_MB = 2048
logger = logging.getLogger(__name__)


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


def _build_local_video_destination(filename: str):
    safe_name = _safe_filename(filename, 'video')
    final_name = f'{uuid4().hex[:12]}-{safe_name}'
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
    if file_path and file_path.exists():
        file_path.unlink()
