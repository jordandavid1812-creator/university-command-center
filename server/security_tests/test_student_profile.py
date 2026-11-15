"""Student profiles: owner-only through forced RLS, column-limited updates, never deleted."""
import uuid
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from academics.services import InvalidRecord, RecordConflict, profiles
from .base import StudentSecurityCase

DETAILS = {"display_name": "Synthetic A", "institution": "Synthetic University", "programme": "B.Sc. Testing",
           "level": "200", "matric_number": "SYN/2026/0001"}


class StudentProfileSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None):
        with self.assertRaises(DatabaseError), transaction.atomic(using="runtime"):
            self.sql(statement, parameters)

    def insert(self, owner):
        return ("""INSERT INTO academics_studentprofile (id, owner_id, display_name, institution, programme, level,
                   matric_number, record_version, created_at, updated_at)
                   VALUES (%s, %s, 'X', '', '', '', '', 1, now(), now())""", [uuid.uuid4(), owner])

    def setUp(self):
        super().setUp()
        self.profile_a = profiles.create(self.a, **DETAILS)
        self.profile_b = profiles.create(self.b, **dict(DETAILS, display_name="Synthetic B", matric_number="SYN/B/9"))

    def test_rls_is_enabled_forced_and_covers_all_commands(self):
        rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
                   FROM pg_class c JOIN pg_policy p ON p.polrelid=c.oid
                   WHERE c.relname='academics_studentprofile'""")
        self.assertEqual(rows, [(True, True, '*', True, True)])

    def test_no_context_sees_nothing(self):
        self.assertEqual(self.sql("SELECT id FROM academics_studentprofile"), [])
        self.denied(*self.insert(self.a.student_id))

    def test_each_student_reads_and_changes_only_their_own_profile(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT matric_number FROM academics_studentprofile"), [("SYN/2026/0001",)])
            self.assertEqual(self.sql("UPDATE academics_studentprofile SET display_name='Changed' WHERE id=%s",
                                      [self.profile_b.pk]), 0)
            self.denied(*self.insert(self.b.student_id))
        self.assertEqual(profiles.current(self.b).display_name, "Synthetic B")
        self.assertEqual(profiles.current(self.a).pk, self.profile_a.pk)

    def test_owner_identifiers_and_deletion_are_refused(self):
        with student_transaction(self.a):
            for change, value in (("owner_id", self.b.student_id), ("id", uuid.uuid4())):
                self.denied(f"UPDATE academics_studentprofile SET {change}=%s WHERE id=%s", [value, self.profile_a.pk])
            self.denied("DELETE FROM academics_studentprofile WHERE id=%s", [self.profile_a.pk])
            self.denied("TRUNCATE academics_studentprofile")
        with self.assertRaises(InvalidRecord):
            profiles.delete(self.a, self.profile_a.pk, version=1)

    def test_one_profile_per_student_and_versioned_updates(self):
        with self.assertRaises(InvalidRecord):
            profiles.create(self.a, display_name="Second")
        updated = profiles.update(self.a, self.profile_a.pk, version=1, level="300")
        self.assertEqual((updated.level, updated.record_version), ("300", 2))
        with self.assertRaises(RecordConflict):
            profiles.update(self.a, self.profile_a.pk, version=1, level="400")

    def test_invalid_values_and_server_fields_are_rejected(self):
        for bad in ({"level": "800"}, {"matric_number": "../etc"}, {"matric_number": "a b"},
                    {"display_name": " padded"}, {"owner_id": self.b.student_id}, {"record_version": 9}):
            with self.subTest(bad=bad), self.assertRaises(InvalidRecord):
                profiles.update(self.a, self.profile_a.pk, version=1, **bad)
