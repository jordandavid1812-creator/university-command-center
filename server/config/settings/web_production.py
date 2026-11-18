"""Public HTTPS website for the invited trial (launch milestone).

Runs behind the Caddy proxy on the same server: Caddy holds the HTTPS certificate and is the
only thing that can reach this process. Everything that differs per server comes from the
environment and is checked here; a missing or unsafe value stops the website before it starts.

Still blocked by check accounts.E105 until a reviewed real-email backend is approved (launch
step 4): without real email, sign-up and password-reset links would have nowhere safe to go.
"""
import ipaddress
import os
import re

from django.core.exceptions import ImproperlyConfigured

from .web_secure import *  # noqa: F403
from .base import required

_HOST = re.compile(r'(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')


def site_host(value):
    """One lowercase public domain name such as ucc-student.com (no scheme, port, path or *)."""
    if not _HOST.fullmatch(value) or value.endswith(('.localhost', '.local', '.invalid', '.test')):
        raise ImproperlyConfigured('UCC_SITE_HOST must be one public domain name, e.g. ucc-student.com.')
    return value


def proxy_network(value):
    """The private address range Caddy's requests come from (the server's internal network)."""
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise ImproperlyConfigured('UCC_TRUSTED_PROXY must be one network such as 172.30.0.0/24.') from None
    if not network.is_private or network.is_loopback or network.prefixlen < 16:
        raise ImproperlyConfigured('UCC_TRUSTED_PROXY must be a small private network (/16 or narrower).')
    return str(network)


UCC_SITE_HOST = site_host(required('UCC_SITE_HOST'))
ALLOWED_HOSTS = [UCC_SITE_HOST]
CSRF_TRUSTED_ORIGINS = [f'https://{UCC_SITE_HOST}']
AUTH_LINK_ORIGIN = f'https://{UCC_SITE_HOST}'

# Only Caddy can reach this process, so its X-Forwarded-* headers are trusted: the scheme for
# HTTPS detection, and the client address for the sign-in limits (accounts.throttling).
UCC_TRUSTED_PROXIES = (proxy_network(required('UCC_TRUSTED_PROXY')),)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
# Browsers remember to use HTTPS for a year, on the domain and every subdomain (the domain is
# used for this website only). The browser preload list stays off on purpose: leaving it takes
# months, so security.W021 is silenced as a deliberate choice, not an oversight.
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ['security.W021']
# __Host- cookies are refused by browsers unless they are HTTPS-only, for this exact host and
# the whole site, so no other subdomain can set or replace them.
SESSION_COOKIE_NAME = '__Host-ucc_session'
CSRF_COOKIE_NAME = '__Host-ucc_csrf'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Style sheets and scripts are served by WhiteNoise from STATIC_ROOT (filled by collectstatic
# when the server image is built), before any database work happens.
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
MIDDLEWARE.insert(MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
                  'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT = os.environ.get('UCC_STATIC_ROOT') or STATIC_ROOT  # noqa: F405
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
UCC_LOCAL_STATIC = False
