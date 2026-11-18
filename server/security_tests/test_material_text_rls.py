"""Search text of study files: owner-only through forced RLS, same owner as the file, saved once
and never updated, deleted with its material, and refused by the startup check if weakened."""
import uuid
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError, transaction
from psycopg import sql
from academics.ownership import require_runtime_role, student_transaction
from academics.services import InvalidRecord, materials, search_texts
from .base import StudentSecurityCase

CONTENT = b"Synthetic notes: TCP resends lost packets. 50% of _marks_ come from the exam."


class MaterialTextSecurityTests(StudentSecurityCase):
    def setUp(self):
        super().setUp()
        self.material_a = materials.create_with_file(self.a, title="A notes", course_id=self.course_a.pk,
                                                     original_filename="a.txt", file_type="txt", content=CONTENT)
        self.material_b = materials.create_with_file(self.b, title="B notes", course_id=self.course_b.pk,
                                                     original_filename="b.txt", file_type="txt", content=CONTENT)
        search_texts.save(self.a, self.material_a.pk, text=CONTENT.decode())
        search_texts.save(self.b, self.material_b.pk, text=CONTENT.decode())

    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None):
        with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
            self.sql(statement, parameters)

    def migrator(self, statement):
        role = connections["runtime"].settings_dict["USER"]
        with connections["default"].cursor() as cursor:
            cursor.execute(sql.SQL(statement).format(role=sql.Identifier(role)))

    def test_rls_is_forced_and_each_student_sees_only_their_own(self):
        rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd FROM pg_class c
                           JOIN pg_policy p ON p.polrelid=c.oid WHERE c.relname='academics_materialtext'""")
        self.assertEqual(rows, [(True, True, "*")])
        self.assertEqual(self.sql("SELECT id FROM academics_materialtext"), [])  # no student context
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT material_id FROM academics_materialtext"), [(self.material_a.pk,)])
            self.assertEqual(self.sql("DELETE FROM academics_materialtext WHERE material_id=%s",
                                      [self.material_b.pk]), 0)
        found, _ = search_texts.search(self.a, "TCP")
        self.assertEqual([material.pk for material, _ in found], [self.material_a.pk])

    def test_text_is_never_updated_and_must_share_the_files_owner(self):
        with student_transaction(self.a):
            self.denied("UPDATE academics_materialtext SET text='changed' WHERE material_id=%s", [self.material_a.pk])
            # Pointing A's text at B's material fails the same-owner link (and RLS).
            self.denied("""INSERT INTO academics_materialtext (id, owner_id, material_id, text, truncated, problem,
                           created_at, updated_at) VALUES (%s, %s, %s, 'x', false, '', now(), now())""",
                        [uuid.uuid4(), self.a.student_id, self.material_b.pk])
        with self.assertRaises(InvalidRecord):
            search_texts.save(self.a, self.material_b.pk, text="x")

    def test_text_or_a_reason_never_both(self):
        other = materials.create_with_file(self.a, title="A scan", course_id=self.course_a.pk,
                                           original_filename="scan.txt", file_type="txt", content=b"Scan")
        for text, problem in (("", ""), ("text", "no_text"), ("", "made_up")):
            with self.subTest(text=text, problem=problem), self.assertRaises(InvalidRecord):
                search_texts.save(self.a, other.pk, text=text, problem=problem)
        with student_transaction(self.a):
            self.denied("""INSERT INTO academics_materialtext (id, owner_id, material_id, text, truncated, problem,
                           created_at, updated_at) VALUES (%s, %s, %s, '', false, '', now(), now())""",
                        [uuid.uuid4(), self.a.student_id, other.pk])
        search_texts.save(self.a, other.pk, problem="no_text")
        self.assertEqual(search_texts.search(self.a, "anything")[1], 1)
        search_texts.save(self.a, other.pk, text="second save does nothing")
        self.assertEqual(search_texts.missing(self.a, 10), ([], 0))

    def test_deleting_the_material_deletes_its_text(self):
        materials.delete(self.a, self.material_a.pk, version=self.material_a.record_version)
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT count(*) FROM academics_materialtext"), [(0,)])

    def test_search_is_literal(self):
        self.assertEqual(len(search_texts.search(self.a, "50%")[0]), 1)
        self.assertEqual(len(search_texts.search(self.a, "_marks_")[0]), 1)
        self.assertEqual(search_texts.search(self.a, "5_%")[0], [])  # wildcards are plain characters

    def test_startup_check_rejects_weakened_search_text(self):
        for weaken, restore in (
            ("ALTER TABLE academics_materialtext NO FORCE ROW LEVEL SECURITY",
             "ALTER TABLE academics_materialtext FORCE ROW LEVEL SECURITY"),
            ("GRANT UPDATE (text) ON academics_materialtext TO {role}",
             "REVOKE UPDATE (text) ON academics_materialtext FROM {role}"),
            ("GRANT TRUNCATE ON academics_materialtext TO {role}",
             "REVOKE TRUNCATE ON academics_materialtext FROM {role}"),
        ):
            self.migrator(weaken)
            try:
                with self.assertRaises(ImproperlyConfigured):
                    require_runtime_role(connections["runtime"])
            finally:
                self.migrator(restore)
        require_runtime_role(connections["runtime"])
