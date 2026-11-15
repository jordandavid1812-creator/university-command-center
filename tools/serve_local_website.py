"""Start the local student website on 127.0.0.1 without Django's runserver.

runserver always reads the django_migrations table on startup. The restricted academic
runtime login is deliberately not allowed to read it, so runserver cannot start with the
application credentials. This serves the same WSGI application with Django's development
server, bound to 127.0.0.1 only. Run migrate, configure_auth_role and configure_runtime
with the offline migration settings first; start this with application credentials only.

    python tools/serve_local_website.py
    python tools/serve_local_website.py --port 8001
    python tools/serve_local_website.py --settings config.settings.auth_development
"""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
DEFAULT_SETTINGS = "config.settings.web_development"
ALLOWED_SETTINGS = ("config.settings.web_development", "config.settings.auth_development")


def options(argv=None):
    parser = argparse.ArgumentParser(description="Start the local student website on 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8000, help="Port on 127.0.0.1 (1024-65535, default 8000).")
    parser.add_argument("--settings", default=DEFAULT_SETTINGS, choices=ALLOWED_SETTINGS,
                        help="A local development profile; production and migration profiles are refused.")
    values = parser.parse_args(argv)
    if not 1024 <= values.port <= 65535:
        parser.error("Choose a port from 1024 to 65535.")
    return values


def main(argv=None):
    values = options(argv)
    sys.path[:0] = [str(REPO / "server"), str(REPO)]
    os.environ["DJANGO_SETTINGS_MODULE"] = values.settings
    import django
    django.setup()
    from django.core.management import call_command
    from django.core.servers.basehttp import run
    from django.core.wsgi import get_wsgi_application
    # The same system checks runserver performs (project and Django checks, no database
    # checks). Any error stops here before the website starts.
    call_command("check")
    print(f"Open http://{HOST}:{values.port}/  ({values.settings}; press Ctrl+C to stop)")
    try:
        run(HOST, values.port, get_wsgi_application(), threading=True)
    except KeyboardInterrupt:
        print("Website stopped.")


if __name__ == "__main__":
    main()
