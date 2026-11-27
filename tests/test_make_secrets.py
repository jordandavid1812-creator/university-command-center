"""deploy/make_secrets.py: private server settings are complete, separate and never overwritten."""
import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import stat
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('make_secrets', Path(__file__).resolve().parents[1] / 'deploy' / 'make_secrets.py')
make_secrets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(make_secrets)


def read(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines())


class MakeSecretsTests(unittest.TestCase):
    def make(self, *args):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory())) / 'secrets'
        output = io.StringIO()
        with redirect_stdout(output):
            make_secrets.main(['--folder', str(folder), *args])
        return folder, output.getvalue()

    def test_creates_four_private_files_and_prints_nothing_secret(self):
        folder, output = self.make('--host', 'ucc-student.example.com', '--email', 'Owner@Example.com')
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['caddy.env', 'db.env', 'migrator.env', 'web.env'])
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for path in folder.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
            for value in read(path).values():
                if len(value) >= 32:
                    self.assertNotIn(value, output)
        self.assertEqual(read(folder / 'caddy.env'), {'UCC_SITE_HOST': 'ucc-student.example.com',
                                                      'UCC_CADDY_TLS': 'owner@example.com'})

    def test_each_service_gets_only_its_own_login(self):
        folder, _ = self.make('--host', 'ucc-student.example.com', '--email', 'owner@example.com')
        db, migrator, web = (read(folder / name) for name in ('db.env', 'migrator.env', 'web.env'))
        self.assertEqual((migrator['PGUSER'], migrator['PGPASSWORD']), ('ucc_migrator', db['UCC_MIGRATOR_PASSWORD']))
        self.assertEqual((web['PGUSER'], web['PGPASSWORD']), ('ucc_runtime', db['UCC_RUNTIME_PASSWORD']))
        self.assertEqual(web['UCC_AUTH_PASSWORD'], db['UCC_AUTH_PASSWORD'])
        web_values = set(web.values())
        for secret in (db['POSTGRES_PASSWORD'], db['UCC_MIGRATOR_PASSWORD']):
            self.assertNotIn(secret, web_values)  # the website never holds admin or migrator logins
        self.assertNotIn('UCC_AUTH_PASSWORD', migrator)
        self.assertEqual(web['UCC_SITE_HOST'], 'ucc-student.example.com')
        self.assertEqual(web['UCC_TRUSTED_PROXY'], '172.30.0.10/32')
        self.assertEqual(web['DJANGO_SECRET_KEY'], migrator['DJANGO_SECRET_KEY'])
        self.assertEqual(len(bytes.fromhex(web['UCC_CONTEXT_SIGNING_KEY'])), 32)
        passwords = [db[k] for k in db if k.endswith('PASSWORD')]
        self.assertEqual(len(set(passwords)), 4)  # all different
        self.assertTrue(all(len(p) >= 40 for p in passwords))

    def test_never_overwrites_existing_settings(self):
        folder, _ = self.make('--host', 'ucc-student.example.com', '--email', 'owner@example.com')
        before = {p.name: p.read_text() for p in folder.iterdir()}
        with self.assertRaises(SystemExit) as stopped:
            make_secrets.main(['--folder', str(folder), '--host', 'other.example.com', '--email', 'owner@example.com'])
        self.assertIn('Nothing was changed', str(stopped.exception))
        self.assertEqual({p.name: p.read_text() for p in folder.iterdir()}, before)

    def test_refuses_bad_host_or_email(self):
        for args in (['--host', 'https://ucc.example.com', '--email', 'a@example.com'],
                     ['--host', 'UCC.example.com', '--email', 'a@example.com'],
                     ['--host', 'localhost', '--email', 'a@example.com'],
                     ['--host', 'ucc.example.com'],
                     ['--host', 'ucc.example.com', '--email', 'not-an-email']):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.make(*args)


if __name__ == '__main__':
    unittest.main()
