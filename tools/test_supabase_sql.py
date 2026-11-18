"""End-to-end check of the Supabase SQL files on Supabase's own PostgreSQL image.

Needs Docker and the Django requirements; takes a few minutes. Uses synthetic data, throwaway
passwords and two local containers only (a plain PostgreSQL 17 to check the files are current,
and ghcr.io/supabase/postgres to run them as the SQL editor's postgres login). Removed afterwards.

    python tools/test_supabase_sql.py -v
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[1]
SUPABASE_IMAGE = 'ghcr.io/supabase/postgres:17.6.1.054'
PLAIN_IMAGE = 'postgres:17.12'
PLAIN, SUPA = 'ucc-sqltest-plain', 'ucc-sqltest-supabase'
ADMIN_PASSWORD = 'synthetic-local-only-password'
SYSTEM_LOGINS = ('authenticator', 'pgbouncer', 'supabase_auth_admin', 'supabase_storage_admin', 'dashboard_user')

JOURNEY = r'''
import json, os, sys
from urllib.parse import urlsplit
sys.path[:0] = [os.environ["UCC_SERVER"], os.environ["UCC_REPO"]]
import django
django.setup()
from django.test.utils import setup_test_environment
setup_test_environment()
from django.core import mail
from django.test import Client
PASSWORD = "Synthetic-Long-Passphrase-42"
result = {}

def student(name):
    client = Client(HTTP_HOST="localhost")
    client.post("/accounts/register/", {"username": name, "email": f"{name}@example.invalid",
                                         "password1": PASSWORD, "password2": PASSWORD})
    link = urlsplit(mail.outbox[-1].body.split()[0]).path
    client.post(link)
    result[name + "_login"] = client.post("/accounts/login/", {"username": name, "password": PASSWORD}).status_code
    return client

alpha = student("synthetic_alpha")
alpha.post("/semesters/new/", {"label": "Synthetic semester", "display_order": "0"})
page = alpha.get("/courses/new/").content.decode()
import re
semester = re.search('<option value="([0-9a-f-]{36})"', page).group(1)
result["course"] = alpha.post("/courses/new/", {"name": "Synthetic course", "original_code": "SYN101",
                                                "credit_units": "3", "semester_id": semester, "actual_grade": "A"}).status_code
result["alpha_sees_course"] = "SYN101" in alpha.get("/courses/").content.decode()
result["gpa"] = "Your CGPA <strong>5.00</strong>" in alpha.get("/performance/").content.decode()
result["export"] = alpha.get("/settings/export/").status_code
bravo = student("synthetic_bravo")
result["bravo_sees_course"] = "SYN101" in bravo.get("/courses/").content.decode()
print("RESULT " + json.dumps(result))
'''


def free_port():
    with socket.socket() as handle:
        handle.bind(('127.0.0.1', 0))
        return handle.getsockname()[1]


def docker(*args, check=True, timeout=300, stdin=None):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout, input=stdin)
    if check and result.returncode != 0:
        raise AssertionError(f'docker {" ".join(args[:3])} failed:\n{result.stdout}\n{result.stderr}')
    return result


def wait_ready(name):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if docker('exec', name, 'pg_isready', '-h', 'localhost', '-U', 'postgres', check=False).returncode == 0:
            time.sleep(4)  # the Supabase image finishes its own setup scripts after accepting connections
            return
        time.sleep(2)
    raise AssertionError(f'{name} never became ready')


class SupabaseSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.plain_port, cls.supa_port = free_port(), free_port()
        for name in (PLAIN, SUPA):
            docker('rm', '-f', name, check=False)
        try:
            docker('run', '-d', '--name', PLAIN, '-e', f'POSTGRES_PASSWORD={ADMIN_PASSWORD}',
                   '-p', f'127.0.0.1:{cls.plain_port}:5432', PLAIN_IMAGE)
            docker('run', '-d', '--name', SUPA, '-e', f'POSTGRES_PASSWORD={ADMIN_PASSWORD}',
                   '-p', f'127.0.0.1:{cls.supa_port}:5432', SUPABASE_IMAGE, timeout=900)
            wait_ready(PLAIN)
            wait_ready(SUPA)
            env = dict(os.environ, PGHOST='127.0.0.1', PGPORT=str(cls.plain_port), PGUSER='postgres',
                       PGPASSWORD=ADMIN_PASSWORD)
            cls.check = subprocess.run([sys.executable, str(REPO / 'tools' / 'export_supabase_sql.py'), '--check'],
                                       env=env, capture_output=True, text=True, timeout=600)
            home = Path(cls.folder.name) / 'home'
            subprocess.run([sys.executable, str(REPO / 'tools' / 'supabase_secrets.py')], check=True, capture_output=True,
                           env=dict(os.environ, UCC_LOCAL_HOME=str(home)))
            cls.private = home / 'supabase'
            cls.secrets = json.loads((cls.private / 'secrets.json').read_text())
            cls.applied = [cls.run_sql_file(path) for path in sorted((REPO / 'supabase' / 'migrations').glob('*.sql'))]
            cls.applied.append(cls.run_sql_file(cls.private / 'private-setup.sql'))
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for name in (PLAIN, SUPA):
            docker('rm', '-f', name, check=False)
        cls.folder.cleanup()

    @classmethod
    def run_sql_file(cls, path):
        """As the SQL editor does: the whole file at once, as the postgres login (not a superuser)."""
        return docker('exec', '-i', '-e', f'PGPASSWORD={ADMIN_PASSWORD}', SUPA, 'psql', '-h', 'localhost', '-U', 'postgres',
                      '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q', check=False, stdin=path.read_text())

    @classmethod
    def query(cls, sql, user='postgres'):
        return docker('exec', '-e', f'PGPASSWORD={ADMIN_PASSWORD}', SUPA, 'psql', '-h', 'localhost', '-U', user,
                      '-d', 'postgres', '-Atc', sql).stdout.strip()

    def website_env(self):
        return dict(os.environ, PGHOST='127.0.0.1', PGPORT=str(self.supa_port), PGDATABASE='postgres',
                    PGUSER='ucc_runtime', PGPASSWORD=self.secrets['runtime_password'], UCC_AUTH_ROLE='ucc_auth',
                    UCC_RUNTIME_ROLE='ucc_runtime', UCC_AUTH_PASSWORD=self.secrets['auth_password'],
                    UCC_CONTEXT_SIGNING_KEY=self.secrets['context_signing_key'],
                    DJANGO_SECRET_KEY=self.secrets['django_secret_key'],
                    DJANGO_SETTINGS_MODULE='config.settings.web_development',
                    UCC_SERVER=str(REPO / 'server'), UCC_REPO=str(REPO))

    def login_page_status(self):
        code = ('import os,sys;sys.path[:0]=[os.environ["UCC_SERVER"],os.environ["UCC_REPO"]];import django;django.setup();'
                'from django.test import Client;print(Client(HTTP_HOST="localhost").get("/accounts/login/").status_code)')
        result = subprocess.run([sys.executable, '-c', code], env=self.website_env(), capture_output=True, text=True, timeout=120)
        return int(result.stdout.strip().splitlines()[-1])

    def test_committed_files_match_the_migrations(self):
        self.assertEqual(self.check.returncode, 0, self.check.stdout + self.check.stderr)

    def test_every_file_runs_cleanly_as_the_sql_editor_login(self):
        for result in self.applied:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.query("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"), 'f')

    def test_security_file_can_be_run_again(self):
        newest = sorted((REPO / 'supabase' / 'migrations').glob('*_security.sql'))[-1]
        self.assertEqual(self.run_sql_file(newest).returncode, 0)

    def test_django_sees_every_migration_applied(self):
        env = dict(os.environ, PGHOST='127.0.0.1', PGPORT=str(self.supa_port), PGDATABASE='postgres', PGUSER='postgres',
                   PGPASSWORD=ADMIN_PASSWORD, DJANGO_SECRET_KEY='synthetic', UCC_CONTEXT_SIGNING_KEY='00' * 32,
                   UCC_RUNTIME_ROLE='ucc_runtime', UCC_AUTH_ROLE='ucc_auth')
        result = subprocess.run([sys.executable, 'manage.py', 'migrate', '--check', '--settings=config.settings.auth_migration'],
                                cwd=REPO / 'server', env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_supabase_data_api_logins_reach_nothing(self):
        reachable = self.query("""SELECT count(*) FROM pg_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE r.rolname IN ('anon', 'authenticated', 'service_role') AND n.nspname IN ('public', 'ucc_security')
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
              AND (has_table_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
                   OR has_any_column_privilege(r.oid, c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'))""")
        self.assertEqual(reachable, '0')
        for role in ('anon', 'authenticated', 'service_role'):
            with self.subTest(role=role):
                denied = docker('exec', '-e', f'PGPASSWORD={ADMIN_PASSWORD}', SUPA, 'psql', '-h', 'localhost', '-U',
                                'supabase_admin', '-d', 'postgres', '-Atc',
                                f'SET ROLE {role}; SELECT count(*) FROM public.accounts_student', check=False)
                self.assertIn('permission denied', denied.stderr)
        # Tables made later by the postgres login are not opened to the Data API either.
        self.query('CREATE TABLE public.synthetic_later (id int)')
        try:
            self.assertEqual(self.query("SELECT has_table_privilege('anon', 'public.synthetic_later', 'SELECT')"), 'f')
        finally:
            self.query('DROP TABLE public.synthetic_later')

    def test_every_table_has_row_level_security(self):
        self.assertEqual(self.query("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity"""), '0')
        self.assertEqual(self.query("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname LIKE 'academics\\_%' AND c.relkind = 'r' AND NOT c.relforcerowsecurity"""), '0')

    def test_website_logins_are_restricted(self):
        self.assertEqual(self.query("""SELECT string_agg(rolname || ':' || rolsuper || rolbypassrls || rolinherit || rolcreatedb
            || rolcreaterole || rolcanlogin, ',' ORDER BY rolname) FROM pg_roles WHERE rolname IN ('ucc_runtime', 'ucc_auth')"""),
            'ucc_auth:falsefalsefalsefalsefalsetrue,ucc_runtime:falsefalsefalsefalsefalsetrue')
        self.assertEqual(self.query("SELECT has_database_privilege('ucc_runtime', 'postgres', 'TEMPORARY')"), 'f')

    def test_supabase_own_logins_can_still_connect(self):
        for role in SYSTEM_LOGINS:
            with self.subTest(role=role):
                self.assertEqual(self.query(f"SELECT has_database_privilege('{role}', 'postgres', 'CONNECT')"), 't')

    def test_a_full_student_journey_with_row_level_security(self):
        result = subprocess.run([sys.executable, '-c', JOURNEY], env=self.website_env(), capture_output=True, text=True,
                                timeout=300)
        lines = [line for line in result.stdout.splitlines() if line.startswith('RESULT ')]
        self.assertTrue(lines, result.stdout[-2000:] + result.stderr[-4000:])
        data = json.loads(lines[-1][7:])
        self.assertEqual((data['synthetic_alpha_login'], data['synthetic_bravo_login']), (302, 302), data)
        self.assertEqual(data['course'], 302, data)
        self.assertTrue(data['alpha_sees_course'], data)
        self.assertTrue(data['gpa'], data)
        self.assertEqual(data['export'], 200, data)
        self.assertFalse(data['bravo_sees_course'], data)  # another student's rows stay invisible

    def test_website_refuses_to_start_if_the_data_api_is_opened(self):
        newest = sorted((REPO / 'supabase' / 'migrations').glob('*_security.sql'))[-1]
        self.assertEqual(self.login_page_status(), 200)
        for opening in ('GRANT SELECT ON public.accounts_student TO anon',
                        'GRANT SELECT (password) ON public.accounts_student TO authenticated',
                        'GRANT TRUNCATE ON public.academics_course TO service_role',
                        'GRANT SELECT ON public.accounts_invitecode TO anon',
                        'GRANT USAGE ON SCHEMA ucc_security TO anon; '
                        'GRANT EXECUTE ON FUNCTION ucc_security.current_student() TO anon'):
            with self.subTest(opening=opening):
                self.query(opening)
                try:
                    self.assertEqual(self.login_page_status(), 503)
                finally:
                    self.assertEqual(self.run_sql_file(newest).returncode, 0)  # re-running the file repairs it
                self.assertEqual(self.login_page_status(), 200)


if __name__ == '__main__':
    unittest.main()
