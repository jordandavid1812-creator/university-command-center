"""Launch step H: an encrypted backup really restores. Needs Docker and the Django requirements.

Two of Supabase's own PostgreSQL containers: SOURCE gets the numbered files, a private setup file,
supabase/backup/backup_role.sql and two synthetic students (through the website); TARGET gets the
numbered files and a DIFFERENT private setup. tools/backup_database.py copies SOURCE with the
read-only backup login and encrypts it with a test age key; tools/restore_database.py puts it into
TARGET. Synthetic data only; everything is removed afterwards.

    python tools/test_backup_restore.py -v
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import test_supabase_sql as supabase
from backup_database import BACKUP_TABLES

REPO = Path(__file__).resolve().parents[1]
SOURCE, TARGET = 'ucc-backup-source', 'ucc-backup-target'
CLIENT_IMAGE = 'mirror.gcr.io/library/postgres:17.12'
BACKUP_PASSWORD = 'synthetic-backup-password-only-for-tests'
MARKER = b'MARKER-synthetic-backup-notes'
UPLOAD = r'''
from django.core.files.uploadedfile import SimpleUploadedFile
page = alpha.get("/materials/new/").content.decode()
course = re.search('<option value="([0-9a-f-]{36})"', page).group(1)
result["upload"] = alpha.post("/materials/new/", {"title": "Synthetic notes", "course_id": course,
    "file": SimpleUploadedFile("notes.txt", b"MARKER-synthetic-backup-notes for the restore test")}).status_code
'''
CHECK_TARGET = r'''
import json, os, re, sys
sys.path[:0] = [os.environ["UCC_SERVER"], os.environ["UCC_REPO"]]
import django
django.setup()
from django.test import Client
PASSWORD = "Synthetic-Long-Passphrase-42"
result = {}
alpha, bravo = Client(HTTP_HOST="localhost"), Client(HTTP_HOST="localhost")
result["alpha_login"] = alpha.post("/accounts/login/", {"username": "synthetic_alpha", "password": PASSWORD}).status_code
result["bravo_login"] = bravo.post("/accounts/login/", {"username": "synthetic_bravo", "password": PASSWORD}).status_code
result["alpha_sees_course"] = "SYN101" in alpha.get("/courses/").content.decode()
result["bravo_sees_course"] = "SYN101" in bravo.get("/courses/").content.decode()
page = alpha.get("/materials/").content.decode()
material = re.search(r'/materials/([0-9a-f-]{36})/download/', page).group(1)
result["download"] = alpha.get(f"/materials/{material}/download/").content.decode()
result["bravo_download"] = bravo.get(f"/materials/{material}/download/").status_code
print("RESULT " + json.dumps(result))
'''


def docker(*args, **kwargs):
    return supabase.docker(*args, **kwargs)


class BackupRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.work = Path(cls.folder.name)
        cls.ports = {SOURCE: supabase.free_port(), TARGET: supabase.free_port()}
        cls.cleanup()
        try:
            for name, port in cls.ports.items():
                docker('run', '-d', '--name', name, '-e', f'POSTGRES_PASSWORD={supabase.ADMIN_PASSWORD}',
                       '-p', f'127.0.0.1:{port}:5432', supabase.SUPABASE_IMAGE, timeout=900)
            for name in cls.ports:
                supabase.wait_ready(name)
            cls.secrets = {}
            for name in cls.ports:
                home = cls.work / name
                subprocess.run([sys.executable, str(REPO / 'tools' / 'supabase_secrets.py')], check=True,
                               capture_output=True, env=dict(os.environ, UCC_LOCAL_HOME=str(home)))
                cls.secrets[name] = json.loads((home / 'supabase' / 'secrets.json').read_text())
                files = sorted((REPO / 'supabase' / 'migrations').glob('*.sql')) + [home / 'supabase' / 'private-setup.sql']
                for path in files:
                    applied = cls.sql_file(name, path)
                    assert applied.returncode == 0, f'{path.name} failed on {name}'
            cls.backup_role = cls.sql_file(SOURCE, REPO / 'supabase' / 'backup' / 'backup_role.sql')
            cls.backup_role_again = cls.sql_file(SOURCE, REPO / 'supabase' / 'backup' / 'backup_role.sql')
            cls.query(SOURCE, f"ALTER ROLE ucc_backup WITH PASSWORD '{BACKUP_PASSWORD}'")
            journey = supabase.JOURNEY.replace('print("RESULT "', UPLOAD + 'print("RESULT "')
            cls.seeded = cls.website(SOURCE, journey)
            subprocess.run(['age-keygen', '-o', str(cls.work / 'key.txt')], check=True, capture_output=True)
            subprocess.run(['age-keygen', '-o', str(cls.work / 'other-key.txt')], check=True, capture_output=True)
            cls.recipient = re.search(r'age1[0-9a-z]+', (cls.work / 'key.txt').read_text()).group(0)
            cls.backup_file = cls.work / 'ucc-backup-test.dump.age'
            cls.backup = cls.run_tool('backup_database.py', '--output', str(cls.backup_file))
            cls.restore = cls.run_tool('restore_database.py', '--backup', str(cls.backup_file),
                                       '--key', str(cls.work / 'key.txt'))
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def cleanup(cls):
        for name in (SOURCE, TARGET):
            docker('rm', '-f', name, check=False)

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()
        cls.folder.cleanup()

    @classmethod
    def sql_file(cls, name, path):
        return docker('exec', '-i', '-e', f'PGPASSWORD={supabase.ADMIN_PASSWORD}', name, 'psql', '-h', 'localhost',
                      '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-q', check=False,
                      stdin=path.read_text())

    @classmethod
    def query(cls, name, sql, user='postgres', password=supabase.ADMIN_PASSWORD, check=True):
        return docker('exec', '-e', f'PGPASSWORD={password}', name, 'psql', '-h', 'localhost', '-U', user, '-d',
                      'postgres', '-v', 'ON_ERROR_STOP=1', '-Atc', sql, check=check)

    @classmethod
    def tool_env(cls, **extra):
        client = f'docker run --rm -i --network host -e PGPASSWORD {CLIENT_IMAGE}'
        return dict(os.environ, UCC_BACKUP_HOST='127.0.0.1', UCC_BACKUP_PORT=str(cls.ports[SOURCE]),
                    UCC_BACKUP_SSLMODE='disable', UCC_BACKUP_RECIPIENT=cls.recipient, PGPASSWORD=BACKUP_PASSWORD,
                    UCC_PG_DUMP=f'{client} pg_dump', UCC_PG_RESTORE=f'{client} pg_restore',
                    UCC_RESTORE_HOST='127.0.0.1', UCC_RESTORE_PORT=str(cls.ports[TARGET]),
                    UCC_RESTORE_SSLMODE='disable') | extra

    @classmethod
    def run_tool(cls, script, *args, **extra):
        if script == 'restore_database.py':
            extra.setdefault('PGPASSWORD', supabase.ADMIN_PASSWORD)
        env = cls.tool_env(**extra)
        return subprocess.run([sys.executable, str(REPO / 'tools' / script), *args], env=env, capture_output=True,
                              text=True, timeout=600, cwd=REPO / 'tools')

    @classmethod
    def website(cls, name, script):
        secrets = cls.secrets[name]
        env = dict(os.environ, PGHOST='127.0.0.1', PGPORT=str(cls.ports[name]), PGDATABASE='postgres',
                   PGUSER='ucc_runtime', PGPASSWORD=secrets['runtime_password'], UCC_AUTH_ROLE='ucc_auth',
                   UCC_RUNTIME_ROLE='ucc_runtime', UCC_AUTH_PASSWORD=secrets['auth_password'],
                   UCC_CONTEXT_SIGNING_KEY=secrets['context_signing_key'], DJANGO_SECRET_KEY=secrets['django_secret_key'],
                   DJANGO_SETTINGS_MODULE='config.settings.web_development', UCC_SERVER=str(REPO / 'server'),
                   UCC_REPO=str(REPO))
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=300)
        lines = [line for line in result.stdout.splitlines() if line.startswith('RESULT ')]
        assert lines, result.stdout[-2000:] + result.stderr[-3000:]
        return json.loads(lines[-1][7:])

    def fingerprints(self, name):
        sql = ' UNION ALL '.join(f"SELECT '{table}' || ':' || count(*) || ':' || "
                                 f"coalesce(md5(string_agg(t::text, '' ORDER BY t::text)), '-') FROM public.{table} t"
                                 for table in BACKUP_TABLES)
        return self.query(name, sql).stdout.split()

    def test_backup_login_is_set_up_and_its_file_can_be_run_again(self):
        self.assertEqual((self.backup_role.returncode, self.backup_role_again.returncode), (0, 0),
                         self.backup_role.stderr + self.backup_role_again.stderr)
        self.assertEqual(self.seeded['upload'], 302, self.seeded)
        self.assertEqual(self.query(SOURCE, "SELECT rolbypassrls, rolsuper, rolcreaterole, rolcreatedb, rolinherit "
                                            "FROM pg_roles WHERE rolname = 'ucc_backup'").stdout.strip(), 't|f|f|f|f')

    def test_backup_login_reads_every_student_but_cannot_write_or_read_secrets(self):
        reads = self.query(SOURCE, 'SELECT count(DISTINCT id) FROM accounts_student', user='ucc_backup',
                           password=BACKUP_PASSWORD).stdout.strip()
        self.assertEqual(reads, '2')  # both students, despite row-level security
        for sql in ("INSERT INTO academics_aisiteusage (day, requests) VALUES ('2026-01-01', 0)",
                    'UPDATE accounts_student SET is_active = is_active',
                    'DELETE FROM academics_course',
                    'SELECT count(*) FROM django_session',
                    'SELECT count(*) FROM accounts_accounttoken',
                    'SELECT count(*) FROM ucc_security.context_key',
                    'CREATE TABLE public.ucc_backup_probe (x int)'):
            with self.subTest(sql=sql):
                result = self.query(SOURCE, sql, user='ucc_backup', password=BACKUP_PASSWORD, check=False)
                self.assertNotEqual(result.returncode, 0)

    def test_backup_is_encrypted_and_holds_only_the_student_tables(self):
        self.assertEqual(self.backup.returncode, 0, self.backup.stderr)
        self.assertIn('No data was printed', self.backup.stdout)
        data = self.backup_file.read_bytes()
        self.assertTrue(data.startswith(b'age-encryption.org/v1'))
        for plain in (MARKER, b'synthetic_alpha', b'SYN101', b'pbkdf2'):
            self.assertNotIn(plain, data)
        listing = subprocess.run(f'age --decrypt --identity {self.work / "key.txt"} {self.backup_file} | '
                                 f'docker run --rm -i {CLIENT_IMAGE} pg_restore --list', shell=True,
                                 capture_output=True, text=True, timeout=300)
        tables = set(re.findall(r'TABLE DATA public (\w+)', listing.stdout))
        self.assertEqual(tables, set(BACKUP_TABLES))
        self.assertNotIn('context_key', listing.stdout)
        wrong = subprocess.run(['age', '--decrypt', '--identity', str(self.work / 'other-key.txt'),
                                str(self.backup_file)], capture_output=True, timeout=60)
        self.assertNotEqual(wrong.returncode, 0)

    def test_restore_brings_back_every_row_and_the_website_works_with_new_passwords(self):
        self.assertEqual(self.restore.returncode, 0, self.restore.stderr)
        self.assertEqual(self.fingerprints(TARGET), self.fingerprints(SOURCE))
        result = self.website(TARGET, CHECK_TARGET)
        self.assertEqual((result['alpha_login'], result['bravo_login']), (302, 302), result)
        self.assertTrue(result['alpha_sees_course'])
        self.assertFalse(result['bravo_sees_course'])  # row-level security still separates students
        self.assertIn(MARKER.decode(), result['download'])
        self.assertEqual(result['bravo_download'], 404)

    def test_restore_refuses_a_database_that_already_has_data(self):
        self.assertEqual(self.restore.returncode, 0, self.restore.stderr)
        before = self.fingerprints(TARGET)
        again = self.run_tool('restore_database.py', '--backup', str(self.backup_file), '--key', str(self.work / 'key.txt'))
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('already has rows', again.stderr)
        self.assertEqual(self.fingerprints(TARGET), before)

    def test_backup_refuses_bad_settings_and_never_overwrites(self):
        missing = self.run_tool('backup_database.py', '--output', str(self.work / 'x.age'), UCC_BACKUP_RECIPIENT='')
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse((self.work / 'x.age').exists())
        existing = self.run_tool('backup_database.py', '--output', str(self.backup_file))
        self.assertNotEqual(existing.returncode, 0)
        self.assertIn('already exists', existing.stderr)
        wrong_password = self.run_tool('backup_database.py', '--output', str(self.work / 'y.age'), PGPASSWORD='wrong')
        self.assertNotEqual(wrong_password.returncode, 0)
        self.assertFalse((self.work / 'y.age').exists())


if __name__ == '__main__':
    unittest.main()
