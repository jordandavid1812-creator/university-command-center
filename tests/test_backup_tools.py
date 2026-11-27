"""Launch step H: the backup tools refuse unsafe settings and never print or overwrite secrets.
(The real backup and restore are tested with Docker in tools/test_backup_restore.py.)"""
import importlib.util
import io
import os
from contextlib import redirect_stdout
from pathlib import Path
import re
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup_database = load('backup_database')
backup_password = load('backup_password')
REPO = TOOLS.parent


class BackupPasswordTests(unittest.TestCase):
    def test_password_files_are_private_complete_and_never_overwritten(self):
        home = self.enterContext(tempfile.TemporaryDirectory())
        output = io.StringIO()
        with patch.dict(os.environ, {'UCC_LOCAL_HOME': home}), redirect_stdout(output):
            backup_password.main()
        folder = Path(home) / 'backup'
        password = (folder / 'backup-password.txt').read_text().strip()
        self.assertRegex(password, r'^[A-Za-z0-9_-]{40,}$')
        self.assertNotIn(password, output.getvalue())
        self.assertIn(f"ALTER ROLE ucc_backup WITH PASSWORD '{password}';", (folder / 'backup-password.sql').read_text())
        for name in ('backup-password.sql', 'backup-password.txt'):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)
        with patch.dict(os.environ, {'UCC_LOCAL_HOME': home}), self.assertRaises(SystemExit):
            backup_password.main()
        self.assertEqual((folder / 'backup-password.txt').read_text().strip(), password)


class BackupSettingsTests(unittest.TestCase):
    GOOD = {'UCC_BACKUP_HOST': 'aws-0-eu-west-1.pooler.supabase.com', 'UCC_SUPABASE_PROJECT_REF': 'abcdefghijklmnopqrst'}

    def test_supabase_connection_uses_the_session_pooler_user_and_tls(self):
        dsn = backup_database.connection_string(self.GOOD)
        self.assertIn('user=ucc_backup.abcdefghijklmnopqrst', dsn)
        self.assertIn('port=5432', dsn)
        self.assertIn('sslmode=require', dsn)
        self.assertNotIn('password', dsn)  # the password only ever comes from PGPASSWORD

    def test_unsafe_values_stop_the_backup(self):
        for change in ({'UCC_BACKUP_HOST': ''}, {'UCC_BACKUP_HOST': 'host; rm -rf /'}, {'UCC_BACKUP_PORT': 'x'},
                       {'UCC_SUPABASE_PROJECT_REF': 'short'}, {'UCC_BACKUP_SSLMODE': 'prefer'}):
            with self.subTest(change=change), self.assertRaises(SystemExit):
                backup_database.connection_string(self.GOOD | change)

    def test_only_the_student_tables_are_dumped_as_data(self):
        command = backup_database.dump_command(self.GOOD | {'UCC_PG_DUMP': 'pg_dump'})
        tables = {command[i + 1] for i, part in enumerate(command) if part == '--table'}
        self.assertEqual(tables, {f'public.{t}' for t in backup_database.BACKUP_TABLES})
        self.assertIn('--data-only', command)
        for secret_table in ('django_session', 'accounts_accounttoken', 'accounts_auththrottle', 'context_key'):
            self.assertFalse(any(secret_table in part for part in command))

    def test_backup_login_can_read_exactly_the_backed_up_tables(self):
        sql = (REPO / 'supabase' / 'backup' / 'backup_role.sql').read_text()
        granted = set(re.findall(r'public\.(\w+)', sql.split('GRANT SELECT ON', 1)[1].split('TO ucc_backup', 1)[0]))
        self.assertEqual(granted, set(backup_database.BACKUP_TABLES))
        self.assertIn('default_transaction_read_only = on', sql)
        self.assertNotIn('PASSWORD', sql.upper().replace('-- ', '').split('BEGIN;', 1)[1])  # no password in the file

    def test_missing_key_or_password_stops_before_anything_is_written(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        target = Path(folder) / 'b.dump.age'
        for env in ({'UCC_BACKUP_RECIPIENT': ''}, {'UCC_BACKUP_RECIPIENT': 'age1' + 'q' * 58, 'PGPASSWORD': ''}):
            with self.subTest(env=env), patch.dict(os.environ, self.GOOD | env), self.assertRaises(SystemExit):
                backup_database.main(['--output', str(target)])
            self.assertFalse(target.exists())


class BackupWorkflowTests(unittest.TestCase):
    def test_workflow_runs_only_on_schedule_or_by_hand_with_pinned_actions(self):
        workflow = (REPO / '.github' / 'workflows' / 'backup.yml').read_text()
        triggers = workflow.split('on:', 1)[1].split('permissions:', 1)[0]
        self.assertIn('schedule:', triggers)
        self.assertIn('workflow_dispatch:', triggers)
        self.assertNotIn('pull_request', triggers)
        self.assertIn('permissions:\n  contents: read', workflow)
        self.assertIn('retention-days: 30', workflow)
        for line in re.findall(r'uses: (\S+)', workflow):
            self.assertRegex(line, r'@[0-9a-f]{40}$')
        self.assertNotIn('echo $PGPASSWORD', workflow)


if __name__ == '__main__':
    unittest.main()
