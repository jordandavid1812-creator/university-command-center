import os
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from psycopg import sql
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SecurityMigrationTests(TransactionTestCase):
    databases = {"default", "runtime"}

    def test_security_migrations_reverse_and_reapply_without_weakening_foundation(self):
        connection = connections["default"]
        try:
            MigrationExecutor(connection).migrate([("academics", "0002_owner_relationships")])
            with connection.cursor() as cursor:
                cursor.execute("SELECT relrowsecurity FROM pg_class WHERE relname='academics_course'")
                self.assertEqual(cursor.fetchone(), (False,))
                cursor.execute("SELECT count(*) FROM pg_constraint WHERE conname IN ('course_semester_same_owner','assignment_course_same_owner')")
                self.assertEqual(cursor.fetchone(), (2,))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes("academics"))
            call_command("configure_runtime", verbosity=0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='academics_course'")
            self.assertEqual(cursor.fetchone(), (True, True))
            cursor.execute("SELECT count(*) FROM pg_constraint WHERE conname IN ('course_credits_scale','course_credits_range','course_grade_valid','course_semester_same_owner','assignment_course_same_owner')")
            self.assertEqual(cursor.fetchone(), (5,))

    def test_verifier_is_hardened_and_secrets_are_not_runtime_readable(self):
        with connections['default'].cursor() as cursor:
            cursor.execute("""SELECT p.prosecdef, p.proconfig, r.rolname
                FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid
                JOIN pg_roles r ON r.oid=p.proowner
                WHERE n.nspname='ucc_security' AND p.proname='current_student'""")
            definer, config, owner = cursor.fetchone()
            self.assertTrue(definer)
            self.assertIn('search_path=pg_catalog', config)
            self.assertEqual(owner, connections['default'].settings_dict['USER'])
        with connections['runtime'].cursor() as cursor:
            cursor.execute("SELECT has_table_privilege(current_user, 'ucc_security.context_key', 'SELECT')")
            self.assertEqual(cursor.fetchone(), (False,))

    def test_provisioning_removes_old_column_and_public_grants(self):
        role = connections['runtime'].settings_dict['USER']
        with connections['default'].cursor() as cursor:
            cursor.execute(sql.SQL("GRANT UPDATE (owner_id) ON academics_course TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT SELECT (secret) ON ucc_security.context_key TO {}").format(sql.Identifier(role)))
            cursor.execute("GRANT SELECT (username) ON accounts_student TO PUBLIC")
        call_command("configure_runtime", verbosity=0)
        with connections['runtime'].cursor() as cursor:
            for table, column, privilege in (
                ('academics_course', 'owner_id', 'UPDATE'),
                ('ucc_security.context_key', 'secret', 'SELECT'),
                ('accounts_student', 'username', 'SELECT'),
            ):
                cursor.execute("SELECT has_column_privilege(current_user, %s, %s, %s)", [table, column, privilege])
                self.assertEqual(cursor.fetchone(), (False,))

    def test_privileged_role_is_rejected_by_provisioning(self):
        with patch.dict(os.environ, {'UCC_RUNTIME_ROLE': connections['default'].settings_dict['USER']}):
            with self.assertRaises(CommandError):
                call_command("configure_runtime", verbosity=0)
