from urllib.parse import urlsplit


def split_csv(value):
    return [item.strip() for item in (value or '').split(',') if item.strip()]


def normalize_origin(value, default_scheme='http'):
    origin = (value or '').strip()
    if not origin:
        return None
    if '://' not in origin:
        origin = f'{default_scheme}://{origin}'
    parsed = urlsplit(origin)
    scheme = parsed.scheme or default_scheme
    netloc = parsed.netloc or parsed.path
    if not netloc:
        return None
    return f'{scheme}://{netloc}'


def build_csrf_trusted_origins(explicit_origins, allowed_hosts):
    trusted = []
    seen = set()

    def add(origin):
        normalized = normalize_origin(origin)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        trusted.append(normalized)

    for origin in explicit_origins:
        add(origin)

    for host in allowed_hosts:
        host = (host or '').strip()
        if not host or host == '*':
            continue

        if '://' in host:
            add(host)
            continue

        wildcard_host = host
        if wildcard_host.startswith('.'):
            wildcard_host = f'*.{wildcard_host.lstrip(".")}'

        add(f'http://{wildcard_host}')
        add(f'https://{wildcard_host}')

    return trusted
