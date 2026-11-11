import os
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AuthenticationSchemaTests(TransactionTestCase):
    databases = {'default', 'runtime', 'auth'}

    def test_account_migration_reverses_without_removing_academic_rls(self):
        connection = connections['default']
        try:
            MigrationExecutor(connection).migrate([('accounts', '0001_initial')])
            self.assertNotIn('accounts_accounttoken', connection.introspection.table_names())
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_class WHERE relname IN ('academics_course','academics_assignment','academics_semester') AND relrowsecurity AND relforcerowsecurity")
                self.assertEqual(cursor.fetchone(), (3,))
        finally:
            MigrationExecutor(connection).migrate([('accounts', '0002_accounttoken_auththrottle_student_email_and_more')])
            call_command('configure_runtime', verbosity=0)
            call_command('configure_auth_role', verbosity=0)
        self.assertIn('accounts_accounttoken', connection.introspection.table_names())

    def test_auth_role_provisioning_rejects_shared_runtime_or_privileged_role(self):
        for role in (os.environ['UCC_RUNTIME_ROLE'], connections['default'].settings_dict['USER']):
            with patch.dict(os.environ, {'UCC_AUTH_ROLE': role}):
                with self.assertRaises(CommandError):
                    call_command('configure_auth_role', verbosity=0)
