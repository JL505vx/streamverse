#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def _settings_for_runserver(argv):
    if len(argv) < 2 or argv[1] != 'runserver':
        return None
    if any(arg.startswith('--settings=') for arg in argv):
        return None

    addrport = next((arg for arg in argv[2:] if not arg.startswith('-')), '')
    port = (addrport.rsplit(':', 1)[-1] if addrport else '').strip()
    if port == '8032':
        return 'config.settings_admin'
    if port == '8033':
        return 'config.settings_client'
    return None


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', _settings_for_runserver(sys.argv) or 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
