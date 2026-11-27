"""The Vercel profile (config.settings.web_vercel), checked in fresh processes.

Synthetic host names and project reference only. Nothing here connects to Vercel or Supabase.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from django.test import SimpleTestCase

SERVER = Path(__file__).resolve().parents[1]
PROFILE = 'config.settings.web_vercel'
GOOD = {'UCC_EMAIL_ADDRESS': 'ucc.synthetic.site@gmail.com', 'UCC_EMAIL_APP_PASSWORD': 'abcd efgh ijkl mnop',
        'UCC_SITE_HOST': 'ucc-synthetic.example.com', 'UCC_SUPABASE_PROJECT_REF': 'abcdefghijklmnopqrst',
        'PGHOST': 'aws-0-eu-west-1.pooler.supabase.com', 'PGPORT': '6543', 'PGDATABASE': 'postgres'}


def run(code='', env_updates=None, args=None):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE=PROFILE, PYTHONPATH=os.pathsep.join((str(SERVER.parent), str(SERVER))),
               PYTHONDONTWRITEBYTECODE='1', **GOOD)
    for name, value in (env_updates or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    command = [sys.executable] + (args if args is not None else ['-c', 'import django; django.setup()\n' + code])
    return subprocess.run(command, cwd=SERVER, env=env, capture_output=True, text=True, timeout=60)


class VercelProfileTests(SimpleTestCase):
    databases = {'default', 'runtime', 'auth'}  # the website test runner prepares them (run alone too)

    def test_deploy_check_is_completely_clean_with_real_email(self):
        """Launch step C: with the reviewed email backend, every check passes (warnings count as errors)."""
        result = run(args=['manage.py', 'check', '--deploy', '--fail-level', 'WARNING', '--settings=' + PROFILE])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('System check identified no issues (1 silenced).', result.stdout + result.stderr)

    def test_email_settings_are_required_and_checked(self):
        catch = ('import sys\nfrom django.core.exceptions import ImproperlyConfigured\n'
                 f'try:\n    import {PROFILE}\n'
                 'except ImproperlyConfigured as error:\n    print(error); sys.exit(3)\n')
        for env_updates, message in (({'UCC_EMAIL_ADDRESS': None}, 'UCC_EMAIL_ADDRESS'),
                                     ({'UCC_EMAIL_ADDRESS': 'someone@yahoo.com'}, 'UCC_EMAIL_ADDRESS'),
                                     ({'UCC_EMAIL_ADDRESS': 'not an address@gmail.com'}, 'UCC_EMAIL_ADDRESS'),
                                     ({'UCC_EMAIL_APP_PASSWORD': None}, 'UCC_EMAIL_APP_PASSWORD'),
                                     ({'UCC_EMAIL_APP_PASSWORD': 'short'}, 'UCC_EMAIL_APP_PASSWORD'),
                                     ({'UCC_EMAIL_APP_PASSWORD': 'abcd-efgh-ijkl-mnop'}, 'UCC_EMAIL_APP_PASSWORD')):
            with self.subTest(env=env_updates):
                caught = run(env_updates=env_updates, args=['-c', catch])
                self.assertEqual(caught.returncode, 3, caught.stderr)
                self.assertIn(message, caught.stdout)
        result = run('''import json
from django.conf import settings as s
print(json.dumps([s.EMAIL_BACKEND, s.EMAIL_HOST, s.EMAIL_PORT, s.EMAIL_USE_TLS, s.EMAIL_USE_SSL, s.EMAIL_HOST_USER,
                  s.EMAIL_HOST_PASSWORD == "abcdefghijklmnop", s.DEFAULT_FROM_EMAIL]))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['accounts.email_backend.ReviewedSMTPBackend', 'smtp.gmail.com', 587, True,
                                                     False, 'ucc.synthetic.site@gmail.com', True,
                                                     'UniCommand <ucc.synthetic.site@gmail.com>'])

    def test_public_site_rules_and_supabase_pooler_connections(self):
        result = run('''import json
from django.conf import settings as s
print(json.dumps({k: getattr(s, k) for k in ("ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "AUTH_LINK_ORIGIN",
    "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_PROXY_SSL_HEADER",
    "SESSION_COOKIE_NAME", "CSRF_COOKIE_NAME", "UCC_TRUSTED_PROXIES", "UCC_PUBLIC_SITE", "UCC_REQUIRE_INVITE", "UCC_SIGNUP_CODE",
    "UCC_AI_REQUESTS_PER_DAY", "UCC_AI_SITE_REQUESTS_PER_DAY",
    "MIDDLEWARE", "STATIC_ROOT", "WHITENOISE_USE_FINDERS", "DEBUG", "UCC_SECURE_PROFILE",
    "UCC_MAX_UPLOAD_BYTES", "FILE_UPLOAD_MAX_MEMORY_SIZE", "FILE_UPLOAD_HANDLERS")} |
    {"db": {alias: {k: s.DATABASES[alias][k] for k in ("NAME", "USER", "HOST", "PORT", "DISABLE_SERVER_SIDE_CURSORS",
                                                       "CONN_MAX_AGE")} | {"OPTIONS": s.DATABASES[alias]["OPTIONS"]}
            for alias in ("default", "auth")}}))''', {'UCC_RUNTIME_ROLE': 'ucc_runtime', 'UCC_AUTH_ROLE': 'ucc_auth'})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        host = GOOD['UCC_SITE_HOST']
        self.assertEqual((data['ALLOWED_HOSTS'], data['CSRF_TRUSTED_ORIGINS'], data['AUTH_LINK_ORIGIN']),
                         ([host], [f'https://{host}'], f'https://{host}'))
        self.assertEqual((data['SECURE_SSL_REDIRECT'], data['SECURE_HSTS_SECONDS'], data['SECURE_HSTS_INCLUDE_SUBDOMAINS']),
                         (True, 31_536_000, True))
        self.assertEqual((data['SESSION_COOKIE_NAME'], data['CSRF_COOKIE_NAME']), ('__Host-ucc_session', '__Host-ucc_csrf'))
        self.assertIsNone(data['SECURE_PROXY_SSL_HEADER'])  # Vercel's runtime sets the scheme itself
        self.assertEqual(data['UCC_TRUSTED_PROXIES'], [])  # REMOTE_ADDR is the visitor, set at Vercel's edge
        self.assertTrue(data['UCC_PUBLIC_SITE'] and data['UCC_SIGNUP_CODE'] and data['UCC_SECURE_PROFILE'])
        self.assertIs(data['UCC_REQUIRE_INVITE'], False)  # open sign-up
        self.assertEqual((data['UCC_AI_REQUESTS_PER_DAY'], data['UCC_AI_SITE_REQUESTS_PER_DAY']), (10, 200))
        self.assertIs(data['DEBUG'], False)
        self.assertEqual(data['MIDDLEWARE'][:2], ['django.middleware.security.SecurityMiddleware',
                                                  'whitenoise.middleware.WhiteNoiseMiddleware'])
        self.assertIsNone(data['STATIC_ROOT'])
        # Vercel refuses request bodies over 4.5 MB: files up to 4,000,000 bytes, whole request
        # at most 4,065,536, still held in memory only.
        self.assertEqual((data['UCC_MAX_UPLOAD_BYTES'], data['FILE_UPLOAD_MAX_MEMORY_SIZE']), (4_000_000, 4_065_536))
        self.assertLess(data['FILE_UPLOAD_MAX_MEMORY_SIZE'], 4_500_000)
        self.assertEqual(data['FILE_UPLOAD_HANDLERS'], ['django.core.files.uploadhandler.MemoryFileUploadHandler'])
        self.assertIs(data['WHITENOISE_USE_FINDERS'], True)
        for alias, role, statement_ms in (('default', 'ucc_runtime', 10000), ('auth', 'ucc_auth', 5000)):
            with self.subTest(alias=alias):
                db = data['db'][alias]
                self.assertEqual((db['NAME'], db['USER'], db['HOST'], db['PORT']),
                                 ('postgres', f'{role}.abcdefghijklmnopqrst', GOOD['PGHOST'], '6543'))
                self.assertEqual((db['DISABLE_SERVER_SIDE_CURSORS'], db['CONN_MAX_AGE']), (True, 0))
                self.assertEqual(db['OPTIONS']['sslmode'], 'require')
                self.assertIn(f'statement_timeout={statement_ms}', db['OPTIONS']['options'])  # still sent

    def test_unsafe_values_stop_the_website(self):
        catch = ('import sys\nfrom django.core.exceptions import ImproperlyConfigured\n'
                 'try:\n    import config.settings.web_vercel\n'
                 'except ImproperlyConfigured as error:\n    print(error); sys.exit(3)\n')
        cases = [({'UCC_SUPABASE_PROJECT_REF': None}, 'Set UCC_SUPABASE_PROJECT_REF'),
                 ({'UCC_SITE_HOST': 'localhost'}, 'UCC_SITE_HOST must be'),
                 ({'UCC_SITE_HOST': '*.vercel.app'}, 'UCC_SITE_HOST must be')]
        for ref in ('short', 'ABCDEFGHIJKLMNOPQRST', 'abcdefghijklmnopqrst.x', 'abcdefghijklmnopqrs-'):
            cases.append(({'UCC_SUPABASE_PROJECT_REF': ref}, 'UCC_SUPABASE_PROJECT_REF must be'))
        for host in ('db.abcdefghijklmnopqrst.supabase.co', 'evil.example.com', '127.0.0.1', 'aws-0-eu-west-1.pooler.supabase.com.evil.net'):
            cases.append(({'PGHOST': host}, 'PGHOST must be'))
        cases += [({'PGPORT': '5432'}, 'PGPORT must be 6543'), ({'PGDATABASE': 'other'}, 'PGDATABASE must be postgres')]
        for env_updates, message in cases:
            with self.subTest(env=env_updates):
                caught = run(env_updates=env_updates, args=['-c', catch])
                self.assertEqual(caught.returncode, 3, caught.stderr)
                self.assertIn(message, caught.stdout)

    def test_visitor_address_comes_from_vercel_not_from_forwarded_headers(self):
        result = run('''import json
from django.test import RequestFactory
from accounts.throttling import client_address
factory = RequestFactory()
request = factory.get("/", REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.9")
print(json.dumps(client_address(request)))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), '203.0.113.7')

    def test_static_files_and_https_before_any_database_work(self):
        result = run('''import json
from unittest.mock import patch
from django.test import Client
with patch("academics.ownership.require_runtime_role", side_effect=AssertionError("database used")):
    css = Client().get("/static/student_web/site.css", HTTP_HOST="ucc-synthetic.example.com", secure=True)
    plain = Client().get("/accounts/login/", HTTP_HOST="ucc-synthetic.example.com")
    other = Client().get("/", HTTP_HOST="evil.example.net")
print(json.dumps([css.status_code, css["Content-Type"], css.get("Strict-Transport-Security"),
                  plain.status_code, plain.get("Location"), other.status_code]))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        css, content_type, hsts, plain, location, other = json.loads(result.stdout)
        self.assertEqual(css, 200)
        self.assertTrue(content_type.startswith('text/css'))
        self.assertEqual(hsts, 'max-age=31536000; includeSubDomains')
        self.assertEqual((plain, location), (301, 'https://ucc-synthetic.example.com/accounts/login/'))
        self.assertEqual(other, 400)

    def test_local_starter_refuses_this_profile(self):
        result = subprocess.run([sys.executable, str(SERVER.parent / 'tools' / 'serve_local_website.py'), '--settings', PROFILE],
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
