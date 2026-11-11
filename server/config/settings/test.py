"""Real PostgreSQL, real migrations, independent test database."""
from .base import *  # noqa: F403

DATABASES["default"]["TEST"] = {"NAME": required("PGTESTDATABASE")}
if DATABASES["default"]["TEST"]["NAME"] == DATABASES["default"]["NAME"]:
    raise ImproperlyConfigured("PGTESTDATABASE must differ from PGDATABASE.")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
