"""Rules every public HTTPS profile shares (web_production on the server, web_vercel on Vercel).

Kept in one place so the two hosting options cannot drift apart.
"""
import re

from django.core.exceptions import ImproperlyConfigured

_HOST = re.compile(r'(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')


def site_host(value):
    """One lowercase public domain name such as ucc-student.com (no scheme, port, path or *)."""
    if not _HOST.fullmatch(value) or value.endswith(('.localhost', '.local', '.invalid', '.test')):
        raise ImproperlyConfigured('UCC_SITE_HOST must be one public domain name, e.g. ucc-student.com.')
    return value


def configure(namespace, host):
    namespace['UCC_SITE_HOST'] = host
    namespace['ALLOWED_HOSTS'] = [host]
    namespace['CSRF_TRUSTED_ORIGINS'] = [f'https://{host}']
    namespace['AUTH_LINK_ORIGIN'] = f'https://{host}'
    namespace['SECURE_SSL_REDIRECT'] = True
    # Browsers remember to use HTTPS for a year, on the domain and every subdomain (the domain is
    # used for this website only). The browser preload list stays off on purpose: leaving it takes
    # months, so security.W021 is silenced as a deliberate choice, not an oversight.
    namespace['SECURE_HSTS_SECONDS'] = 31_536_000
    namespace['SECURE_HSTS_INCLUDE_SUBDOMAINS'] = True
    namespace['SECURE_HSTS_PRELOAD'] = False
    namespace['SILENCED_SYSTEM_CHECKS'] = ['security.W021']
    # __Host- cookies are refused by browsers unless they are HTTPS-only, for this exact host and
    # the whole site, so no other subdomain can set or replace them.
    namespace['SESSION_COOKIE_NAME'] = '__Host-ucc_session'
    namespace['CSRF_COOKIE_NAME'] = '__Host-ucc_csrf'
    namespace['SESSION_COOKIE_SECURE'] = True
    namespace['CSRF_COOKIE_SECURE'] = True
    # Style sheets and scripts are served by WhiteNoise before any database work happens.
    middleware = list(namespace['MIDDLEWARE'])
    middleware.insert(middleware.index('django.middleware.security.SecurityMiddleware') + 1,
                      'whitenoise.middleware.WhiteNoiseMiddleware')
    namespace['MIDDLEWARE'] = middleware
    namespace['UCC_LOCAL_STATIC'] = False
    # Launch step 3: only people with an invite code can create an account (check accounts.E106).
    namespace['UCC_PUBLIC_SITE'] = True
    namespace['UCC_REQUIRE_INVITE'] = True
