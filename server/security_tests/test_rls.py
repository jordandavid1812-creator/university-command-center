"""Use actual restricted LOGIN connections; never SET ROLE from a superuser."""
import uuid
import psycopg
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from academics.services import assignments, courses, semesters
from .base import StudentSecurityCase


class RowSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None):
        with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
            self.sql(statement, parameters)

    def insert_semester(self, owner):
        return ("""INSERT INTO academics_semester
                   (id, owner_id, label, display_order, record_version, created_at, updated_at)
                   VALUES (%s, %s, 'Synthetic SQL', 0, 1, now(), now())""", [uuid.uuid4(), owner])

    def test_runtime_login_has_no_bypass_ddl_or_role_memberships(self):
        rows = self.sql("""SELECT current_user, session_user, r.rolsuper, r.rolbypassrls,
                    r.rolcreatedb, r.rolcreaterole, r.rolinherit,
                    EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                    FROM pg_roles r WHERE rolname=current_user""")
        self.assertEqual(rows[0][:2], (connections["runtime"].settings_dict["USER"],) * 2)
        self.assertEqual(rows[0][2:], (False,) * 6)
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
            owner, superuser, bypass = cursor.fetchone()
        self.assertNotEqual(owner, rows[0][0])
        self.assertEqual((superuser, bypass), (False, False))

    def test_rls_is_enabled_forced_and_policies_cover_all_commands(self):
        rows = self.sql("""SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.polcmd, p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
                   FROM pg_class c JOIN pg_policy p ON p.polrelid=c.oid
                   WHERE c.relname IN ('academics_semester','academics_course','academics_assignment')
                   ORDER BY c.relname""")
        self.assertEqual(len(rows), 3)
        for name, enabled, forced, command, using, check in rows:
            self.assertEqual((enabled, forced, command, using, check), (True, True, '*', True, True))

    def test_no_context_denies_select_insert_update_and_delete(self):
        for table in ('academics_semester', 'academics_course', 'academics_assignment'):
            self.assertEqual(self.sql(f'SELECT id FROM {table}'), [])
            self.assertEqual(self.sql(f'DELETE FROM {table}'), 0)
        self.assertEqual(self.sql("UPDATE academics_course SET actual_grade='F'"), 0)
        self.denied(*self.insert_semester(self.a.student_id))

    def test_plain_forged_and_malformed_owner_settings_fail_closed(self):
        for identifier in (str(self.a.student_id), str(self.b.student_id), 'invalid-uuid', ''):
            with transaction.atomic(using="runtime"):
                self.sql("SELECT set_config('ucc.student_id', %s, true), set_config('ucc.student_signature', %s, true)",
                         [identifier, '0' * 64])
                self.assertEqual(self.sql("SELECT ucc_security.current_student()"), [(None,)])
                self.assertEqual(self.sql("SELECT id FROM academics_course"), [])
                self.denied(*self.insert_semester(self.b.student_id))

    def test_signed_context_cannot_be_changed_to_another_student(self):
        with student_transaction(self.a):
            self.sql("SELECT set_config('ucc.student_id', %s, true)", [str(self.b.student_id)])
            self.assertEqual(self.sql("SELECT id FROM academics_course"), [])
            self.assertEqual(self.sql("UPDATE academics_course SET actual_grade='F' WHERE id=%s", [self.course_b.pk]), 0)
            self.denied(*self.insert_semester(self.b.student_id))
        self.assertEqual(courses.retrieve(self.b, self.course_b.pk).actual_grade, 'A')

    def test_direct_sql_select_only_returns_own_rows(self):
        with student_transaction(self.a):
            for table, own in (('academics_semester', self.sem_a), ('academics_course', self.course_a),
                               ('academics_assignment', self.task_a)):
                self.assertEqual(self.sql(f'SELECT id FROM {table}'), [(own.pk,)])

    def test_direct_sql_cannot_modify_other_students_grades_or_delete_assignments(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("UPDATE academics_course SET actual_grade='F' WHERE id=%s", [self.course_b.pk]), 0)
            self.assertEqual(self.sql("DELETE FROM academics_assignment WHERE id=%s", [self.task_b.pk]), 0)
        self.assertEqual(courses.retrieve(self.b, self.course_b.pk).actual_grade, 'A')
        self.assertEqual(assignments.retrieve(self.b, self.task_b.pk).pk, self.task_b.pk)

    def test_with_check_rejects_cross_owner_inserts_and_reassignment(self):
        with student_transaction(self.a):
            self.denied(*self.insert_semester(self.b.student_id))
            for table, record in (('academics_semester', self.sem_a), ('academics_course', self.course_a),
                                   ('academics_assignment', self.task_a)):
                self.denied(f'UPDATE {table} SET owner_id=%s WHERE id=%s', [self.b.student_id, record.pk])

    def test_composite_constraints_still_reject_cross_owner_parents(self):
        with student_transaction(self.a):
            self.denied("UPDATE academics_course SET semester_id=%s WHERE id=%s", [self.sem_b.pk, self.course_a.pk])
            self.denied("UPDATE academics_assignment SET course_id=%s WHERE id=%s", [self.course_b.pk, self.task_a.pk])

    def test_valid_direct_sql_own_dml_remains_possible(self):
        with student_transaction(self.a):
            statement, parameters = self.insert_semester(self.a.student_id)
            self.assertEqual(self.sql(statement, parameters), 1)
            self.assertEqual(self.sql("UPDATE academics_semester SET label='Updated' WHERE id=%s", [parameters[0]]), 1)
            self.assertEqual(self.sql("DELETE FROM academics_semester WHERE id=%s", [parameters[0]]), 1)

    def test_runtime_cannot_read_keys_accounts_migrations_or_change_security(self):
        migrator = connections['default'].settings_dict['USER']
        # This identifier comes from the controlled test configuration, not a request.
        from psycopg import sql
        statements = (
            'SELECT secret FROM ucc_security.context_key',
            'SELECT password FROM accounts_student',
            'SELECT * FROM django_migrations',
            'ALTER TABLE academics_course DISABLE ROW LEVEL SECURITY',
            'TRUNCATE academics_course CASCADE',
            'CREATE TABLE public.forbidden (id integer)',
            'CREATE TABLE ucc_security.forbidden (id integer)',
            "UPDATE ucc_security.context_key SET secret=decode(repeat('00',32),'hex')",
            'DROP FUNCTION ucc_security.current_student()',
            sql.SQL('SET ROLE {}').format(sql.Identifier(migrator)),
        )
        for statement in statements:
            self.denied(statement)

    def test_runtime_cannot_rewrite_identifiers_or_creation_timestamps(self):
        with student_transaction(self.a):
            for table, record in (("academics_semester", self.sem_a), ("academics_course", self.course_a),
                                  ("academics_assignment", self.task_a)):
                self.denied(f"UPDATE {table} SET id=%s WHERE id=%s", [uuid.uuid4(), record.pk])
                self.denied(f"UPDATE {table} SET created_at=now() WHERE id=%s", [record.pk])

    def test_disabling_row_security_setting_does_not_bypass_policies(self):
        with transaction.atomic(using="runtime"):
            self.sql("SET LOCAL row_security=off")
            self.denied("SELECT id FROM academics_course")

    def test_table_owner_also_fails_closed_without_context(self):
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT id FROM academics_course")
            self.assertEqual(cursor.fetchall(), [])

    def test_connection_reuse_clears_context_after_commit(self):
        pid = self.sql("SELECT pg_backend_pid()")[0][0]
        semesters.list(self.a)
        self.assertEqual(self.sql("SELECT pg_backend_pid()")[0][0], pid)
        self.assertEqual(self.sql("SELECT ucc_security.current_student()"), [(None,)])
        self.assertEqual(self.sql("SELECT id FROM academics_semester"), [])
        self.assertEqual([s.pk for s in semesters.list(self.b)], [self.sem_b.pk])
        self.assertEqual(self.sql("SELECT pg_backend_pid()")[0][0], pid)
        self.assertEqual(self.sql("SELECT id FROM academics_semester"), [])

    def test_connection_reuse_clears_context_after_rollback(self):
        pid = self.sql("SELECT pg_backend_pid()")[0][0]
        with self.assertRaises(RuntimeError):
            with student_transaction(self.a):
                raise RuntimeError("Synthetic rollback")
        self.assertEqual(self.sql("SELECT pg_backend_pid()")[0][0], pid)
        self.assertEqual(self.sql("SELECT id FROM academics_course"), [])
        self.assertEqual([s.pk for s in semesters.list(self.b)], [self.sem_b.pk])

    def test_captured_signature_cannot_be_replayed_in_a_new_transaction(self):
        with student_transaction(self.a):
            proof = self.sql("SELECT current_setting('ucc.student_signature')")[0][0]
        with transaction.atomic(using="runtime"):
            self.sql("SELECT set_config('ucc.student_id', %s, true), set_config('ucc.student_signature', %s, true)",
                     [str(self.a.student_id), proof])
            self.assertEqual(self.sql("SELECT id FROM academics_course"), [])

    def test_session_level_stale_context_does_not_leak_identity(self):
        with student_transaction(self.a):
            proof = self.sql("SELECT current_setting('ucc.student_signature')")[0][0]
        self.sql("SELECT set_config('ucc.student_id', %s, false), set_config('ucc.student_signature', %s, false)",
                 [str(self.a.student_id), proof])
        self.assertEqual(self.sql("SELECT id FROM academics_course"), [])
        self.assertEqual([s.pk for s in semesters.list(self.b)], [self.sem_b.pk])
        self.assertEqual(self.sql("SELECT id FROM academics_course"), [])

    def test_captured_signature_cannot_be_replayed_on_another_backend(self):
        config = connections['runtime'].settings_dict
        with student_transaction(self.a):
            proof, pid = self.sql("SELECT current_setting('ucc.student_signature'), pg_backend_pid()")[0]
            with psycopg.connect(dbname=config['NAME'], user=config['USER'], password=config['PASSWORD'],
                                 host=config['HOST'], port=config['PORT']) as second:
                second.execute("SELECT set_config('ucc.student_id', %s, true), set_config('ucc.student_signature', %s, true)",
                               [str(self.a.student_id), proof])
                self.assertNotEqual(second.execute("SELECT pg_backend_pid()").fetchone()[0], pid)
                self.assertEqual(second.execute("SELECT id FROM academics_course").fetchall(), [])
