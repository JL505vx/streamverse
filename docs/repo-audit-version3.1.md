# Auditoria de repositorio v3.1

Fecha: 2026-05-09

## Resumen

El repositorio esta en buen estado para la fase actual de separacion progresiva: un solo monolito Django con dos entrypoints de ejecucion, admin en `8032` y cliente en `8033`. La limpieza segura se limita a artefactos locales ignorados; no se eliminaron archivos versionados porque los candidatos dudosos aun pueden estar en uso por base de datos, compatibilidad temporal o despliegue.

## Clasificacion

### Critico

- `config/settings.py`, `config/settings_admin.py`, `config/settings_client.py`
- `config/urls_admin.py`, `config/urls_client.py`
- `config/wsgi_admin.py`, `config/wsgi_client.py`
- `core/local_media.py`
- `core/forms.py`
- `core/views.py`
- `movies/models.py`
- `movies/views.py`
- `templates/movies/movie_watch.html`
- migraciones en `core/migrations/` y `movies/migrations/`
- configs de deploy en `deploy/`

### Usado

- `templates/`: todos los templates `.html` aparecen referenciados por vistas, includes, extends o configuracion de errores.
- `static/css/main.css`, `static/js/*.js`, `static/pwa/*.png`: referenciados desde `base.html` o vistas PWA.
- `config/asgi.py`, `config/routing.py`, `movies/routing.py`, `movies/consumers.py`: usados por Channels y watch party.
- `core/middleware.py`: usado desde `core.apps.CoreConfig.ready()` para separar cookies de sesion/CSRF por rol.
- `core/management/commands/migrate_legacy_media_to_supabase.py`: comando operativo de migracion.
- `core/urls.py` y `config/urls.py`: compatibilidad del monolito mientras la migracion sigue viva.

### Sospechoso, mantener por ahora

- `static/demo/*.svg`: no tienen referencia directa en codigo, pero pueden estar guardados como `cover_url` en registros existentes de Supabase/PostgreSQL.
- aliases legacy en `core/urls_admin.py` bajo `cuenta/panel-admin/`: existen para no romper enlaces anteriores durante la migracion.
- `config/urls.py` y `core/urls.py`: duplican superficie admin/cliente del monolito, pero mantienen compatibilidad local y rollback.

### Muerto seguro local

Estos archivos no deben versionarse ni desplegarse:

- `__pycache__/`
- `*.pyc`
- `db.sqlite3`
- `runserver-local.log`
- `runserver-local.err.log`

## Problemas encontrados

- Hay compatibilidad legacy intencional, especialmente rutas del monolito anterior.
- La separacion admin/cliente todavia comparte `base.html`, `core/views.py` y `core/forms.py`; funcional, pero no es separacion fisica completa.
- `static/demo/*.svg` depende de datos externos en la base, asi que no puede borrarse sin consultar registros.
- No hay linter configurado en el repo para detectar imports muertos de forma automatica.

## Acciones ejecutadas

- Se corrigio el README para documentar que `manage.py runserver 8032/8033` selecciona settings automaticamente.
- Se agrego este reporte de auditoria para dejar trazabilidad de lo que se mantiene, lo que es sospechoso y lo que se puede limpiar localmente.
- Se ajusto un test de upload por chunks para validar el contrato minimo y permitir campos nuevos de progreso en la respuesta.
- Se limpiaron artefactos locales ignorados generados por ejecuciones previas.

## Recomendaciones futuras

- Crear una consulta/management command para detectar `cover_url` que apunten a `static/demo/` antes de eliminar esos SVG.
- Marcar fecha de retiro para aliases legacy `cuenta/panel-admin/*`.
- Separar gradualmente `core/views.py` en modulos `core/admin_views.py` y `core/client_views.py`.
- Agregar `ruff` o `pyflakes` a desarrollo para detectar imports no usados y dead code con menos riesgo.
- Mantener `media/`, `.env` y `.venv` fuera de Git, como ya esta definido en `.gitignore`.
