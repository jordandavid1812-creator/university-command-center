#!/bin/sh
# One-off database update, run with the MIGRATOR login only (never the website's):
#   docker compose run --rm migrate
set -eu
cd /app/server
settings=--settings=config.settings.auth_migration
python manage.py migrate --noinput $settings
python manage.py configure_auth_role $settings
python manage.py configure_runtime $settings
echo "Database is up to date and the website's restricted logins are configured."
