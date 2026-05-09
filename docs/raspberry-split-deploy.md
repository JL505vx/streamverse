# StreamVerse split deploy en Raspberry Pi

Objetivo de esta fase: mantener un solo repo Django, pero correr dos procesos separados:

```text
projectgp.online        -> landing actual
app.projectgp.online    -> StreamVerse cliente -> 127.0.0.1:8032
admin.projectgp.online  -> StreamVerse admin   -> 127.0.0.1:8033
```

## 1. DNS en Cloudflare

Crea estos registros como CNAME hacia el tunnel actual:

```text
projectgp.online        CNAME <tunnel-id>.cfargotunnel.com
app.projectgp.online    CNAME <tunnel-id>.cfargotunnel.com
admin.projectgp.online  CNAME <tunnel-id>.cfargotunnel.com
```

Si usas `cloudflared tunnel route dns`, el equivalente es:

```bash
cloudflared tunnel route dns devgp projectgp.online
cloudflared tunnel route dns devgp app.projectgp.online
cloudflared tunnel route dns devgp admin.projectgp.online
```

## 2. Variables de entorno

En `/mnt/ssd1/proyectos/streamverse/.env` deja, como minimo:

```env
DEBUG=0
SECRET_KEY=pon-tu-secret-key-real
ALLOWED_HOSTS=127.0.0.1,localhost,app.projectgp.online,admin.projectgp.online
CSRF_TRUSTED_ORIGINS=https://app.projectgp.online,https://admin.projectgp.online
CLIENT_BASE_URL=https://app.projectgp.online
ADMIN_BASE_URL=https://admin.projectgp.online
DATABASE_URL=postgresql://...
SUPABASE_URL=https://...
SUPABASE_KEY=...
MEDIA_URL=/media/
MEDIA_ROOT=/mnt/ssd1/proyectos/streamverse/media
FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe
```

## 3. Preparar repo

```bash
cd /mnt/ssd1/proyectos/streamverse
git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings_client
python manage.py collectstatic --noinput --settings=config.settings_client
python manage.py check --settings=config.settings_client
python manage.py check --settings=config.settings_admin
```

## 4. Instalar systemd

Ajusta `User=pi` si tu usuario del sistema tiene otro nombre.

```bash
cd /mnt/ssd1/proyectos/streamverse
sudo cp deploy/systemd/streamverse-client.service /etc/systemd/system/
sudo cp deploy/systemd/streamverse-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable streamverse-client streamverse-admin
sudo systemctl start streamverse-client streamverse-admin
sudo systemctl status streamverse-client --no-pager
sudo systemctl status streamverse-admin --no-pager
```

Pruebas por IP local antes de dominio:

```bash
curl -I http://127.0.0.1:8032/
curl -I http://127.0.0.1:8033/login/
```

## 5. Instalar Nginx

```bash
cd /mnt/ssd1/proyectos/streamverse
sudo cp deploy/nginx/streamverse-proxy-headers.conf /etc/nginx/snippets/
sudo cp deploy/nginx/streamverse-subdomains.conf /etc/nginx/sites-available/streamverse-subdomains.conf
sudo ln -sf /etc/nginx/sites-available/streamverse-subdomains.conf /etc/nginx/sites-enabled/streamverse-subdomains.conf
sudo nginx -t
sudo systemctl reload nginx
```

Si la landing de `projectgp.online` sigue corriendo por PM2 en `127.0.0.1:8022`, edita el server block de `projectgp.online` y usa el bloque `proxy_pass` comentado en lugar de `root`.

Pruebas por Host header:

```bash
curl -I -H "Host: app.projectgp.online" http://127.0.0.1/
curl -I -H "Host: admin.projectgp.online" http://127.0.0.1/login/
curl -I -H "Host: app.projectgp.online" http://127.0.0.1/cuenta/panel-admin/
```

La ultima debe devolver `404`.

## 6. Cloudflare Tunnel

Actualiza tu `/home/pi/.cloudflared/config.yml` usando `deploy/cloudflared/config.yml.example` como base.

```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager
```

Todo hostname debe apuntar a Nginx local:

```text
https://projectgp.online       -> http://127.0.0.1:80
https://app.projectgp.online   -> http://127.0.0.1:80
https://admin.projectgp.online -> http://127.0.0.1:80
```

## 7. Seguridad admin

El admin ya queda fuera del dominio cliente porque `app.projectgp.online` no monta rutas admin y Nginx bloquea prefijos administrativos.

Para restringir admin a LAN/Tailscale, descomenta en Nginx:

```nginx
allow 192.168.0.0/16;
allow 100.64.0.0/10;
deny all;
```

Si necesitas Basic Auth:

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-streamverse-admin tu_usuario
```

Dentro del server block `admin.projectgp.online`:

```nginx
auth_basic "StreamVerse Admin";
auth_basic_user_file /etc/nginx/.htpasswd-streamverse-admin;
```

## 8. Flujo de deploy

Deploy manual limpio:

```bash
cd /mnt/ssd1/proyectos/streamverse
git pull
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=config.settings_client
python manage.py collectstatic --noinput --settings=config.settings_client
python manage.py check --settings=config.settings_client
python manage.py check --settings=config.settings_admin
sudo systemctl restart streamverse-client streamverse-admin
sudo systemctl status streamverse-client streamverse-admin --no-pager
```

Rollback rapido:

```bash
cd /mnt/ssd1/proyectos/streamverse
git log --oneline -5
git checkout <commit-anterior>
sudo systemctl restart streamverse-client streamverse-admin
```

## 9. Errores comunes

`DisallowedHost`
: revisa `ALLOWED_HOSTS`.

`CSRF verification failed`
: revisa `CSRF_TRUSTED_ORIGINS`.

`502 Bad Gateway`
: revisa `systemctl status streamverse-client streamverse-admin` y que los puertos 8032/8033 esten escuchando.

`admin visible desde app.projectgp.online`
: confirma que Nginx cargo el sitio correcto con `sudo nginx -T | grep -n "app.projectgp.online"`.

`videos no reproducen`
: revisa permisos de `/mnt/ssd1/proyectos/streamverse/media` y que `MEDIA_ROOT` apunte a la carpeta real.
