"""Vercel entry point for the student website (named in pyproject.toml: [tool.vercel]).

1. Always uses config.settings.web_vercel (never a development or migration profile, whatever the
   environment says).
2. Runs every system check, including the deploy checks and the project's own E101-E106 gates
   (restricted database settings, logging privacy, no debug, approved email, invite-only
   sign-up), and stops before serving anything if one fails. Vercel itself runs none of them.
3. Then hands requests to Django. The database role checks still run on every request.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
for folder in (str(ROOT), str(ROOT / 'server')):
    if folder not in sys.path:
        sys.path.insert(0, folder)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.web_vercel'

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.core.wsgi import get_wsgi_application  # noqa: E402

# Raises SystemCheckError (and the website does not start) on any warning or error.
call_command('check', deploy=True, fail_level='WARNING')

app = get_wsgi_application()
