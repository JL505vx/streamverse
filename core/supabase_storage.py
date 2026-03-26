import mimetypes
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse
from uuid import uuid4

from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify
from supabase import ClientOptions, create_client


SUPABASE_BUCKET = 'movies'
DEFAULT_STORAGE_TIMEOUT = 600
DEFAULT_VIDEO_STORAGE_TIMEOUT = 3600


def _get_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'{name} es obligatoria para usar Supabase Storage.')
    return value


def get_supabase_storage_client():
    timeout = _get_storage_timeout()
    options = ClientOptions(storage_client_timeout=timeout)
    return create_client(_get_env('SUPABASE_URL'), _get_env('SUPABASE_KEY'), options=options).storage.from_(SUPABASE_BUCKET)


def _get_storage_timeout(*, video: bool = False) -> int:
    env_name = 'SUPABASE_VIDEO_STORAGE_TIMEOUT' if video else 'SUPABASE_STORAGE_TIMEOUT'
    fallback = DEFAULT_VIDEO_STORAGE_TIMEOUT if video else DEFAULT_STORAGE_TIMEOUT
    raw_value = os.getenv(env_name, '').strip()
    if not raw_value:
        return fallback
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ImproperlyConfigured(f'{env_name} debe ser un entero en segundos.') from exc
    if parsed <= 0:
        raise ImproperlyConfigured(f'{env_name} debe ser mayor que 0.')
    return parsed


def _safe_filename(filename: str, fallback: str) -> str:
    source = Path(filename or fallback)
    stem = slugify(source.stem) or fallback
    suffix = source.suffix.lower()
    return f'{stem}{suffix}'


def build_storage_path(folder: str, filename: str, fallback_name: str = 'archivo') -> str:
    safe_name = _safe_filename(filename, fallback_name)
    return f'movies/{folder}/{uuid4().hex[:12]}-{safe_name}'


def upload_uploaded_file(uploaded_file, *, folder: str, replace_url: str | None = None) -> str:
    storage = get_supabase_storage_client_for_folder(folder)
    remote_path = build_storage_path(folder, getattr(uploaded_file, 'name', ''), folder[:-1] if folder.endswith('s') else folder)
    content_type = getattr(uploaded_file, 'content_type', None) or mimetypes.guess_type(getattr(uploaded_file, 'name', ''))[0] or 'application/octet-stream'
    upload_source = getattr(uploaded_file, 'temporary_file_path', None)
    temp_path = None

    if callable(upload_source):
        source = upload_source()
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(getattr(uploaded_file, 'name', '')).suffix or '') as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        source = temp_path

    try:
        storage.upload(
            remote_path,
            source,
            {
                'content-type': content_type,
                'upsert': 'true',
                'cache-control': '3600',
            },
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    public_url = storage.get_public_url(remote_path)
    if replace_url:
        delete_public_file(replace_url)
    return public_url


def upload_local_file(local_path: str | Path, *, folder: str, replace_url: str | None = None) -> str:
    storage = get_supabase_storage_client_for_folder(folder)
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f'No existe el archivo local: {local_path}')

    remote_path = build_storage_path(folder, local_path.name, folder[:-1] if folder.endswith('s') else folder)
    content_type = mimetypes.guess_type(local_path.name)[0] or 'application/octet-stream'
    with local_path.open('rb') as file_obj:
        storage.upload(
            remote_path,
            file_obj,
            {
                'content-type': content_type,
                'upsert': 'true',
                'cache-control': '3600',
            },
        )

    public_url = storage.get_public_url(remote_path)
    if replace_url:
        delete_public_file(replace_url)
    return public_url


def extract_public_path(public_url: str) -> str | None:
    if not public_url:
        return None

    parsed = urlparse(public_url)
    marker = f'/storage/v1/object/public/{SUPABASE_BUCKET}/'
    if marker not in parsed.path:
        return None
    return parsed.path.split(marker, 1)[1]


def delete_public_file(public_url: str) -> None:
    relative_path = extract_public_path(public_url)
    if not relative_path:
        return
    storage = get_supabase_storage_client()
    try:
        storage.remove([relative_path])
    except Exception:
        # Si el archivo ya no existe o la URL no pertenece a este bucket, no bloqueamos el flujo.
        return


def get_supabase_storage_client_for_folder(folder: str):
    return create_client(
        _get_env('SUPABASE_URL'),
        _get_env('SUPABASE_KEY'),
        options=ClientOptions(
            storage_client_timeout=_get_storage_timeout(video=folder == 'videos')
        ),
    ).storage.from_(SUPABASE_BUCKET)
