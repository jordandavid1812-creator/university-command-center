"""Study materials: each student can reach only their own rows, even with raw SQL."""

import uuid
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from .base import StudentSecurityCase


class StudyMaterialSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None):
        with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
            self.sql(statement, parameters)

    def insert_material(self, owner, course):
        return (
            """INSERT INTO academics_studymaterial
                   (id, owner_id, course_id, title, original_filename, file_type,
                    size_bytes, record_version, created_at, updated_at)
                   VALUES (%s, %s, %s, 'Synthetic notes', 'notes.txt', 'txt', 10, 1, now(), now())""",
            [uuid.uuid4(), owner, course],
        )

    def setUp(self):
        super().setUp()
        statement, parameters = self.insert_material(
            self.a.student_id, self.course_a.pk
        )
        with student_transaction(self.a):
            self.sql(statement, parameters)
        self.material_a = parameters[0]
        statement, parameters = self.insert_material(
            self.b.student_id, self.course_b.pk
        )
        with student_transaction(self.b):
            self.sql(statement, parameters)
        self.material_b = parameters[0]

    def test_rls_is_enabled_forced_and_covers_all_commands(self):
        rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
                   FROM pg_class c JOIN pg_policy p ON p.polrelid=c.oid
                   WHERE c.relname='academics_studymaterial'""")
        self.assertEqual(rows, [(True, True, "*", True, True)])

    def test_no_context_sees_and_changes_nothing(self):
        self.assertEqual(self.sql("SELECT id FROM academics_studymaterial"), [])
        self.assertEqual(self.sql("DELETE FROM academics_studymaterial"), 0)
        self.denied(*self.insert_material(self.a.student_id, self.course_a.pk))

    def test_student_sees_only_own_material(self):
        with student_transaction(self.a):
            self.assertEqual(
                self.sql("SELECT id FROM academics_studymaterial"), [(self.material_a,)]
            )

    def test_cannot_change_or_delete_other_students_material(self):
        with student_transaction(self.a):
            self.assertEqual(
                self.sql(
                    "UPDATE academics_studymaterial SET title='Changed' WHERE id=%s",
                    [self.material_b],
                ),
                0,
            )
            self.assertEqual(
                self.sql(
                    "DELETE FROM academics_studymaterial WHERE id=%s", [self.material_b]
                ),
                0,
            )
        with student_transaction(self.b):
            self.assertEqual(
                self.sql("SELECT title FROM academics_studymaterial"),
                [("Synthetic notes",)],
            )

    def test_cannot_create_for_another_student_or_use_their_course(self):
        with student_transaction(self.a):
            self.denied(*self.insert_material(self.b.student_id, self.course_b.pk))
            self.denied(*self.insert_material(self.a.student_id, self.course_b.pk))
            self.denied(
                "UPDATE academics_studymaterial SET course_id=%s WHERE id=%s",
                [self.course_b.pk, self.material_a],
            )
            self.denied(
                "UPDATE academics_studymaterial SET owner_id=%s WHERE id=%s",
                [self.b.student_id, self.material_a],
            )

    def test_file_facts_and_identifiers_cannot_be_rewritten(self):
        with student_transaction(self.a):
            for change in (
                "original_filename='other.pdf'",
                "file_type='pdf'",
                "size_bytes=5",
                "created_at=now()",
                "id=gen_random_uuid()",
            ):
                self.denied(
                    f"UPDATE academics_studymaterial SET {change} WHERE id=%s",
                    [self.material_a],
                )

    def test_own_material_can_still_be_renamed(self):
        with student_transaction(self.a):
            self.assertEqual(
                self.sql(
                    """UPDATE academics_studymaterial
                SET title='Week 1 notes', record_version=2, updated_at=now() WHERE id=%s""",
                    [self.material_a],
                ),
                1,
            )
