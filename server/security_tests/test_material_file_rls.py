"""Stored material files: owner-only through forced RLS, and never updated."""
import hashlib
import uuid
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from academics.services import materials
from .base import StudentSecurityCase

CONTENT = b"Synthetic notes"
DIGEST = hashlib.sha256(CONTENT).hexdigest()
FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": len(CONTENT)}


class MaterialFileSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None):
        with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
            self.sql(statement, parameters)

    def insert_file(self, owner, material, content=CONTENT, digest=DIGEST):
        return ("""INSERT INTO academics_materialfile (id, owner_id, material_id, content, sha256, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, now(), now())""", [uuid.uuid4(), owner, material, content, digest])

    def store(self, identity, material):
        statement, parameters = self.insert_file(identity.student_id, material.pk)
        with student_transaction(identity):
            self.sql(statement, parameters)
        return parameters[0]

    def setUp(self):
        super().setUp()
        self.material_a = materials.create(self.a, course_id=self.course_a.pk, title="A notes", **FACTS)
        self.material_b = materials.create(self.b, course_id=self.course_b.pk, title="B notes", **FACTS)
        self.spare_a = materials.create(self.a, course_id=self.course_a.pk, title="A spare", **FACTS)
        self.spare_b = materials.create(self.b, course_id=self.course_b.pk, title="B spare", **FACTS)
        self.file_a = self.store(self.a, self.material_a)
        self.file_b = self.store(self.b, self.material_b)

    def test_rls_is_enabled_forced_and_covers_all_commands(self):
        rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
                   FROM pg_class c JOIN pg_policy p ON p.polrelid=c.oid
                   WHERE c.relname='academics_materialfile'""")
        self.assertEqual(rows, [(True, True, '*', True, True)])

    def test_no_context_sees_and_changes_nothing(self):
        self.assertEqual(self.sql("SELECT id FROM academics_materialfile"), [])
        self.assertEqual(self.sql("DELETE FROM academics_materialfile"), 0)
        self.denied(*self.insert_file(self.a.student_id, self.spare_a.pk))

    def test_student_reads_only_own_file_bytes(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT id, content FROM academics_materialfile"), [(self.file_a, CONTENT)])

    def test_cannot_store_a_file_for_another_student_or_their_material(self):
        with student_transaction(self.a):
            self.denied(*self.insert_file(self.b.student_id, self.spare_b.pk))
            self.denied(*self.insert_file(self.a.student_id, self.spare_b.pk))

    def test_stored_files_can_never_be_updated(self):
        with student_transaction(self.a):
            for change, value in (("content", b"changed"), ("sha256", "0" * 64),
                                  ("material_id", self.spare_a.pk), ("owner_id", self.b.student_id)):
                self.denied(f"UPDATE academics_materialfile SET {change}=%s WHERE id=%s", [value, self.file_a])
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT content FROM academics_materialfile"), [(CONTENT,)])

    def test_empty_oversized_and_bad_fingerprint_files_are_rejected(self):
        with student_transaction(self.a):
            self.denied(*self.insert_file(self.a.student_id, self.spare_a.pk, content=b""))
            self.denied(*self.insert_file(self.a.student_id, self.spare_a.pk, digest="NOT-A-SHA256"))
            self.denied(*self.insert_file(self.a.student_id, self.spare_a.pk,
                                          content=b"a" * (10 * 1024 * 1024 + 1)))

    def test_delete_is_owner_only_and_material_delete_removes_its_file(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("DELETE FROM academics_materialfile WHERE id=%s", [self.file_b]), 0)
        materials.delete(self.a, self.material_a.pk, version=1)
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT id FROM academics_materialfile"), [])
        with student_transaction(self.b):
            self.assertEqual(self.sql("SELECT id FROM academics_materialfile"), [(self.file_b,)])
