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


_ADDRESS = re.compile(r'[a-z0-9._%+-]{1,64}@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,63}')
_APP_PASSWORD = re.compile(r'[A-Za-z0-9]{16}')
EMAIL_HOSTS = {'gmail.com': 'smtp.gmail.com'}


def configure_email(namespace, environ):
    """Launch step C: real sign-up and password-reset email through the reviewed backend.

    UCC_EMAIL_ADDRESS is the website's own Gmail address (a new account, never a personal one)
    and UCC_EMAIL_APP_PASSWORD its 16-character Google app password (spaces allowed, as Google
    shows it). Anything missing or malformed stops the website before it starts.
    """
    address = environ.get('UCC_EMAIL_ADDRESS', '').strip().lower()
    password = ''.join(environ.get('UCC_EMAIL_APP_PASSWORD', '').split())
    if not _ADDRESS.fullmatch(address) or address.split('@')[1] not in EMAIL_HOSTS:
        raise ImproperlyConfigured('Set UCC_EMAIL_ADDRESS to the website\'s own Gmail address.')
    if not _APP_PASSWORD.fullmatch(password):
        raise ImproperlyConfigured('Set UCC_EMAIL_APP_PASSWORD to its 16-character Google app password.')
    namespace.update(
        EMAIL_BACKEND='accounts.email_backend.ReviewedSMTPBackend',
        EMAIL_HOST=EMAIL_HOSTS[address.split('@')[1]], EMAIL_PORT=587, EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
        EMAIL_HOST_USER=address, EMAIL_HOST_PASSWORD=password, EMAIL_TIMEOUT=10,
        DEFAULT_FROM_EMAIL=f'University Command Center <{address}>', SERVER_EMAIL=address,
    )
