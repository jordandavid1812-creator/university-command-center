"""The Vercel settings (config.settings.web_vercel) against Supabase's database through a
transaction-mode pooler, like Supabase's own (Supavisor) on port 6543.

Needs Docker and the Django requirements. Containers: ghcr.io/supabase/postgres with the
supabase/migrations files and a private test file applied, and two PgBouncer poolers in
transaction mode (one per website login) that, like Supavisor, ignore per-connection options and
keep no session state or prepared statements between transactions. Synthetic data only; all
removed afterwards. Only the pooler addresses, plain user names and TLS are swapped for the test.

    python tools/test_vercel_stack.py -v
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_supabase_sql as supabase

REPO = Path(__file__).resolve().parents[1]
POOLER_IMAGE = 'mirror.gcr.io/edoburu/pgbouncer:v1.24.1-p1'
NETWORK = 'ucc-vercel-test'
SUPA, RUNTIME_POOL, AUTH_POOL = 'ucc-vtest-supabase', 'ucc-vtest-pool-runtime', 'ucc-vtest-pool-auth'
HOST = 'ucc-synthetic.example.com'
EMAIL = {'UCC_EMAIL_ADDRESS': 'ucc.synthetic.site@gmail.com', 'UCC_EMAIL_APP_PASSWORD': 'abcdefghijklmnop'}
POOLER_INI = '''[databases]
postgres = host={supa} port=5432 dbname=postgres user={user} password={password}
[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6543
auth_type = any
pool_mode = transaction
default_pool_size = 2
max_prepared_statements = 0
ignore_startup_parameters = options,extra_float_digits
server_reset_query =
'''
SETTINGS = '''from config.settings.web_vercel import *  # noqa
# Test only: local poolers instead of Supabase's (plain user names, no TLS on the local network).
DATABASES['default'].update(HOST='127.0.0.1', PORT='{runtime_port}', USER='ucc_runtime')
DATABASES['auth'].update(HOST='127.0.0.1', PORT='{auth_port}', USER='ucc_auth')
for _alias in ('default', 'auth'):
    DATABASES[_alias]['OPTIONS']['sslmode'] = 'disable'
'''
JOURNEY = r'''
import json, os, re, sys
from urllib.parse import urlsplit
sys.path[:0] = [os.environ["UCC_SETTINGS_DIR"], os.environ["UCC_SERVER"], os.environ["UCC_REPO"]]
import django
django.setup()
from django.test.utils import setup_test_environment
setup_test_environment()
from django.core import mail
from django.db import connections
from django.test import Client
from academics.ownership import require_runtime_role, database_alias
from accounts.boundary import require_auth_role
PASSWORD = "Synthetic-Long-Passphrase-42"
HOST = os.environ["UCC_SITE_HOST"]
codes = json.loads(os.environ["UCC_TEST_CODES"])
result = {}

def get(client, path):
    return client.get(path, secure=True)

def post(client, path, data):
    return client.post(path, data, secure=True)

def student(name, code):
    client = Client(HTTP_HOST=HOST)
    post(client, "/accounts/register/", {"username": name, "email": f"{name}@example.invalid",
                                         "password1": PASSWORD, "password2": PASSWORD, "invite_code": code})
    link = urlsplit(mail.outbox[-1].body.split()[0])
    result[name + "_link_host"] = link.netloc
    post(client, link.path, {})
    result[name + "_login"] = post(client, "/accounts/login/", {"username": name, "password": PASSWORD}).status_code
    return client

alpha = student("synthetic_alpha", codes[0])
post(alpha, "/semesters/new/", {"label": "Synthetic semester", "display_order": "0"})
page = get(alpha, "/courses/new/").content.decode()
semester = re.search('<option value="([0-9a-f-]{36})"', page).group(1)
result["course"] = post(alpha, "/courses/new/", {"name": "Synthetic course", "original_code": "SYN101",
                                                 "credit_units": "3", "semester_id": semester, "actual_grade": "A"}).status_code
bravo = student("synthetic_bravo", codes[1])
# Interleave the two students so pooled server connections are shared between them.
for _ in range(3):
    result.setdefault("alpha_sees", []).append("SYN101" in get(alpha, "/courses/").content.decode())
    result.setdefault("bravo_sees", []).append("SYN101" in get(bravo, "/courses/").content.decode())
result["gpa"] = "Your CGPA <strong>5.00</strong>" in get(alpha, "/performance/").content.decode()
result["export"] = get(alpha, "/settings/export/").status_code
result["no_code"] = "This field is required" in post(Client(HTTP_HOST=HOST), "/accounts/register/", {
    "username": "synthetic_charlie", "email": "c@example.invalid", "password1": PASSWORD, "password2": PASSWORD}).content.decode()
require_runtime_role(connections[database_alias()])
require_auth_role()
with connections["default"].cursor() as cursor:
    cursor.execute("SHOW statement_timeout")
    result["runtime_timeout"] = cursor.fetchone()[0]
    cursor.execute("SHOW lock_timeout")
    result["runtime_lock"] = cursor.fetchone()[0]
with connections["auth"].cursor() as cursor:
    cursor.execute("SHOW statement_timeout")
    result["auth_timeout"] = cursor.fetchone()[0]
print("RESULT " + json.dumps(result))
'''


def docker(*args, check=True, timeout=300, stdin=None):
    return supabase.docker(*args, check=check, timeout=timeout, stdin=stdin)


class VercelStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        folder = Path(cls.folder.name)
        cls.runtime_port, cls.auth_port = supabase.free_port(), supabase.free_port()
        cls.cleanup()
        try:
            docker('network', 'create', NETWORK)
            docker('run', '-d', '--name', SUPA, '--network', NETWORK, '-e', f'POSTGRES_PASSWORD={supabase.ADMIN_PASSWORD}',
                   supabase.SUPABASE_IMAGE, timeout=900)
            supabase.wait_ready(SUPA)
            home = folder / 'home'
            subprocess.run([sys.executable, str(REPO / 'tools' / 'supabase_secrets.py')], check=True, capture_output=True,
                           env=dict(os.environ, UCC_LOCAL_HOME=str(home)))
            cls.secrets = json.loads((home / 'supabase' / 'secrets.json').read_text())
            files = sorted((REPO / 'supabase' / 'migrations').glob('*.sql')) + [home / 'supabase' / 'private-setup.sql']
            cls.applied = [cls.run_sql_file(path) for path in files]
            for name, user, port in ((RUNTIME_POOL, 'ucc_runtime', cls.runtime_port), (AUTH_POOL, 'ucc_auth', cls.auth_port)):
                password = cls.secrets['runtime_password' if user == 'ucc_runtime' else 'auth_password']
                ini = folder / f'{name}.ini'
                ini.write_text(POOLER_INI.format(supa=SUPA, user=user, password=password))
                ini.chmod(0o644)
                docker('run', '-d', '--name', name, '--network', NETWORK, '-p', f'127.0.0.1:{port}:6543',
                       '-v', f'{ini}:/etc/pgbouncer/pgbouncer.ini:ro', POOLER_IMAGE)
            settings = folder / 'settings'
            settings.mkdir()
            (settings / 'vercel_test_settings.py').write_text(
                SETTINGS.format(runtime_port=cls.runtime_port, auth_port=cls.auth_port))
            cls.settings_dir = str(settings)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def cleanup(cls):
        for name in (RUNTIME_POOL, AUTH_POOL, SUPA):
            docker('rm', '-f', name, check=False)
        docker('network', 'rm', NETWORK, check=False)

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()
        cls.folder.cleanup()

    @classmethod
    def run_sql_file(cls, path):
        return docker('exec', '-i', '-e', f'PGPASSWORD={supabase.ADMIN_PASSWORD}', SUPA, 'psql', '-h', 'localhost', '-U',
                      'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q', check=False, stdin=path.read_text())

    @classmethod
    def query(cls, sql):
        return docker('exec', '-e', f'PGPASSWORD={supabase.ADMIN_PASSWORD}', SUPA, 'psql', '-h', 'localhost', '-U',
                      'postgres', '-d', 'postgres', '-Atc', sql).stdout.strip()

    def invite_codes(self):
        """Two synthetic invite codes, stored the way accounts.invites does: SHA-256 of the code
        without dashes (only the digest is ever stored)."""
        codes = ['SYNT-HETC-ABCD-EFGH-JKMN', 'SYNT-HETC-ABCD-EFGH-JKMP']
        values = ', '.join(f"('{hashlib.sha256(code.replace('-', '').encode()).hexdigest()}', 'Synthetic', now(), "
                           f"now() + interval '1 day')" for code in codes)
        self.query(f'INSERT INTO accounts_invitecode (code_hash, note, created_at, expires_at) VALUES {values}')
        return codes

    def website_env(self, **extra):
        return dict(os.environ, PGHOST='aws-0-eu-west-1.pooler.supabase.com', PGPORT='6543', PGDATABASE='postgres',
                    PGUSER='ignored-by-web-vercel', PGPASSWORD=self.secrets['runtime_password'],
                    UCC_AUTH_PASSWORD=self.secrets['auth_password'], UCC_RUNTIME_ROLE='ucc_runtime', UCC_AUTH_ROLE='ucc_auth',
                    UCC_SUPABASE_PROJECT_REF='abcdefghijklmnopqrst', UCC_SITE_HOST=HOST,
                    UCC_CONTEXT_SIGNING_KEY=self.secrets['context_signing_key'],
                    DJANGO_SECRET_KEY=self.secrets['django_secret_key'], DJANGO_SETTINGS_MODULE='vercel_test_settings',
                    UCC_SETTINGS_DIR=self.settings_dir, UCC_SERVER=str(REPO / 'server'), UCC_REPO=str(REPO), **extra)

    def test_files_apply_and_logins_carry_their_time_limits(self):
        for result in self.applied:
            self.assertEqual(result.returncode, 0, result.stderr)
        settings = self.query("""SELECT string_agg(r.rolname || ':' || array_to_string(s.setconfig, ','), ' ' ORDER BY r.rolname)
            FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname IN ('ucc_runtime', 'ucc_auth')""")
        self.assertIn('ucc_runtime:statement_timeout=10000ms,lock_timeout=3000ms,idle_in_transaction_session_timeout=15000ms', settings)
        self.assertIn('ucc_auth:statement_timeout=5000ms,lock_timeout=3000ms,idle_in_transaction_session_timeout=15000ms', settings)

    def test_student_journey_through_a_transaction_pooler(self):
        codes = self.invite_codes()
        result = subprocess.run([sys.executable, '-c', JOURNEY], env=self.website_env(UCC_TEST_CODES=json.dumps(codes), **EMAIL),
                                capture_output=True, text=True, timeout=300)
        lines = [line for line in result.stdout.splitlines() if line.startswith('RESULT ')]
        self.assertTrue(lines, result.stdout[-2000:] + result.stderr[-4000:])
        data = json.loads(lines[-1][7:])
        self.assertEqual((data['synthetic_alpha_login'], data['synthetic_bravo_login']), (302, 302), data)
        self.assertEqual(data['synthetic_alpha_link_host'], HOST)  # email links use the public https address
        self.assertEqual(data['course'], 302, data)
        self.assertEqual(data['alpha_sees'], [True] * 3, data)
        self.assertEqual(data['bravo_sees'], [False] * 3, data)  # row-level security holds through the pooler
        self.assertTrue(data['gpa'], data)
        self.assertEqual(data['export'], 200, data)
        self.assertTrue(data['no_code'], data)  # invite-only sign-up
        # The pooler ignored the per-connection options; the login settings still apply.
        self.assertEqual((data['runtime_timeout'], data['runtime_lock'], data['auth_timeout']), ('10s', '3s', '5s'), data)

    def test_the_real_entry_point_starts_only_with_email_settings(self):
        code = ('import os, sys; sys.path[:0] = [os.environ["UCC_REPO"]]\n'
                'try:\n    import vercel_app\nexcept SystemExit as stop:\n    print("STOPPED", stop.code)\n'
                'except Exception as error:\n    print("REFUSED", type(error).__name__)\n'
                'else:\n    print("STARTED", callable(vercel_app.app))\n')
        started = subprocess.run([sys.executable, '-c', code], env=self.website_env(**EMAIL), capture_output=True, text=True,
                                 timeout=120)
        self.assertIn('STARTED True', started.stdout, started.stdout + started.stderr[-2000:])
        refused = subprocess.run([sys.executable, '-c', code], env=self.website_env(), capture_output=True, text=True,
                                 timeout=120)
        self.assertIn('REFUSED ImproperlyConfigured', refused.stdout, refused.stdout + refused.stderr[-2000:])

if __name__ == '__main__':
    unittest.main()
