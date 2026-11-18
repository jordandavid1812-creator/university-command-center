"""tools/supabase_secrets.py: the private Supabase file is complete, private and never overwritten."""
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import re
import stat
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('supabase_secrets', Path(__file__).resolve().parents[1] / 'tools' / 'supabase_secrets.py')
supabase_secrets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supabase_secrets)


class SupabaseSecretsTests(unittest.TestCase):
    def make(self):
        home = self.enterContext(tempfile.TemporaryDirectory())
        output = io.StringIO()
        with patch.dict(os.environ, {'UCC_LOCAL_HOME': home}), redirect_stdout(output):
            supabase_secrets.main([])
        return Path(home) / 'supabase', output.getvalue()

    def test_private_files_hold_new_values_and_nothing_is_printed(self):
        folder, output = self.make()
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for name in ('private-setup.sql', 'secrets.json'):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)
        data = json.loads((folder / 'secrets.json').read_text())
        sql = (folder / 'private-setup.sql').read_text()
        for value in data.values():
            self.assertNotIn(value, output)
            self.assertRegex(value, r'^[A-Za-z0-9_-]{40,}$')
        self.assertIn(f"ALTER ROLE ucc_runtime PASSWORD '{data['runtime_password']}';", sql)
        self.assertIn(f"ALTER ROLE ucc_auth PASSWORD '{data['auth_password']}';", sql)
        self.assertIn(f"decode('{data['context_signing_key']}', 'hex')", sql)
        self.assertEqual(len(bytes.fromhex(data['context_signing_key'])), 32)
        self.assertEqual(len(set(data.values())), 4)
        self.assertEqual(sql.count("'"), 8)  # two passwords, the key and 'hex': no stray quotes

    def test_never_overwrites(self):
        folder, _ = self.make()
        before = (folder / 'secrets.json').read_text()
        with patch.dict(os.environ, {'UCC_LOCAL_HOME': str(folder.parent)}), self.assertRaises(SystemExit):
            supabase_secrets.main([])
        self.assertEqual((folder / 'secrets.json').read_text(), before)

    def test_refuses_a_folder_inside_the_repository(self):
        inside = str(Path(__file__).resolve().parents[1] / 'work' / 'private')
        with patch.dict(os.environ, {'UCC_LOCAL_HOME': inside}), self.assertRaises(SystemExit) as stopped:
            supabase_secrets.main([])
        self.assertIn('inside the repository', str(stopped.exception))
        self.assertFalse(Path(inside).exists())


if __name__ == '__main__':
    unittest.main()
