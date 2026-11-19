"""tools/vercel_env.py: the private Vercel settings file is complete, private and never overwritten."""
import importlib.util
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('vercel_env', TOOLS / 'vercel_env.py')
vercel_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vercel_env)
import supabase_secrets  # noqa: E402

ARGS = ['--site-host', 'university-command-center.vercel.app', '--project-ref', 'abcdefghijklmnopqrst',
        '--pooler-host', 'aws-0-eu-west-1.pooler.supabase.com', '--email-address', 'UCC.Synthetic.Site@gmail.com']


class VercelEnvTests(unittest.TestCase):
    def setUp(self):
        self.home = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'UCC_LOCAL_HOME': self.home}))
        with redirect_stdout(io.StringIO()):
            supabase_secrets.main([])
        self.folder = Path(self.home) / 'supabase'

    def make(self, args=ARGS, app_password='abcd efgh ijkl mnop'):
        output = io.StringIO()
        with redirect_stdout(output), patch.object(vercel_env.getpass, 'getpass', return_value=app_password):
            vercel_env.main(args)
        return output.getvalue()

    def test_writes_every_setting_privately_and_prints_nothing_secret(self):
        output = self.make()
        secrets = json.loads((self.folder / 'secrets.json').read_text())
        path = self.folder / 'vercel.env'
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        data = dict(line.split('=', 1) for line in path.read_text().splitlines())
        self.assertEqual(data['PGPASSWORD'], secrets['runtime_password'])
        self.assertEqual(data['UCC_AUTH_PASSWORD'], secrets['auth_password'])
        self.assertEqual(data['UCC_CONTEXT_SIGNING_KEY'], secrets['context_signing_key'])
        self.assertEqual(data['DJANGO_SECRET_KEY'], secrets['django_secret_key'])
        self.assertEqual((data['PGHOST'], data['PGPORT'], data['PGDATABASE']),
                         ('aws-0-eu-west-1.pooler.supabase.com', '6543', 'postgres'))
        self.assertEqual((data['UCC_SITE_HOST'], data['UCC_SUPABASE_PROJECT_REF']),
                         ('university-command-center.vercel.app', 'abcdefghijklmnopqrst'))
        self.assertEqual((data['UCC_EMAIL_ADDRESS'], data['UCC_EMAIL_APP_PASSWORD']),
                         ('ucc.synthetic.site@gmail.com', 'abcdefghijklmnop'))
        for value in list(secrets.values()) + ['abcdefghijklmnop', 'abcd efgh ijkl mnop']:
            self.assertNotIn(value, output)

    def test_a_wrong_app_password_writes_nothing(self):
        for bad in ('short', 'abcd-efgh-ijkl-mnop', ''):
            with self.subTest(app_password=bad), self.assertRaises(SystemExit):
                self.make(app_password=bad)
        self.assertFalse((self.folder / 'vercel.env').exists())

    def test_never_overwrites_and_refuses_bad_values(self):
        self.make()
        before = (self.folder / 'vercel.env').read_text()
        with self.assertRaises(SystemExit):
            self.make()
        self.assertEqual((self.folder / 'vercel.env').read_text(), before)
        for bad in (['--site-host', 'https://x.vercel.app'], ['--project-ref', 'short'], ['--pooler-host', 'db.x.supabase.co'],
                    ['--email-address', 'me@yahoo.com']):
            args = list(ARGS)
            args[args.index(bad[0]) + 1] = bad[1]
            with self.subTest(bad=bad), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.make(args)


if __name__ == '__main__':
    unittest.main()
