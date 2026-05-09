# StreamVerse

Plataforma personal de streaming hecha con Django para administrar y reproducir peliculas y series propias.

## Stack principal

- Python 3.11
- Django 5.2.12
- PostgreSQL obligatorio por `DATABASE_URL`
- Supabase PostgreSQL + Supabase Storage
- Django Templates
- CSS personalizado
- JavaScript
- Three.js
- `dj-database-url`
- `psycopg`
- `python-dotenv`
- `supabase`
- `ffmpeg` / `ffprobe` disponibles en el sistema para procesar video

## Base de datos

Este proyecto ya no usa SQLite.
La unica forma valida de conectar la aplicacion es mediante `DATABASE_URL` apuntando a PostgreSQL.

Ejemplo:

```env
DATABASE_URL=postgresql://usuario:password@host:5432/postgres?sslmode=require
```

### Supabase

Si usas Supabase, el proyecto agrega `sslmode=require` automaticamente si no viene en la URL.
Aun asi, lo correcto es dejarlo ya incluido en `DATABASE_URL`.

## Storage y procesamiento de archivos

El proyecto usa dos caminos de almacenamiento:

- Los datos del catalogo viven en PostgreSQL (Supabase).
- Portadas y avatars subidos desde formularios se guardan en Supabase Storage.
- Los videos subidos desde el panel admin se guardan temporalmente en `MEDIA_ROOT/videos/`, se procesan en segundo plano con `ffmpeg` y terminan como HLS local en `MEDIA_ROOT/videos/hls/.../index.m3u8`.
- `Movie.video_url` queda apuntando al `.m3u8` final cuando el procesamiento termina correctamente.
- `Movie.status` y `Movie.processing_step` guardan el estado: `subiendo`, `procesando`, `listo` o `error`.

### Variables obligatorias para Storage

```env
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-service-role-o-anon-key
```

Sin esas variables:
- la app sigue arrancando
- pero los uploads desde el panel admin mostraran error
- no se usara almacenamiento local como fallback

### Procesamiento HLS de videos

Cuando un administrador sube un video local:

1. Django guarda el archivo sin bloquear el guardado de la ficha.
2. Se lanza un thread en background desde `core.local_media.start_video_processing_background`.
3. El proceso normaliza el video a MP4 compatible con `libx264`, `preset=superfast`, `CRF 23`, `threads=0` y `movflags=+faststart`.
4. `ffmpeg` genera HLS multi-bitrate en un solo proceso: 360p, 480p y 720p.
5. Se generan thumbnails tipo sprite + WebVTT cada 10 segundos.
6. La base de datos se actualiza para usar el `master.m3u8` final.
7. El reproductor carga automaticamente HLS con `hls.js` cuando el navegador lo necesita.

Variables opcionales:

```env
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
FFMPEG_HLS_TIME=5
FFMPEG_HLS_PRESET=superfast
FFMPEG_HLS_CRF=23
FFMPEG_THREADS=0
FFMPEG_HLS_AUDIO_BITRATE=128k
LOCAL_VIDEO_UPLOAD_MAX_MB=2048
```

Comandos FFmpeg equivalentes del pipeline optimizado:

```powershell
# a) MP4 compatible rapido para navegador y HLS
ffmpeg -y -nostdin -hide_banner -loglevel error -threads 0 -i input.ext -map 0:v:0 -map 0:a? -c:v libx264 -preset superfast -crf 23 -profile:v main -pix_fmt yuv420p -c:a aac -b:a 128k -ac 2 -movflags +faststart output.mp4

# b) HLS multi-bitrate en un solo ffmpeg
ffmpeg -y -nostdin -hide_banner -loglevel error -threads 0 -i output.mp4 -filter_complex "[0:v]split=3[v0in][v1in][v2in];[v0in]scale=w=640:h=360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];[v1in]scale=w=854:h=480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];[v2in]scale=w=1280:h=720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[v2]" -map "[v0]" -map 0:a:0 -map "[v1]" -map 0:a:0 -map "[v2]" -map 0:a:0 -c:v:0 libx264 -preset:v:0 superfast -crf:v:0 23 -b:v:0 600k -maxrate:v:0 700k -bufsize:v:0 1000k -c:v:1 libx264 -preset:v:1 superfast -crf:v:1 23 -b:v:1 1000k -maxrate:v:1 1200k -bufsize:v:1 1500k -c:v:2 libx264 -preset:v:2 superfast -crf:v:2 23 -b:v:2 2500k -maxrate:v:2 2800k -bufsize:v:2 4000k -c:a:0 aac -b:a:0 128k -ac:a:0 2 -c:a:1 aac -b:a:1 128k -ac:a:1 2 -c:a:2 aac -b:a:2 128k -ac:a:2 2 -f hls -hls_time 5 -hls_playlist_type vod -hls_segment_filename "media/videos/hls/<movie_id>/%v/segment_%03d.ts" -master_pl_name master.m3u8 -var_stream_map "v:0,a:0,name:360p v:1,a:1,name:480p v:2,a:2,name:720p" "media/videos/hls/<movie_id>/%v/index.m3u8"

# c) Thumbnails cada 10 segundos en sprite + VTT
ffmpeg -y -nostdin -hide_banner -loglevel error -threads 0 -i output.mp4 -an -vf "fps=1/10,scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:(ow-iw)/2:(oh-ih)/2,tile=5x<rows>" -frames:v 1 -q:v 4 media/thumbnails/<movie_id>/sprite.jpg
```

Estructura resultante:

```text
MEDIA_ROOT/
  videos/
    hls/<movie_id>/
      master.m3u8
      360p/index.m3u8
      360p/segment_000.ts
      480p/index.m3u8
      480p/segment_000.ts
      720p/index.m3u8
      720p/segment_000.ts
  thumbnails/<movie_id>/
    sprite.jpg
    preview.vtt
```

Este flujo es mas rapido en Raspberry Pi porque decodifica la fuente una sola vez para generar las tres calidades HLS, usa `superfast` + `CRF 23`, permite que FFmpeg use todos los nucleos con `-threads 0`, baja el costo de thumbnails a una captura cada 10 segundos y evita presets lentos.

### Migracion de archivos legacy

Si todavia tienes archivos en la carpeta local `media/`, ejecuta esto **antes de borrar esa carpeta**:

```powershell
& .\.venv\Scripts\python.exe manage.py migrate_legacy_media_to_supabase
```

Ese comando:
- sube portadas, videos y avatars legacy a Supabase Storage
- guarda la URL publica en la base de datos
- elimina el archivo local si la subida fue exitosa

## Variables de entorno

Archivo base:
- `.env.example`

Contenido minimo:

```env
DEBUG=1
SECRET_KEY=change-me-dev-key
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgresql://usuario:password@host:5432/postgres?sslmode=require
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-service-role-o-anon-key
```

## Como levantar el proyecto

### Deploy separado en Raspberry

La guia de produccion para correr cliente y admin como procesos separados esta en:

- `docs/raspberry-split-deploy.md`

Entry points nuevos:

- Cliente: `config.settings_client` + `config.wsgi_client`
- Admin: `config.settings_admin` + `config.wsgi_admin`

### Instalacion inicial

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver 8033 --settings=config.settings_client
```

### Comandos utiles

```powershell
& .\.venv\Scripts\python.exe manage.py check
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver 8032 --settings=config.settings_admin
& .\.venv\Scripts\python.exe manage.py runserver 8033 --settings=config.settings_client
```

## URLs importantes

- Admin local: `http://127.0.0.1:8032/`
- Admin login: `http://127.0.0.1:8032/login/`
- Admin catalogo: `http://127.0.0.1:8032/peliculas/`
- Cliente home: `http://127.0.0.1:8033/`
- Cliente login: `http://127.0.0.1:8033/cuenta/login/`
- Cliente registro: `http://127.0.0.1:8033/cuenta/registro/`
- Cliente dashboard: `http://127.0.0.1:8033/cuenta/dashboard/`

## Que hace el proyecto

### Usuario
- login y registro
- perfil y ajustes
- avatar por URL o upload a Supabase Storage
- favoritos (`Mi lista`)
- `Seguir viendo`
- guardado de progreso
- sugerencias por genero
- reproduccion por URL publica

### Admin
- panel admin personalizado
- CRUD de peliculas y series
- carga rapida de catalogo
- subida de portadas y videos a Supabase Storage
- gestion de generos
- gestion de usuarios
- salud del catalogo
- actividad de reproduccion

## Archivos importantes

- `config/settings.py`
- `.env`
- `.env.example`
- `core/views.py`
- `movies/views.py`
- `templates/base.html`
- `templates/movies/home.html`
- `templates/core/dashboard.html`
- `templates/core/admin_panel.html`
- `static/css/main.css`
- `static/js/cinema-scene.js`

## Notas

- `DATABASE_URL` es obligatoria.
- Si falta `DATABASE_URL`, Django lanzara error al arrancar.
- El proyecto esta preparado para Supabase PostgreSQL.
- El admin sigue siendo web y la parte usuario puede evolucionar a PWA/APK.
