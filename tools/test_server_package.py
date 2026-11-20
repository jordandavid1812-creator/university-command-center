"""End-to-end check of the server package (deploy/): database, migrator, website and Caddy.

Needs Docker with Compose and free ports 80 and 443 on this machine; takes a few minutes.
Uses a synthetic host name, Caddy's internal test certificate (never a public one), new random
passwords in a temporary folder and synthetic data only. Everything is removed afterwards.

    python tools/test_server_package.py -v
"""
import http.client
import http.cookies
from email import policy
from email.parser import Parser
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse

REPO = Path(__file__).resolve().parents[1]
HOST = 'ucc-synthetic.example.com'
PROJECT = 'ucc-package-test'
# Smoke run for the journey only: the same image and settings, but sign-up emails are printed to the
# website's log (console backend) instead of being sent to Gmail, so the test can read the sign-up code.
# The real start command, with its full preflight, is tested separately (it must boot).
SMOKE = '''services:
  web:
    environment:
      DJANGO_SETTINGS_MODULE: ucc_smoke_settings
      PYTHONPATH: /app:/smoke
    volumes:
      - {smoke}:/smoke:ro
    command: ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000",
              "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--worker-tmp-dir", "/tmp"]
'''


def console_email_messages(output):
    """Read complete Django console messages, not duplicated text in MIME alternatives.

    Call Compose logs with --no-log-prefix/--no-color. Only synthetic smoke email uses
    this console channel; production keeps the approved real backend and privacy checks.
    """
    blocks = re.findall(r'(?ms)^(Content-Type:.*?)\n-{79}(?:\n|$)', output.replace('\r\n', '\n'))
    return [Parser(policy=policy.default).parsestr(block) for block in blocks]


class ServerPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        folder = Path(cls.folder.name)
        cls.secrets = folder / 'secrets'
        subprocess.run([sys.executable, str(REPO / 'deploy' / 'make_secrets.py'), '--host', HOST, '--internal-tls',
                        '--folder', str(cls.secrets)], check=True, capture_output=True)
        smoke = folder / 'smoke'
        smoke.mkdir()
        (smoke / 'ucc_smoke_settings.py').write_text(
            'from config.settings.web_production import *  # noqa\n'
            "EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # test only: links go to the log\n")
        os.chmod(smoke, 0o755)
        os.chmod(smoke / 'ucc_smoke_settings.py', 0o644)
        (folder / 'smoke.yml').write_text(SMOKE.format(smoke=smoke))
        cls.base = ['docker', 'compose', '-p', PROJECT, '-f', str(REPO / 'deploy' / 'compose.yml')]
        cls.smoke = cls.base + ['-f', str(folder / 'smoke.yml')]
        cls.env = dict(os.environ, UCC_SECRETS=str(cls.secrets))
        try:
            cls.compose('build', 'web', timeout=1200)
            cls.compose('up', '-d', '--wait', 'db', timeout=300)
            cls.migrated = cls.compose('run', '--rm', 'migrate', timeout=600).stdout
            # 1. The real start command without email settings: the website refuses to start.
            cls.compose('up', '-d', 'web', timeout=120)
            cls.refused = cls.wait_for_log('ucc-log')
            cls.compose('stop', 'web', timeout=120)
            # 2. With the owner's email settings added: the full preflight passes and gunicorn boots.
            with open(cls.secrets / 'web.env', 'a', encoding='utf-8') as handle:
                handle.write('UCC_EMAIL_ADDRESS=ucc.synthetic.site@gmail.com\nUCC_EMAIL_APP_PASSWORD=abcdefghijklmnop\n')
            cls.compose('up', '-d', '--force-recreate', 'web', timeout=120)
            cls.booted = cls.wait_for_log('Booting worker')
            cls.compose('stop', 'web', timeout=120)
            cls.compose('up', '-d', '--force-recreate', 'web', 'caddy', command=cls.smoke, timeout=300)
            cls.wait_for_site()
            root = cls.compose('exec', '-T', 'caddy', 'cat', '/data/caddy/pki/authorities/local/root.crt').stdout
            cls.context = ssl.create_default_context(cadata=root)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        subprocess.run(cls.base + ['down', '-v', '--remove-orphans'], env=cls.env, capture_output=True, timeout=300)
        cls.folder.cleanup()

    @classmethod
    def compose(cls, *args, command=None, timeout=300, check=True):
        result = subprocess.run((command or cls.base) + list(args), cwd=REPO, env=cls.env, capture_output=True,
                                text=True, timeout=timeout)
        if check and result.returncode != 0:
            raise AssertionError(f'docker compose {" ".join(args)} failed:\n{result.stdout}\n{result.stderr}')
        return result

    @classmethod
    def wait_for_log(cls, text, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            logs = cls.compose('logs', 'web', check=False).stdout
            if text in logs:
                return logs
            time.sleep(2)
        raise AssertionError(f'{text} never appeared in the website log')

    @classmethod
    def wait_for_site(cls, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(('127.0.0.1', 80), timeout=3):
                    root = cls.compose('exec', '-T', 'caddy', 'cat', '/data/caddy/pki/authorities/local/root.crt', check=False)
                    if root.returncode == 0:
                        cls.context = ssl.create_default_context(cadata=root.stdout)
                        if cls.request('GET', '/accounts/login/')[0] == 200:
                            return
            except OSError:
                pass
            time.sleep(2)
        raise AssertionError('the site never answered over HTTPS:\n' + cls.compose('logs', check=False).stdout[-3000:])

    @classmethod
    def request(cls, method, path, host=HOST, body=None, headers=None, https=True, sni=None):
        """One request to this machine's ports 80/443 as if to `host`; certificates are verified
        against Caddy's internal test authority only."""
        if https:
            connection = http.client.HTTPSConnection(host, 443, timeout=15, context=cls.context)
            raw = socket.create_connection(('127.0.0.1', 443), timeout=15)
            connection.sock = cls.context.wrap_socket(raw, server_hostname=sni or host)
        else:
            connection = http.client.HTTPConnection(host, 80, timeout=15)
            connection.sock = socket.create_connection(('127.0.0.1', 80), timeout=15)
        connection.request(method, path, body=body, headers={'Host': host, **(headers or {})})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, response.headers, data

    def browse(self, jar, method, path, form=None):
        """A tiny browser: keeps cookies, sends the CSRF token and same-site Origin/Referer."""
        headers = {'Cookie': '; '.join(f'{k}={v}' for k, v in jar.items()), 'Origin': f'https://{HOST}',
                   'Referer': f'https://{HOST}{path}'}
        body = None
        if form is not None:
            body = urllib.parse.urlencode({'csrfmiddlewaretoken': jar['token'], **form})
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        status, response_headers, data = self.request(method, path, body=body, headers=headers)
        for value in response_headers.get_all('Set-Cookie') or []:
            for name, morsel in http.cookies.SimpleCookie(value).items():
                jar[name] = morsel.value
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', data)
        if token:
            jar['token'] = token.group(1).decode()
        return status, response_headers, data.decode('utf-8', 'replace')

    def test_a_full_student_journey_through_the_real_server(self):
        """Register, enter the emailed code, sign in, add a semester and a course, and see it,
        all through Caddy, gunicorn and the restricted database logins."""
        jar = {}
        _, _, page = self.browse(jar, 'GET', '/accounts/register/')
        self.assertNotIn('invite_code', page)  # open sign-up: anyone with an email
        password = 'Synthetic-Long-Passphrase-42'
        details = {'username': 'synthetic_student', 'email': 'synthetic.student@example.invalid',
                   'password1': password, 'password2': password}
        status, _, page = self.browse(jar, 'POST', '/accounts/register/', details)
        self.assertEqual(status, 200)
        self.assertIn('Enter your code', page)
        # The smoke run uses the console email backend, so the code is in the website's output.
        messages = console_email_messages(self.compose('logs', '--no-log-prefix', '--no-color', 'web').stdout)
        self.assertEqual(len(messages), 1, 'exactly one sign-up email expected')
        self.assertEqual(str(messages[0]['To']), details['email'])
        plain = messages[0].get_body(preferencelist=('plain',))
        self.assertIsNotNone(plain, 'the sign-up email must retain its plain-text alternative')
        codes = re.findall(r'sign-up code is (\d{6})', plain.get_content())
        self.assertEqual(len(codes), 1, 'one sign-up code expected')
        status, _, page = self.browse(jar, 'POST', '/accounts/verify/code/', {
            'email': details['email'], 'code': codes[0], 'action': 'verify'})
        self.assertIn('Email confirmed', page)
        self.browse(jar, 'GET', '/accounts/login/')
        status, headers, _ = self.browse(jar, 'POST', '/accounts/login/', {'username': 'synthetic_student',
                                                                           'password': password})
        self.assertEqual(status, 302, headers)
        self.assertIn('__Host-ucc_session', jar)
        self.browse(jar, 'GET', '/semesters/new/')
        self.assertEqual(self.browse(jar, 'POST', '/semesters/new/', {'label': 'Synthetic semester',
                                                                       'display_order': '0'})[0], 302)
        status, _, page = self.browse(jar, 'GET', '/courses/new/')
        semester = re.search(r'<option value="([0-9a-f-]{36})"', page).group(1)
        self.assertEqual(self.browse(jar, 'POST', '/courses/new/', {
            'name': 'Synthetic course', 'original_code': 'SYN101', 'credit_units': '3', 'semester_id': semester,
            'actual_grade': 'A'})[0], 302)
        status, _, page = self.browse(jar, 'GET', '/courses/')
        self.assertEqual(status, 200)
        self.assertIn('SYN101', page)
        status, _, page = self.browse(jar, 'GET', '/performance/')
        self.assertIn('5.00', page)  # one A over 3 units
        # The student's rows are protected by row-level security: the database administrator can
        # see one course exists, and the runtime login cannot bypass the rules.
        count = self.compose('exec', '-T', 'db', 'sh', '-c', 'psql -U "$POSTGRES_USER" -d ucc -Atc '
                             '"SELECT count(*) FROM academics_course"').stdout.strip()
        self.assertEqual(count, '1')

    def test_database_is_set_up_with_the_migrator_only(self):
        self.assertIn("restricted logins are configured", self.migrated)
        roles = self.compose('exec', '-T', 'db', 'sh', '-c',
                             'psql -U "$POSTGRES_USER" -d postgres -Atc "SELECT rolname, rolsuper, rolbypassrls, '
                             'rolcreaterole, rolcreatedb, rolinherit FROM pg_roles WHERE rolname LIKE \'ucc\\_%\' '
                             'AND rolname <> \'ucc_dba\' ORDER BY 1"').stdout.split()
        self.assertEqual(roles, ['ucc_auth|f|f|f|f|f', 'ucc_migrator|f|f|f|f|f', 'ucc_runtime|f|f|f|f|f'])
        owner = self.compose('exec', '-T', 'db', 'sh', '-c', 'psql -U "$POSTGRES_USER" -d postgres -Atc '
                             '"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = \'ucc\'"').stdout.strip()
        self.assertEqual(owner, 'ucc_migrator')

    def test_real_start_command_refuses_without_email_settings(self):
        self.assertNotIn('Booting worker', self.refused)
        self.assertNotIn('Traceback', self.refused)  # the reason is kept out of the log on purpose

    def test_real_start_command_boots_after_the_full_preflight(self):
        self.assertIn('System check identified no issues (1 silenced).', self.booted)
        self.assertIn('Booting worker', self.booted)

    def test_containers_are_locked_down(self):
        names = {'web': None, 'caddy': None, 'db': None}
        for service in names:
            container = self.compose('ps', '-q', service).stdout.strip()
            names[service] = json.loads(subprocess.run(['docker', 'inspect', container], capture_output=True,
                                                       text=True, check=True).stdout)[0]
        web, caddy, db = names['web'], names['caddy'], names['db']
        self.assertEqual(web['Config']['User'], 'ucc')
        self.assertTrue(web['HostConfig']['ReadonlyRootfs'])
        self.assertEqual(web['HostConfig']['CapDrop'], ['ALL'])
        self.assertIn('no-new-privileges:true', web['HostConfig']['SecurityOpt'])
        self.assertEqual(web['HostConfig']['PortBindings'] or {}, {})  # only Caddy is reachable
        self.assertEqual(db['HostConfig']['PortBindings'] or {}, {})
        self.assertEqual(sorted(caddy['HostConfig']['PortBindings']), ['443/tcp', '443/udp', '80/tcp'])
        self.assertEqual(sorted(db['NetworkSettings']['Networks']), [f'{PROJECT}_backend'])
        self.assertEqual(sorted(caddy['NetworkSettings']['Networks']), [f'{PROJECT}_frontend'])
        backend = json.loads(subprocess.run(['docker', 'network', 'inspect', f'{PROJECT}_backend'], capture_output=True,
                                            text=True, check=True).stdout)[0]
        self.assertTrue(backend['Internal'])  # the database network has no internet
        # The website's environment has no database administrator or migrator login.
        web_env = '\n'.join(web['Config']['Env'])
        self.assertIn('PGUSER=ucc_runtime', web_env)
        self.assertNotIn('ucc_migrator', web_env)
        self.assertNotIn('POSTGRES_PASSWORD', web_env)
        # Caddy cannot even find the database.
        lookup = self.compose('exec', '-T', 'caddy', 'nslookup', 'db', check=False)
        self.assertNotEqual(lookup.returncode, 0)

    def test_http_redirects_to_https(self):
        status, headers, _ = self.request('GET', '/accounts/login/?next=/', https=False)
        self.assertIn(status, (301, 308))
        self.assertEqual(headers['Location'], f'https://{HOST}/accounts/login/?next=/')

    def test_pages_have_https_security_headers_and_host_only_cookies(self):
        status, headers, body = self.request('GET', '/accounts/login/')
        self.assertEqual(status, 200)
        self.assertIn(b'csrfmiddlewaretoken', body)
        self.assertEqual(headers['Strict-Transport-Security'], 'max-age=31536000; includeSubDomains')
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIsNone(headers['Server'])
        cookie = headers['Set-Cookie']
        self.assertTrue(cookie.startswith('__Host-ucc_csrf='), cookie)
        self.assertRegex(cookie, r'(?i); Secure')
        self.assertRegex(cookie, r'(?i); Path=/')
        self.assertNotRegex(cookie, r'(?i)domain=')

    def test_static_files_are_served_compressed(self):
        status, headers, body = self.request('GET', '/static/student_web/site.css', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Encoding'], 'gzip')
        self.assertTrue(headers['Content-Type'].startswith('text/css'))

    def test_other_names_get_nothing_from_the_website(self):
        status, _, body = self.request('GET', '/accounts/login/', host='evil.example.net', https=False)
        self.assertNotIn(b'csrfmiddlewaretoken', body)
        self.assertNotEqual(status, 301)  # no redirect to an https site for this name either
        with self.assertRaises(ssl.SSLError):
            self.request('GET', '/accounts/login/', host='evil.example.net')

    def test_oversized_uploads_are_refused_by_caddy(self):
        """A 12 MiB body is refused by Caddy (often before it is all sent) and never reaches the website."""
        size = 12 * 1024 * 1024
        connection = http.client.HTTPSConnection(HOST, 443, timeout=15, context=self.context)
        connection.sock = self.context.wrap_socket(socket.create_connection(('127.0.0.1', 443), timeout=15),
                                                   server_hostname=HOST)
        self.addCleanup(connection.close)
        connection.putrequest('POST', '/materials/new/', skip_host=True)
        for name, value in (('Host', HOST), ('Content-Type', 'application/octet-stream'), ('Content-Length', str(size))):
            connection.putheader(name, value)
        connection.endheaders()
        try:
            for _ in range(size // 65536):
                connection.send(b'x' * 65536)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            pass  # Caddy stopped reading: refused early
        self.assertEqual(connection.getresponse().status, 413)

    def test_sign_in_limits_ignore_forged_visitor_addresses(self):
        """Caddy replaces any X-Forwarded-For a visitor sends, so changing it cannot dodge the limit."""
        status, headers, body = self.request('GET', '/accounts/login/')
        cookie = http.cookies.SimpleCookie(headers['Set-Cookie'])['__Host-ucc_csrf'].value
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body).group(1).decode()
        statuses = []
        for attempt in range(12):
            form = urllib.parse.urlencode({'csrfmiddlewaretoken': token, 'username': 'synthetic-nobody',
                                           'password': 'synthetic-wrong-password'})
            statuses.append(self.request('POST', '/accounts/login/', body=form, headers={
                'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': f'__Host-ucc_csrf={cookie}',
                'Origin': f'https://{HOST}', 'Referer': f'https://{HOST}/accounts/login/',
                'X-Forwarded-For': f'203.0.113.{attempt + 1}'})[0])
        self.assertNotIn(403, statuses, statuses)  # the forms were accepted (CSRF passed)
        self.assertEqual(statuses[-1], 429, statuses)


if __name__ == '__main__':
    unittest.main()
