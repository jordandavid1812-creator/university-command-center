#!/bin/sh
# Website container start. Preflight first: every system check, including the deploy checks
# and the project's own E101-E105 gates, must pass or the website does not start.
set -eu
cd /app/server
python manage.py check --deploy --fail-level WARNING
# gthread workers keep the site responsive while one request waits on an AI answer (60 s cap).
# No access log: request lines can contain one-time sign-up and reset tokens.
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 --worker-class gthread --workers 2 --threads 4 \
    --timeout 120 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 100 \
    --worker-tmp-dir /tmp
