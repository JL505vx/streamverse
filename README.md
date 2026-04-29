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
3. El proceso normaliza el audio a AAC/MP4 compatible cuando hace falta.
4. `ffmpeg` genera `index.m3u8` y segmentos `.ts`.
5. La base de datos se actualiza para usar el `.m3u8` final.
6. El reproductor carga automaticamente HLS con `hls.js` cuando el navegador lo necesita.

Variables opcionales:

```env
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
FFMPEG_HLS_TIME=6
FFMPEG_HLS_PRESET=veryfast
FFMPEG_HLS_CRF=23
FFMPEG_HLS_AUDIO_BITRATE=128k
LOCAL_VIDEO_UPLOAD_MAX_MB=2048
```

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

### Instalacion inicial

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver 8032
```

### Comandos utiles

```powershell
& .\.venv\Scripts\python.exe manage.py check
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver 8032
```

## URLs importantes

- Home: `http://127.0.0.1:8032/`
- Login: `http://127.0.0.1:8032/cuenta/login/`
- Registro: `http://127.0.0.1:8032/cuenta/registro/`
- Dashboard usuario: `http://127.0.0.1:8032/cuenta/dashboard/`
- Ajustes usuario: `http://127.0.0.1:8032/cuenta/ajustes/`
- Panel admin: `http://127.0.0.1:8032/cuenta/panel-admin/`
- Catalogo admin: `http://127.0.0.1:8032/cuenta/panel-admin/peliculas/`

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
