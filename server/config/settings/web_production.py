"""Public HTTPS website for the invited trial (launch milestone), on the step 2 server package.

Runs behind the Caddy proxy on the same server: Caddy holds the HTTPS certificate and is the
only thing that can reach this process. Everything that differs per server comes from the
environment and is checked here; a missing or unsafe value stops the website before it starts.

Real email (launch step C) uses the reviewed backend; check accounts.E105 refuses any other.
"""
import ipaddress
import os

from django.core.exceptions import ImproperlyConfigured

from .web_secure import *  # noqa: F403
from .base import required
from . import public_site
from .public_site import site_host  # noqa: F401  (kept importable here)


def proxy_network(value):
    """The private address range Caddy's requests come from (the server's internal network)."""
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise ImproperlyConfigured('UCC_TRUSTED_PROXY must be one network such as 172.30.0.0/24.') from None
    if not network.is_private or network.is_loopback or network.prefixlen < 16:
        raise ImproperlyConfigured('UCC_TRUSTED_PROXY must be a small private network (/16 or narrower).')
    return str(network)


public_site.configure(globals(), site_host(required('UCC_SITE_HOST')))
public_site.configure_email(globals(), os.environ)

# Only Caddy can reach this process, so its X-Forwarded-* headers are trusted: the scheme for
# HTTPS detection, and the client address for the sign-in limits (accounts.throttling).
UCC_TRUSTED_PROXIES = (proxy_network(required('UCC_TRUSTED_PROXY')),)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Static files come from STATIC_ROOT, filled by collectstatic when the server image is built.
STATIC_ROOT = os.environ.get('UCC_STATIC_ROOT') or STATIC_ROOT  # noqa: F405
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
