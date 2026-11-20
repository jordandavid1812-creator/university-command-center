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
    # Open sign-up (owner's choice): anyone with an email can register, and the account works
    # only after its 6-digit email code is entered within 5 minutes (check accounts.E106).
    namespace['UCC_PUBLIC_SITE'] = True
    namespace['UCC_REQUIRE_INVITE'] = False
    namespace['UCC_SIGNUP_CODE'] = True
    # Launch step E (owner's choice): the shared AI key allows 10 requests per student and 200 for
    # the whole site per Lagos day. Local and test profiles keep 50 per student and no site limit.
    namespace['UCC_AI_REQUESTS_PER_DAY'] = 10
    namespace['UCC_AI_SITE_REQUESTS_PER_DAY'] = 200


_ADDRESS = re.compile(r'[a-z0-9._%+-]{1,64}@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,63}')
_APP_PASSWORD = re.compile(r'[A-Za-z0-9]{16}')
EMAIL_HOSTS = {'gmail.com': 'smtp.gmail.com'}
# Resend (owner's choice): sends from an address on the site's own domain, which the owner
# verifies in Resend with DNS records. SMTP login name is the literal word "resend" and the
# password is a Resend API key (re_...). Replies go to the public contact address.
RESEND_HOST = 'smtp.resend.com'
_RESEND_KEY = re.compile(r're_[A-Za-z0-9_]{16,128}')
REPLY_TO = 'unicommand.info@gmail.com'  # the public contact address (accounts.views.LEGAL_CONTACT)


def configure_email(namespace, environ):
    """Launch step C: real sign-up and password-reset email through the reviewed backend.

    Either Gmail: UCC_EMAIL_ADDRESS is the website's own Gmail address (a new account, never a
    personal one) and UCC_EMAIL_APP_PASSWORD its 16-character Google app password (spaces
    allowed, as Google shows it). Or Resend (owner's choice): UCC_EMAIL_ADDRESS is an address on
    UCC_SITE_HOST (e.g. noreply@unicommand.com.ng) and UCC_RESEND_API_KEY the Resend API key;
    replies go to REPLY_TO. Anything missing or malformed stops the website before it starts.
    """
    address = environ.get('UCC_EMAIL_ADDRESS', '').strip().lower()
    domain = address.split('@')[1] if _ADDRESS.fullmatch(address) else ''
    if domain and domain == namespace.get('UCC_SITE_HOST'):
        # Resend: e.g. noreply@unicommand.com.ng. Only the site's own (verified) domain is accepted.
        key = environ.get('UCC_RESEND_API_KEY', '').strip()
        if not _RESEND_KEY.fullmatch(key):
            raise ImproperlyConfigured('Set UCC_RESEND_API_KEY to the Resend API key (it starts with re_).')
        host, login, secret, reply_to = RESEND_HOST, 'resend', key, REPLY_TO
    elif domain in EMAIL_HOSTS:
        password = ''.join(environ.get('UCC_EMAIL_APP_PASSWORD', '').split())
        if not _APP_PASSWORD.fullmatch(password):
            raise ImproperlyConfigured('Set UCC_EMAIL_APP_PASSWORD to its 16-character Google app password.')
        host, login, secret, reply_to = EMAIL_HOSTS[domain], address, password, ''
    else:
        raise ImproperlyConfigured('Set UCC_EMAIL_ADDRESS to the website\'s own Gmail address, or to an address '
                                   'on the site\'s own domain (for Resend).')
    namespace.update(
        EMAIL_BACKEND='accounts.email_backend.ReviewedSMTPBackend',
        EMAIL_HOST=host, EMAIL_PORT=587, EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
        EMAIL_HOST_USER=login, EMAIL_HOST_PASSWORD=secret, EMAIL_TIMEOUT=10,
        DEFAULT_FROM_EMAIL=f'UniCommand <{address}>', SERVER_EMAIL=address, UCC_EMAIL_REPLY_TO=reply_to,
    )
