import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify


DEFAULT_LOCAL_VIDEO_MAX_MB = 2048


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


def save_uploaded_video_locally(uploaded_file) -> str:
    videos_dir = Path(settings.MEDIA_ROOT) / 'videos'
    videos_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(getattr(uploaded_file, 'name', ''), 'video')
    filename = f'{uuid4().hex[:12]}-{safe_name}'
    destination = videos_dir / filename

    with destination.open('wb+') as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)

    return f"{settings.MEDIA_URL.rstrip('/')}/videos/{filename}"


def delete_local_video(public_url: str) -> None:
    if not public_url:
        return
    media_prefix = settings.MEDIA_URL.rstrip('/') + '/'
    if not public_url.startswith(media_prefix):
        return
    relative_path = public_url[len(media_prefix):].lstrip('/')
    file_path = Path(settings.MEDIA_ROOT) / relative_path
    if file_path.exists():
        file_path.unlink()

