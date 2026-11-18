"""The public launch profile (config.settings.web_production), checked in fresh processes.

Synthetic host names only. Nothing here connects to a real server or sends email.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from django.test import SimpleTestCase

SERVER = Path(__file__).resolve().parents[1]
PROFILE = 'config.settings.web_production'
GOOD = {'UCC_SITE_HOST': 'ucc-synthetic.example.com', 'UCC_TRUSTED_PROXY': '172.30.0.0/24'}


def run(code='', env_updates=None, args=None):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE=PROFILE, PYTHONPATH=os.pathsep.join((str(SERVER.parent), str(SERVER))), PYTHONDONTWRITEBYTECODE='1', **GOOD)
    for name, value in (env_updates or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    command = [sys.executable] + (args if args is not None else ['-c', 'import django; django.setup()\n' + code])
    return subprocess.run(command, cwd=SERVER, env=env, capture_output=True, text=True, timeout=60)


class ProductionProfileTests(SimpleTestCase):
    databases = {'default', 'runtime', 'auth'}  # the website test runner prepares them (run alone too)

    def test_deploy_check_is_clean_except_the_email_gate(self):
        """Only accounts.E105 remains: real email must be approved (launch step 4) before launch."""
        result = run(args=['manage.py', 'check', '--deploy', '--settings=' + PROFILE])
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn('(accounts.E105)', output)
        self.assertIn('System check identified 1 issue (1 silenced).', output)
        self.assertNotIn('WARNINGS', output)

    def test_https_cookies_hosts_and_order(self):
        result = run('''import json
from django.conf import settings as s
print(json.dumps({k: getattr(s, k) for k in ("ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "AUTH_LINK_ORIGIN",
    "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD",
    "SECURE_PROXY_SSL_HEADER", "SESSION_COOKIE_NAME", "CSRF_COOKIE_NAME", "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE", "SESSION_COOKIE_HTTPONLY", "CSRF_COOKIE_HTTPONLY", "DEBUG", "UCC_TRUSTED_PROXIES",
    "UCC_LOCAL_STATIC", "MIDDLEWARE", "STORAGES", "EMAIL_BACKEND", "UCC_SECURE_PROFILE",
    "UCC_PUBLIC_SITE", "UCC_REQUIRE_INVITE")}))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        host = GOOD['UCC_SITE_HOST']
        self.assertEqual(data['ALLOWED_HOSTS'], [host])
        self.assertEqual(data['CSRF_TRUSTED_ORIGINS'], [f'https://{host}'])
        self.assertEqual(data['AUTH_LINK_ORIGIN'], f'https://{host}')
        self.assertIs(data['SECURE_SSL_REDIRECT'], True)
        self.assertEqual((data['SECURE_HSTS_SECONDS'], data['SECURE_HSTS_INCLUDE_SUBDOMAINS'], data['SECURE_HSTS_PRELOAD']),
                         (31_536_000, True, False))
        self.assertEqual(data['SECURE_PROXY_SSL_HEADER'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        self.assertEqual((data['SESSION_COOKIE_NAME'], data['CSRF_COOKIE_NAME']), ('__Host-ucc_session', '__Host-ucc_csrf'))
        self.assertTrue(all(data[k] is True for k in ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
                                                      'SESSION_COOKIE_HTTPONLY', 'CSRF_COOKIE_HTTPONLY', 'UCC_SECURE_PROFILE')))
        self.assertIs(data['DEBUG'], False)
        self.assertIs(data['UCC_LOCAL_STATIC'], False)
        self.assertIs(data['UCC_PUBLIC_SITE'], True)
        self.assertIs(data['UCC_REQUIRE_INVITE'], True)  # launch step 3: invite-only sign-up
        self.assertEqual(data['UCC_TRUSTED_PROXIES'], ['172.30.0.0/24'])
        self.assertEqual(data['MIDDLEWARE'][:3], ['django.middleware.security.SecurityMiddleware',
                                                  'whitenoise.middleware.WhiteNoiseMiddleware',
                                                  'accounts.middleware.ContentSecurityPolicyMiddleware'])
        self.assertEqual(data['STORAGES']['staticfiles']['BACKEND'], 'whitenoise.storage.CompressedStaticFilesStorage')
        # Console email would print sign-up links into server logs; E105 blocks it (see above).
        self.assertEqual(data['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')

    def test_unsafe_host_and_proxy_values_stop_the_website(self):
        cases = [({'UCC_SITE_HOST': None}, 'Set UCC_SITE_HOST')]
        for host in ('', '*', 'localhost', '127.0.0.1', 'https://ucc.example.com', 'ucc.example.com:443',
                     'UCC.example.com', 'ucc.example.com/', '.example.com', 'ucc.localhost', 'ucc.test', 'nodot'):
            cases.append(({'UCC_SITE_HOST': host}, 'Set UCC_SITE_HOST' if host == '' else 'UCC_SITE_HOST must be'))
        cases.append(({'UCC_TRUSTED_PROXY': None}, 'Set UCC_TRUSTED_PROXY'))
        for proxy in ('0.0.0.0/0', '8.8.8.0/24', '10.0.0.0/8', '172.30.0.1/24', '127.0.0.1/32', 'caddy', '::/0'):
            cases.append(({'UCC_TRUSTED_PROXY': proxy}, 'UCC_TRUSTED_PROXY must be'))
        # The privacy logger hides uncaught error text on purpose, so the reason is read by
        # catching the error; an uncaught run must still stop without printing any details.
        catch = ('import sys\nfrom django.core.exceptions import ImproperlyConfigured\n'
                 'try:\n    import config.settings.web_production\n'
                 'except ImproperlyConfigured as error:\n    print(error); sys.exit(3)\n')
        for env_updates, message in cases:
            with self.subTest(env=env_updates):
                caught = run(env_updates=env_updates, args=['-c', catch])
                self.assertEqual(caught.returncode, 3, caught.stderr)
                self.assertIn(message, caught.stdout)
                uncaught = run('', env_updates)
                self.assertNotEqual(uncaught.returncode, 0)
                self.assertNotIn('Traceback', uncaught.stderr)

    def test_http_is_redirected_and_unknown_hosts_refused_before_any_database_work(self):
        result = run('''import json
from unittest.mock import patch
from django.test import Client
with patch("academics.ownership.require_runtime_role", side_effect=AssertionError("database used")):
    plain = Client().get("/accounts/login/?next=/", HTTP_HOST="ucc-synthetic.example.com")
    other = Client().get("/", HTTP_HOST="evil.example.net")
print(json.dumps([plain.status_code, plain.get("Location"), other.status_code]))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        plain, location, other = json.loads(result.stdout)
        self.assertEqual((plain, location), (301, 'https://ucc-synthetic.example.com/accounts/login/?next=/'))
        self.assertEqual(other, 400)

    def test_static_files_are_served_without_the_database(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {'UCC_STATIC_ROOT': folder}
            collected = run(env_updates=env, args=['manage.py', 'collectstatic', '--noinput', '-v', '0', '--settings=' + PROFILE])
            self.assertEqual(collected.returncode, 0, collected.stderr)
            self.assertTrue((Path(folder) / 'student_web' / 'site.css.gz').is_file())  # compressed copies made
            result = run('''import json
from unittest.mock import patch
from django.test import Client
with patch("academics.ownership.require_runtime_role", side_effect=AssertionError("database used")):
    response = Client().get("/static/student_web/site.js", HTTP_HOST="ucc-synthetic.example.com",
                            HTTP_X_FORWARDED_PROTO="https")
print(json.dumps([response.status_code, response["Content-Type"], response.get("Strict-Transport-Security"),
                  response.get("X-Content-Type-Options")]))''', env)
            self.assertEqual(result.returncode, 0, result.stderr)
            status, content_type, hsts, nosniff = json.loads(result.stdout)
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith('text/javascript'), content_type)
            self.assertEqual(hsts, 'max-age=31536000; includeSubDomains')
            self.assertEqual(nosniff, 'nosniff')

    def test_sign_in_limits_use_the_real_visitor_address_only_through_the_proxy(self):
        result = run('''import json
from django.test import RequestFactory
from accounts.throttling import client_address
factory = RequestFactory()
through_proxy = factory.get("/", REMOTE_ADDR="172.30.0.2", HTTP_X_FORWARDED_FOR="203.0.113.7")
spoofed = factory.get("/", REMOTE_ADDR="198.51.100.9", HTTP_X_FORWARDED_FOR="203.0.113.7")
print(json.dumps([client_address(through_proxy), client_address(spoofed)]))''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['203.0.113.7', '198.51.100.9'])

    def test_gunicorn_loads_the_application(self):
        result = run(args=['-m', 'gunicorn', '--check-config', 'config.wsgi:application'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_local_starter_still_refuses_this_profile(self):
        result = subprocess.run([sys.executable, str(SERVER.parent / 'tools' / 'serve_local_website.py'), '--settings', PROFILE],
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr)
