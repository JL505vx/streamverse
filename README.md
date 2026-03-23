# StreamVerse

Plataforma personal de streaming hecha con Django para administrar y reproducir peliculas y series propias.

El proyecto esta pensado para funcionar primero en local y despues crecer a:
- PWA para usuarios
- APK para usuarios (wrapper/app Android)
- servidor casero en Raspberry Pi
- panel admin web separado

## Que es este proyecto

StreamVerse es un mini streaming privado con dos experiencias distintas:
- Usuario: explora catalogo, reproduce contenido, guarda favoritos, continua viendo y ajusta su perfil.
- Admin: gestiona peliculas, series, generos, usuarios, archivos locales, salud del catalogo y actividad.

La idea es centralizar una biblioteca personal de video y convertirla en una experiencia tipo Netflix / Disney+ / HBO Max, pero bajo tu control.

## Tecnologias principales

- Python 3.11
- Django 5.2.12
- SQLite por defecto
- PostgreSQL opcional
- Django Templates
- CSS personalizado
- JavaScript
- Three.js para fondo visual 3D
- python-dotenv para variables de entorno
- psycopg 3 para PostgreSQL

## Base de datos

### Base de datos actual

Por defecto, el proyecto usa SQLite.

Archivo actual:
- `db.sqlite3`

Esto significa que si en el archivo `.env` la variable `POSTGRES_DB` esta vacia, Django trabaja con SQLite automaticamente.

### Cuando usa PostgreSQL

El proyecto cambia a PostgreSQL solo si defines `POSTGRES_DB` en `.env`.

Variables disponibles:

```env
POSTGRES_DB=
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

## Funciones implementadas

### Usuario
- login y registro
- dashboard / mi espacio
- perfil y ajustes
- avatar por archivo o URL
- favoritos (`Mi lista`)
- `Seguir viendo`
- guardado de progreso
- continuar reproduccion desde donde se quedo
- sugerencias por genero
- reproduccion de video local o por URL

### Admin
- panel admin personalizado en HTML propio
- CRUD de peliculas y series
- carga rapida de catalogo
- carga de portada por URL o archivo local
- carga de video por URL o archivo local
- reemplazo de archivos de peliculas existentes
- CRUD de generos
- gestion de usuarios
- salud del catalogo
- actividad de reproduccion
- vista responsiva para PC y movil

### Reproduccion
- soporte de streaming local
- soporte `HTTP Range` para adelantar / atrasar videos
- ocultacion del boton de descarga en el reproductor
- registro de sesiones de reproduccion

## Estructura del proyecto

- `config/`: configuracion principal de Django
- `core/`: auth, panel admin, dashboard, ajustes, usuarios
- `movies/`: catalogo, detalle, favoritos, progreso, reproduccion
- `templates/`: vistas HTML
- `static/`: CSS, JS y assets
- `media/`: portadas, videos, avatars subidos
- `db.sqlite3`: base de datos actual local

## Variables de entorno

Archivo base:
- `.env.example`

Pasos:
1. copiar `.env.example` a `.env`
2. ajustar variables si hace falta

Variables actuales:

```env
DEBUG=1
SECRET_KEY=change-me-dev-key
ALLOWED_HOSTS=127.0.0.1,localhost

POSTGRES_DB=
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

## Como levantar el proyecto

### Requisitos
- Windows + PowerShell
- Python 3.11 instalado

### Instalacion inicial

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver 8032
```

### Comando correcto para levantarlo despues

Si ya tienes `.venv` creada y dependencias instaladas, usa este comando:

```powershell
& .\.venv\Scripts\python.exe manage.py runserver 8032
```

### Verificacion rapida

```powershell
& .\.venv\Scripts\python.exe manage.py check
```

## URLs importantes

- Home: `http://127.0.0.1:8032/`
- Login: `http://127.0.0.1:8032/cuenta/login/`
- Registro: `http://127.0.0.1:8032/cuenta/registro/`
- Dashboard usuario: `http://127.0.0.1:8032/cuenta/dashboard/`
- Ajustes usuario: `http://127.0.0.1:8032/cuenta/ajustes/`
- Panel admin: `http://127.0.0.1:8032/cuenta/panel-admin/`
- Catalogo admin: `http://127.0.0.1:8032/cuenta/panel-admin/peliculas/`

## Roles del sistema

### Usuario normal
Puede:
- ver el catalogo
- reproducir contenido
- usar favoritos
- continuar viendo
- editar perfil y ajustes

No puede:
- entrar al panel admin
- editar catalogo
- gestionar usuarios

### Admin (`is_staff=True`)
Puede:
- entrar al panel admin
- cargar peliculas y series
- subir portadas y videos
- editar catalogo
- administrar usuarios y generos
- revisar actividad y estado del sistema

## Cuentas demo actuales

- Admin: `adminsv` / `peliculas08`
- Usuario: `skome` / `peliculas08`

## Dependencias actuales

`requirements.txt`

```txt
django==5.2.12
psycopg[binary]==3.3.3
python-dotenv==1.2.2
```

## Archivos importantes para desarrollo

- `config/settings.py`
- `config/urls.py`
- `core/views.py`
- `movies/views.py`
- `templates/base.html`
- `templates/movies/home.html`
- `templates/core/dashboard.html`
- `templates/core/admin_panel.html`
- `static/css/main.css`
- `static/js/cinema-scene.js`

## Estado actual del despliegue

Hoy el proyecto esta preparado para desarrollo local.

Actualmente:
- corre con `runserver`
- usa SQLite por defecto
- guarda archivos en `media/`
- funciona como web responsiva
- todavia no es PWA completa
- todavia no es APK

## Proximo paso recomendado

Si el siguiente objetivo es instalarlo en celular, el orden correcto es:

1. dejar el proyecto como PWA
2. mantener el admin como panel web
3. empaquetar APK solo para usuarios
4. mover el backend a Raspberry Pi o a un servidor siempre encendido
5. activar HTTPS cuando salga de local

## Notas tecnicas importantes

- Los videos locales se sirven desde `media/`
- El soporte `Range` ya esta implementado para permitir adelantar y atrasar contenido local
- El panel admin es HTML personalizado, no depende del Django Admin tradicional
- `LOGOUT` redirige al home
- `LOGIN_REDIRECT_URL` apunta al dashboard de usuario
- Si `POSTGRES_DB` esta vacio, la app seguira usando SQLite

## Migracion futura a PostgreSQL

1. editar `.env`
2. definir las variables de PostgreSQL
3. correr migraciones

Ejemplo:

```env
POSTGRES_DB=streamverse
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

Luego:

```powershell
& .\.venv\Scripts\python.exe manage.py migrate
```

## Resumen rapido

- framework: Django
- lenguaje principal: Python
- base de datos actual: SQLite
- base de datos opcional: PostgreSQL
- frontend: templates HTML + CSS + JS
- visual extra: Three.js
- uso actual: streaming privado local
- siguiente evolucion natural: PWA para usuarios + admin web
