"""Inspect the real PostgreSQL schema and reverse/reapply app migrations."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigrationTests(TransactionTestCase):
    def test_fresh_academics_migrations_reverse_and_reapply(self):
        executor = MigrationExecutor(connection)
        target = ("academics", "0002_owner_relationships")
        try:
            executor.migrate([("academics", None)])
            self.assertNotIn("academics_course", connection.introspection.table_names())
        finally:
            MigrationExecutor(connection).migrate([target])
        self.assertIn("academics_course", connection.introspection.table_names())

    def test_composite_foreign_keys_are_validated_and_immediate(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT conname, contype, convalidated, condeferrable, array_length(conkey, 1)
                FROM pg_constraint WHERE conname IN
                ('course_semester_same_owner', 'assignment_course_same_owner')
            """)
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        for name, kind, validated, deferred, columns in rows:
            self.assertEqual((kind, validated, deferred, columns), ('f', True, False, 2))

    def test_credits_have_no_rounding_typemod_and_scale_check_exists(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = 'academics_course' AND column_name = 'credit_units'
            """)
            self.assertEqual(cursor.fetchone(), ('numeric', None, None))
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'course_credits_scale'")
            self.assertIn('scale(credit_units)', cursor.fetchone()[0])
