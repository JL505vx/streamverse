import logging
import os
from pathlib import Path
import json
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
    'thumbnails': 95,
    'finalizado': 100,
}

THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 90
THUMBNAIL_COLUMNS = 5
THUMBNAIL_INTERVAL_SECONDS = 10

HLS_RENDITIONS = [
    {
        'stage': 'hls_360p',
        'label': '360p',
        'width': 640,
        'height': 360,
        'bitrate': '600k',
        'maxrate': '700k',
        'bufsize': '1000k',
        'bandwidth': 800000,
    },
    {
        'stage': 'hls_480p',
        'label': '480p',
        'width': 854,
        'height': 480,
        'bitrate': '1000k',
        'maxrate': '1200k',
        'bufsize': '1500k',
        'bandwidth': 1300000,
    },
    {
        'stage': 'hls_720p',
        'label': '720p',
        'width': 1280,
        'height': 720,
        'bitrate': '2500k',
        'maxrate': '2800k',
        'bufsize': '4000k',
        'bandwidth': 3000000,
    },
]


def _ffmpeg_binary() -> str:
    return os.getenv('FFMPEG_BINARY', 'ffmpeg').strip() or 'ffmpeg'


def _ffprobe_binary() -> str:
    return os.getenv('FFPROBE_BINARY', 'ffprobe').strip() or 'ffprobe'


def _ffmpeg_preset() -> str:
    return os.getenv('FFMPEG_HLS_PRESET', 'superfast').strip() or 'superfast'


def _ffmpeg_crf() -> str:
    return os.getenv('FFMPEG_HLS_CRF', '23').strip() or '23'


def _ffmpeg_threads() -> str:
    return os.getenv('FFMPEG_THREADS', '0').strip() or '0'


def _ffmpeg_audio_bitrate() -> str:
    return os.getenv('FFMPEG_HLS_AUDIO_BITRATE', '128k').strip() or '128k'


def _ffmpeg_browser_audio_bitrate() -> str:
    return os.getenv('FFMPEG_BROWSER_AUDIO_BITRATE', '192k').strip() or '192k'


def _ffmpeg_hls_time() -> str:
    return os.getenv('FFMPEG_HLS_TIME', '5').strip() or '5'


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


def _probe_video_duration(video_path):
    command = [
        _ffprobe_binary(),
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return max(0.0, float((result.stdout or '').strip() or 0))
    except FileNotFoundError:
        logger.info('ffprobe no disponible; no se puede detectar duracion path=%s', video_path)
    except (subprocess.CalledProcessError, ValueError) as exc:
        logger.error('ffprobe fallo detectando duracion path=%s error=%s', video_path, exc)
    return 0.0


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


def get_local_thumbnails_dir() -> Path:
    thumbnails_dir = Path(settings.MEDIA_ROOT) / 'thumbnails'
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    return thumbnails_dir


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


def _probe_media_streams(video_path):
    command = [
        _ffprobe_binary(),
        '-v', 'error',
        '-show_streams',
        '-print_format', 'json',
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout or '{}')
        return payload.get('streams') or []
    except FileNotFoundError:
        logger.info('ffprobe no esta disponible; no se puede inspeccionar codecs path=%s', video_path)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        logger.error('ffprobe fallo inspeccionando codecs path=%s error=%s', video_path, exc)
    return []


def _stream_language(stream):
    tags = stream.get('tags') or {}
    return str(tags.get('language') or tags.get('LANGUAGE') or '').strip().lower()


def _select_browser_audio_stream(streams):
    audio_streams = [stream for stream in streams if stream.get('codec_type') == 'audio']
    if not audio_streams:
        return None
    spanish_codes = {'spa', 'es', 'esp', 'spanish', 'es-mx', 'es-es'}
    for stream in audio_streams:
        if _stream_language(stream) in spanish_codes:
            return stream
    return audio_streams[0]


def _browser_fixed_video_path(video_path):
    suffix = video_path.suffix.lower()
    if video_path.stem.endswith('_fix') and suffix == '.mp4':
        return video_path
    return video_path.with_name(f'{video_path.stem}_fix.mp4')


def _public_url_for_existing_local_media_path(media_path):
    try:
        return _public_url_for_media_path(media_path)
    except ValueError:
        return ''


def _build_mp4_transcode_command(input_path, output_path):
    return [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'error',
        '-threads', _ffmpeg_threads(),
        '-i', str(input_path),
        '-map', '0:v:0',
        '-map', '0:a?',
        '-c:v', 'libx264',
        '-preset', _ffmpeg_preset(),
        '-crf', _ffmpeg_crf(),
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', _ffmpeg_browser_audio_bitrate(),
        '-ac', '2',
        '-movflags', '+faststart',
        str(output_path),
    ]


def _build_browser_audio_fix_command(input_path, output_path, audio_stream=None):
    audio_index = audio_stream.get('index') if audio_stream else None
    audio_map = f'0:{audio_index}' if audio_index is not None else '0:a:0?'
    return [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'info',
        '-threads', _ffmpeg_threads(),
        '-i', str(input_path),
        '-map', '0:v:0',
        '-map', audio_map,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-b:a', _ffmpeg_browser_audio_bitrate(),
        '-ac', '2',
        '-movflags', '+faststart',
        str(output_path),
    ]


def _build_hls_filter_complex(renditions):
    if len(renditions) == 1:
        rendition = renditions[0]
        return (
            f'[0:v]scale=w={rendition["width"]}:h={rendition["height"]}:force_original_aspect_ratio=decrease,'
            f'pad={rendition["width"]}:{rendition["height"]}:(ow-iw)/2:(oh-ih)/2,'
            'setsar=1[v0]'
        )

    split_outputs = ''.join(f'[v{i}in]' for i, _ in enumerate(renditions))
    filters = [f'[0:v]split={len(renditions)}{split_outputs}']
    for index, rendition in enumerate(renditions):
        filters.append(
            f'[v{index}in]'
            f'scale=w={rendition["width"]}:h={rendition["height"]}:force_original_aspect_ratio=decrease,'
            f'pad={rendition["width"]}:{rendition["height"]}:(ow-iw)/2:(oh-ih)/2,'
            'setsar=1'
            f'[v{index}]'
        )
    return ';'.join(filters)


def _build_multibitrate_hls_command(video_path, output_dir, renditions, has_audio=True):
    command = [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'error',
        '-threads', _ffmpeg_threads(),
        '-i', str(video_path),
        '-filter_complex', _build_hls_filter_complex(renditions),
    ]

    for index, _rendition in enumerate(renditions):
        command.extend(['-map', f'[v{index}]'])
        if has_audio:
            command.extend(['-map', '0:a:0'])

    for index, rendition in enumerate(renditions):
        command.extend([
            f'-c:v:{index}', 'libx264',
            f'-preset:v:{index}', _ffmpeg_preset(),
            f'-crf:v:{index}', _ffmpeg_crf(),
            f'-profile:v:{index}', 'main',
            f'-pix_fmt:v:{index}', 'yuv420p',
            f'-b:v:{index}', rendition['bitrate'],
            f'-maxrate:v:{index}', rendition['maxrate'],
            f'-bufsize:v:{index}', rendition['bufsize'],
            f'-g:v:{index}', '120',
            f'-keyint_min:v:{index}', '120',
            f'-sc_threshold:v:{index}', '0',
        ])

    if has_audio:
        for index, _rendition in enumerate(renditions):
            command.extend([
                f'-c:a:{index}', 'aac',
                f'-b:a:{index}', _ffmpeg_audio_bitrate(),
                f'-ac:a:{index}', '2',
            ])

    variant_map = []
    for index, rendition in enumerate(renditions):
        if has_audio:
            variant_map.append(f'v:{index},a:{index},name:{rendition["label"]}')
        else:
            variant_map.append(f'v:{index},name:{rendition["label"]}')

    command.extend([
        '-f', 'hls',
        '-hls_time', _ffmpeg_hls_time(),
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', str(output_dir / '%v' / 'segment_%03d.ts'),
        '-master_pl_name', 'master.m3u8',
        '-var_stream_map', ' '.join(variant_map),
        str(output_dir / '%v' / 'index.m3u8'),
    ])
    return command


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


def _build_thumbnail_output(movie_id=None, *, clear_existing=True):
    folder_name = str(movie_id) if movie_id else uuid4().hex
    output_dir = get_local_thumbnails_dir() / folder_name
    if clear_existing and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sprite_path = output_dir / 'sprite.jpg'
    vtt_path = output_dir / 'preview.vtt'
    return {
        'output_dir': output_dir,
        'sprite_path': sprite_path,
        'vtt_path': vtt_path,
        'sprite_url': _public_url_for_media_path(sprite_path),
        'vtt_url': _public_url_for_media_path(vtt_path),
    }


def _thumbnail_output_is_complete(output):
    return (
        output['sprite_path'].exists()
        and output['sprite_path'].stat().st_size > 0
        and output['vtt_path'].exists()
        and output['vtt_path'].stat().st_size > 0
    )


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


def _save_movie_video_url(movie_id, video_path):
    if not movie_id:
        return
    public_url = _public_url_for_existing_local_media_path(video_path)
    if public_url:
        Movie = apps.get_model('movies', 'Movie')
        Movie.objects.filter(pk=movie_id).update(video_url=public_url)


def process_video(video_path, movie_id=None):
    """
    Normaliza un archivo local para navegador sin bloquear la request.
    Devuelve el Path usable o None si ffmpeg/ffprobe fallan.
    """
    video_path = Path(video_path)
    if video_path.suffix.lower() == '.m3u8':
        logger.info('Archivo HLS detectado; se omite normalizacion browser movie_id=%s path=%s', movie_id, video_path)
        return video_path

    _update_movie_processing_state(movie_id, step='analizando audio', stage='analisis')
    streams = _probe_media_streams(video_path)
    if not streams:
        logger.error('No se pudo analizar video para compatibilidad browser movie_id=%s path=%s', movie_id, video_path)
        return None

    video_stream = next((stream for stream in streams if stream.get('codec_type') == 'video'), None)
    audio_stream = _select_browser_audio_stream(streams)
    video_codec = str((video_stream or {}).get('codec_name') or '').lower()
    audio_codec = str((audio_stream or {}).get('codec_name') or '').lower()
    fixed_path = _browser_fixed_video_path(video_path)

    if video_codec in {'h264', 'avc1'} and (not audio_stream or audio_codec == 'aac') and video_path.suffix.lower() == '.mp4':
        logger.info(
            'Video compatible con navegador; se omite conversion movie_id=%s path=%s video=%s audio=%s',
            movie_id, video_path, video_codec, audio_codec or 'sin_audio',
        )
        return video_path

    if fixed_path.exists() and fixed_path.stat().st_size > 0:
        logger.info(
            'Conversion browser ya existe; se reutiliza movie_id=%s input=%s output=%s',
            movie_id, video_path, fixed_path,
        )
        _save_movie_video_url(movie_id, fixed_path)
        return fixed_path

    if video_codec in {'h264', 'avc1'}:
        command = _build_browser_audio_fix_command(video_path, fixed_path, audio_stream=audio_stream)
        conversion_label = 'audio a AAC con video copy'
    else:
        command = _build_mp4_transcode_command(video_path, fixed_path)
        conversion_label = 'video/audio a MP4 compatible'

    logger.info(
        'Inicio conversion browser movie_id=%s tipo=%s input=%s output=%s video=%s audio=%s lang=%s',
        movie_id, conversion_label, video_path, fixed_path, video_codec or 'desconocido',
        audio_codec or 'sin_audio', _stream_language(audio_stream or {}) or 'desconocido',
    )
    logger.info('Progreso conversion browser movie_id=%s estado=iniciado output=%s', movie_id, fixed_path)
    _update_movie_processing_state(movie_id, step='convirtiendo a mp4 compatible', stage='transcode')

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        input_audio_count = len([s for s in streams if s.get('codec_type') == 'audio'])
        output_audio_count = _count_audio_streams(fixed_path)
        if input_audio_count != 0 and not output_audio_count:
            logger.error(
                'ffmpeg genero un archivo sin audio; se conserva el original path=%s audio_entrada=%s stdout=%s stderr=%s',
                video_path, input_audio_count, (result.stdout or '').strip(), (result.stderr or '').strip(),
            )
            fixed_path.unlink(missing_ok=True)
            return None
    except subprocess.CalledProcessError as exc:
        if fixed_path.exists():
            fixed_path.unlink()
        logger.error(
            'ffmpeg fallo en conversion browser movie_id=%s input=%s stderr=%s',
            movie_id, video_path, (exc.stderr or '').strip(), exc_info=True,
        )
        return None
    except FileNotFoundError:
        logger.error('ffmpeg no esta disponible para conversion browser movie_id=%s input=%s', movie_id, video_path)
        return None
    except Exception as exc:
        if fixed_path.exists():
            fixed_path.unlink()
        logger.error('No se pudo convertir video browser movie_id=%s path=%s error=%s', movie_id, video_path, exc, exc_info=True)
        return None

    logger.info(
        'Terminado conversion browser movie_id=%s output=%s audio_salida=%s stdout=%s stderr=%s',
        movie_id, fixed_path, output_audio_count, (result.stdout or '').strip(), (result.stderr or '').strip(),
    )
    _save_movie_video_url(movie_id, fixed_path)
    return fixed_path


def _ensure_browser_compatible_audio(video_path, movie_id=None) -> bool:
    return process_video(video_path, movie_id=movie_id) is not None


def _generate_hls_playlist(video_path, movie_id=None, renditions=None):
    """Genera HLS multi-bitrate en un solo proceso ffmpeg."""
    if renditions is None:
        renditions = list(HLS_RENDITIONS)
    if not renditions:
        logger.error('No hay renditions para generar HLS movie_id=%s', movie_id)
        return None

    output_dir, playlist_path, playlist_url = _build_hls_output(movie_id=movie_id)
    audio_count = _count_audio_streams(video_path)
    has_audio = audio_count != 0
    first_stage = renditions[0]['stage']
    labels = ', '.join(r['label'] for r in renditions)
    _update_movie_processing_state(movie_id, step=f'generando hls {labels}', stage=first_stage)
    command = _build_multibitrate_hls_command(video_path, output_dir, renditions, has_audio=has_audio)

    logger.info(
        'Iniciando HLS multi-bitrate en un proceso movie_id=%s input=%s output_dir=%s renditions=%s audio=%s',
        movie_id, video_path, output_dir, [r['label'] for r in renditions], has_audio,
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
            'ffmpeg fallo generando HLS multi-bitrate movie_id=%s input=%s stderr=%s',
            movie_id, video_path, (exc.stderr or '').strip(), exc_info=True,
        )
        return None

    for rendition in renditions[1:]:
        _update_movie_processing_state(
            movie_id, step=f'hls {rendition["label"]} generado', stage=rendition['stage'],
        )

    has_master = playlist_path.exists() and playlist_path.stat().st_size > 0
    missing_outputs = [
        r['label'] for r in renditions
        if not (output_dir / r['label'] / 'index.m3u8').exists()
        or not any((output_dir / r['label']).glob('*.ts'))
    ]
    if not has_master or missing_outputs:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.error(
            'HLS multi-bitrate incompleto movie_id=%s master=%s missing=%s stdout=%s stderr=%s',
            movie_id, playlist_path, missing_outputs, (result.stdout or '').strip(), (result.stderr or '').strip(),
        )
        return None

    logger.info(
        'HLS multi-bitrate generado movie_id=%s playlist_url=%s output_dir=%s renditions=%s',
        movie_id, playlist_url, output_dir, [r['label'] for r in renditions],
    )
    return {'playlist_url': playlist_url, 'renditions': renditions}


def _format_vtt_timestamp(seconds):
    milliseconds = int(round(max(0.0, float(seconds or 0)) * 1000))
    hours, remainder = divmod(milliseconds, 3600 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    secs, millis = divmod(remainder, 1000)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}'


def _write_thumbnail_vtt(vtt_path, *, sprite_filename, duration, interval, total_thumbnails):
    lines = ['WEBVTT', '']
    safe_duration = max(float(duration or 0), float(interval or THUMBNAIL_INTERVAL_SECONDS))
    for index in range(total_thumbnails):
        start = index * interval
        end = min(start + interval, safe_duration)
        if end <= start:
            end = start + interval
        column = index % THUMBNAIL_COLUMNS
        row = index // THUMBNAIL_COLUMNS
        x = column * THUMBNAIL_WIDTH
        y = row * THUMBNAIL_HEIGHT
        lines.append(f'{_format_vtt_timestamp(start)} --> {_format_vtt_timestamp(end)}')
        lines.append(f'{sprite_filename}#xywh={x},{y},{THUMBNAIL_WIDTH},{THUMBNAIL_HEIGHT}')
        lines.append('')
    vtt_path.write_text('\n'.join(lines), encoding='utf-8')


def _generate_thumbnail_previews(video_path, movie_id=None, interval=THUMBNAIL_INTERVAL_SECONDS, *, force=False):
    interval = max(int(interval or THUMBNAIL_INTERVAL_SECONDS), 1)
    output = _build_thumbnail_output(movie_id=movie_id, clear_existing=False)
    if not force and _thumbnail_output_is_complete(output):
        logger.info(
            'Thumbnails ya existentes; se omite regeneracion movie_id=%s sprite=%s vtt=%s',
            movie_id, output['sprite_path'], output['vtt_path'],
        )
        return {
            'sprite_url': output['sprite_url'],
            'vtt_url': output['vtt_url'],
            'interval': interval,
        }

    if output['output_dir'].exists():
        shutil.rmtree(output['output_dir'], ignore_errors=True)
    _update_movie_processing_state(movie_id, step='generando thumbnails', stage='thumbnails')
    output = _build_thumbnail_output(movie_id=movie_id)
    duration = _probe_video_duration(video_path)
    total_thumbnails = max(1, int((duration + interval - 0.001) // interval) if duration else 1)
    rows = max(1, (total_thumbnails + THUMBNAIL_COLUMNS - 1) // THUMBNAIL_COLUMNS)
    tile_filter = (
        f'fps=1/{interval},'
        f'scale={THUMBNAIL_WIDTH}:{THUMBNAIL_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={THUMBNAIL_WIDTH}:{THUMBNAIL_HEIGHT}:(ow-iw)/2:(oh-ih)/2,'
        f'tile={THUMBNAIL_COLUMNS}x{rows}'
    )
    command = [
        _ffmpeg_binary(),
        '-y', '-nostdin', '-hide_banner',
        '-loglevel', 'error',
        '-threads', _ffmpeg_threads(),
        '-i', str(video_path),
        '-an',
        '-vf', tile_filter,
        '-frames:v', '1',
        '-q:v', '4',
        str(output['sprite_path']),
    ]

    logger.info(
        'Generando thumbnails movie_id=%s input=%s sprite=%s interval=%ss total=%s grid=%sx%s',
        movie_id, video_path, output['sprite_path'], interval, total_thumbnails, THUMBNAIL_COLUMNS, rows,
    )
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        shutil.rmtree(output['output_dir'], ignore_errors=True)
        logger.error('ffmpeg no esta disponible; no se pudieron generar thumbnails movie_id=%s input=%s', movie_id, video_path)
        return None
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(output['output_dir'], ignore_errors=True)
        logger.error(
            'ffmpeg fallo generando thumbnails movie_id=%s input=%s stderr=%s',
            movie_id, video_path, (exc.stderr or '').strip(), exc_info=True,
        )
        return None

    if not output['sprite_path'].exists() or output['sprite_path'].stat().st_size <= 0:
        shutil.rmtree(output['output_dir'], ignore_errors=True)
        logger.error(
            'Sprite de thumbnails incompleto movie_id=%s sprite=%s stdout=%s stderr=%s',
            movie_id, output['sprite_path'], (result.stdout or '').strip(), (result.stderr or '').strip(),
        )
        return None

    _write_thumbnail_vtt(
        output['vtt_path'],
        sprite_filename=output['sprite_path'].name,
        duration=duration,
        interval=interval,
        total_thumbnails=total_thumbnails,
    )
    if not output['vtt_path'].exists() or output['vtt_path'].stat().st_size <= 0:
        shutil.rmtree(output['output_dir'], ignore_errors=True)
        logger.error('VTT de thumbnails incompleto movie_id=%s vtt=%s', movie_id, output['vtt_path'])
        return None

    logger.info(
        'Thumbnails generados movie_id=%s sprite_url=%s vtt_url=%s',
        movie_id, output['sprite_url'], output['vtt_url'],
    )
    return {
        'sprite_url': output['sprite_url'],
        'vtt_url': output['vtt_url'],
        'interval': interval,
    }


def _save_movie_thumbnail_metadata(movie_id, thumbnails, *, mark_ready=False):
    if not movie_id or not thumbnails:
        return
    Movie = apps.get_model('movies', 'Movie')
    updates = {
        'thumbnail_sprite': thumbnails.get('sprite_url', ''),
        'thumbnail_vtt': thumbnails.get('vtt_url', ''),
        'thumbnail_interval': int(thumbnails.get('interval') or THUMBNAIL_INTERVAL_SECONDS),
        'error_message': '',
    }
    if mark_ready:
        updates.update({
            'status': 'listo',
            'processing_step': 'finalizado',
            'processing_stage': 'finalizado',
            'processing_progress': PROCESSING_STAGES['finalizado'],
            'processing_finished_at': timezone.now(),
        })
    Movie.objects.filter(pk=movie_id).update(**updates)


def _mark_movie_hls_ready(movie_id, playlist_url: str, renditions=None, original_size=None, thumbnails=None):
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
    if thumbnails:
        updates['thumbnail_sprite'] = thumbnails.get('sprite_url', '')
        updates['thumbnail_vtt'] = thumbnails.get('vtt_url', '')
        updates['thumbnail_interval'] = int(thumbnails.get('interval') or THUMBNAIL_INTERVAL_SECONDS)
    Movie.objects.filter(pk=movie_id).update(**updates)


def procesar_thumbnails_background(public_url: str, movie_id=None, *, force=False) -> None:
    close_old_connections()
    try:
        video_path = resolve_local_media_path(public_url)
        if not video_path or not video_path.exists():
            logger.warning(
                'No se generaron thumbnails; archivo local inexistente movie_id=%s public_url=%s path=%s',
                movie_id, public_url, video_path,
            )
            return

        normalized_path = process_video(video_path, movie_id=movie_id)
        if normalized_path:
            video_path = normalized_path

        thumbnails = _generate_thumbnail_previews(
            video_path,
            movie_id=movie_id,
            interval=THUMBNAIL_INTERVAL_SECONDS,
            force=force,
        )
        if thumbnails:
            _save_movie_thumbnail_metadata(movie_id, thumbnails, mark_ready=True)
            logger.info('Thumbnails listos en background movie_id=%s public_url=%s', movie_id, public_url)
    except Exception:
        logger.exception('Error inesperado generando thumbnails en background movie_id=%s public_url=%s', movie_id, public_url)
    finally:
        close_old_connections()


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
            thumbnails = _generate_thumbnail_previews(
                video_path,
                movie_id=movie_id,
                interval=THUMBNAIL_INTERVAL_SECONDS,
            )
            if thumbnails:
                _save_movie_thumbnail_metadata(movie_id, thumbnails)
            _update_movie_processing_state(
                movie_id, status='listo', step='hls finalizado', stage='finalizado',
                finished_at=timezone.now(), clear_error=True,
            )
            logger.info('Video ya esta en HLS; se omite procesamiento movie_id=%s public_url=%s', movie_id, public_url)
            return

        normalized_path = process_video(video_path, movie_id=movie_id)
        if not normalized_path:
            _update_movie_processing_state(
                movie_id, status='error', step='error', stage='error',
                progress=0, finished_at=timezone.now(),
                error_message='No se pudo convertir el video a MP4 compatible.',
            )
            return
        video_path = normalized_path

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
        thumbnails = _generate_thumbnail_previews(
            video_path,
            movie_id=movie_id,
            interval=THUMBNAIL_INTERVAL_SECONDS,
        )
        if not thumbnails:
            _update_movie_processing_state(
                movie_id, status='error', step='error', stage='error',
                progress=0, finished_at=timezone.now(),
                error_message='No se pudieron generar thumbnails para el video.',
            )
            return

        _mark_movie_hls_ready(
            movie_id, playlist_url,
            renditions=used_renditions, original_size=original_size,
            thumbnails=thumbnails,
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


def start_thumbnail_processing_background(public_url: str, movie_id=None, *, force=False) -> None:
    thread = threading.Thread(
        target=procesar_thumbnails_background,
        kwargs={'public_url': public_url, 'movie_id': movie_id, 'force': force},
        daemon=True,
        name=f'thumbnail-processing-{movie_id or "pending"}',
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


def delete_local_thumbnails(movie_or_id) -> None:
    movie_id = getattr(movie_or_id, 'pk', movie_or_id)
    if not movie_id:
        return
    thumbnails_dir = get_local_thumbnails_dir() / str(movie_id)
    if thumbnails_dir.exists():
        shutil.rmtree(thumbnails_dir, ignore_errors=True)
