"""Shared PostgreSQL settings. No secrets or SQLite fallback."""
import os
from django.core.exceptions import ImproperlyConfigured


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"Set {name} in the process environment.")
    return value


SECRET_KEY = required("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes",
    "accounts", "academics",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "accounts.Student"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": required("PGDATABASE"),
    "USER": required("PGUSER"),
    "PASSWORD": os.environ.get("PGPASSWORD", ""),
    "HOST": os.environ.get("PGHOST", "127.0.0.1"),
    "PORT": os.environ.get("PGPORT", "5432"),
    "CONN_MAX_AGE": 0,
    "OPTIONS": {"sslmode": os.environ.get("PGSSLMODE", "prefer")},
}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
