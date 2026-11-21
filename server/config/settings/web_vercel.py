"""Public HTTPS website on Vercel with the Supabase database (owner's choice).

Started only by /vercel_app.py, which runs every system check (including deploy checks and the
project's E101-E106 gates) before it serves anything. Real email uses the reviewed backend (launch
step C); check accounts.E105 refuses any other.

- Vercel's edge terminates HTTPS and sets REMOTE_ADDR (the visitor) and wsgi.url_scheme itself
  (vercel_runtime builds them from the x-forwarded-for / x-forwarded-proto headers it adds), so
  no proxy network is trusted here.
- The database is reached through Supabase's shared pooler (transaction mode, port 6543), as
  the restricted ucc_runtime and ucc_auth logins. The pooler needs "<login>.<project ref>" as
  the user name, ignores per-connection options (the timeouts are set on the logins themselves
  by the Supabase security file), and cannot keep server-side cursors between transactions.
"""
import os
import re

from django.core.exceptions import ImproperlyConfigured

from config.static_cache import add_cache_headers

from .web_secure import *  # noqa: F403
from .base import required
from . import public_site
from .web_common import set_upload_cap

_PROJECT_REF = re.compile(r'[a-z0-9]{20}')
_POOLER_HOST = re.compile(r'aws-[0-9]+-[a-z]{2}-[a-z]+-[0-9]+\.pooler\.supabase\.com')


def project_ref(value):
    if not _PROJECT_REF.fullmatch(value):
        raise ImproperlyConfigured('UCC_SUPABASE_PROJECT_REF must be the 20-character Supabase project reference.')
    return value


def pooler_host(value):
    if not _POOLER_HOST.fullmatch(value):
        raise ImproperlyConfigured('PGHOST must be your Supabase pooler host, e.g. aws-0-eu-west-1.pooler.supabase.com.')
    return value


public_site.configure(globals(), public_site.site_host(required('UCC_SITE_HOST')))
public_site.configure_email(globals(), os.environ)

# Vercel Functions refuse request bodies over 4.5 MB before Django sees them. Accept files up to
# 4,000,000 bytes so a whole upload (file + other fields + multipart overhead, at most
# 4,065,536 bytes) always reaches the website and gets a clear message instead.
VERCEL_MAX_UPLOAD_BYTES = 4_000_000
set_upload_cap(globals(), VERCEL_MAX_UPLOAD_BYTES)
UCC_TRUSTED_PROXIES = ()

_ref = project_ref(required('UCC_SUPABASE_PROJECT_REF'))
_host = pooler_host(required('PGHOST'))
if required('PGPORT') != '6543':
    raise ImproperlyConfigured("PGPORT must be 6543 (Supabase's transaction pooler) on Vercel.")
if required('PGDATABASE') != 'postgres':
    raise ImproperlyConfigured('PGDATABASE must be postgres on Supabase.')
for _alias, _role in (('default', required('UCC_RUNTIME_ROLE')), ('auth', required('UCC_AUTH_ROLE'))):
    DATABASES[_alias]['USER'] = f'{_role}.{_ref}'  # noqa: F405
    DATABASES[_alias]['HOST'] = _host  # noqa: F405
    DATABASES[_alias]['PORT'] = '6543'  # noqa: F405
    DATABASES[_alias]['OPTIONS']['sslmode'] = 'require'  # noqa: F405
    DATABASES[_alias]['DISABLE_SERVER_SIDE_CURSORS'] = True  # noqa: F405

# Static files are served by WhiteNoise straight from the app folders (Vercel has no build-time
# collectstatic step for this app); nothing is written to disk.
STATIC_ROOT = None
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = False
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # URLs carry the deployment stamp, so the files can be cached for a year (config.static_cache).
    'staticfiles': {'BACKEND': 'config.static_cache.VersionedStaticFilesStorage'},
}
WHITENOISE_ADD_HEADERS_FUNCTION = add_cache_headers
