"""Timetable classes: owner-only through forced RLS, same owner as the course, database rules for
times, days and types, column-limited updates, removed with their course, and refused by the
startup check if weakened."""
import uuid
from datetime import time
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError, transaction
from psycopg import sql
from academics.ownership import require_runtime_role, student_transaction
from academics.services import RecordNotFound, class_sessions, courses
from .base import StudentSecurityCase


class ClassSessionSecurityTests(StudentSecurityCase):
    def setUp(self):
        super().setUp()
        self.class_a = class_sessions.create(self.a, course_id=self.course_a.pk, weekday=0, start_time=time(8),
                                             end_time=time(10), kind="lecture", venue="LT1")
        self.class_b = class_sessions.create(self.b, course_id=self.course_b.pk, weekday=0, start_time=time(8),
                                             end_time=time(10), kind="lab", venue="Lab B")

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

    def insert(self, owner, course, weekday=1, start="09:00", end="10:00", kind="lecture", venue=""):
        return ("""INSERT INTO academics_classsession (id, owner_id, course_id, weekday, start_time, end_time, kind,
                   venue, record_version, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, now(), now())""",
                [uuid.uuid4(), owner, course, weekday, start, end, kind, venue])

    def test_rls_is_forced_and_each_student_sees_only_their_own(self):
        rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd FROM pg_class c
                           JOIN pg_policy p ON p.polrelid=c.oid WHERE c.relname='academics_classsession'""")
        self.assertEqual(rows, [(True, True, "*")])
        self.assertEqual(self.sql("SELECT id FROM academics_classsession"), [])
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT id FROM academics_classsession"), [(self.class_a.pk,)])
            self.assertEqual(self.sql("UPDATE academics_classsession SET venue='X' WHERE id=%s", [self.class_b.pk]), 0)
            self.assertEqual(self.sql("DELETE FROM academics_classsession WHERE id=%s", [self.class_b.pk]), 0)
        self.assertEqual(class_sessions.retrieve(self.b, self.class_b.pk).venue, "Lab B")

    def test_database_refuses_bad_classes_and_other_owners_courses(self):
        with student_transaction(self.a):
            self.denied(*self.insert(self.a.student_id, self.course_b.pk))  # B's course
            self.denied(*self.insert(self.a.student_id, self.course_a.pk, start="10:00", end="09:00"))
            self.denied(*self.insert(self.a.student_id, self.course_a.pk, start="10:00", end="10:00"))
            self.denied(*self.insert(self.a.student_id, self.course_a.pk, weekday=7))
            self.denied(*self.insert(self.a.student_id, self.course_a.pk, kind="party"))
            self.denied(*self.insert(self.a.student_id, self.course_a.pk, venue=" LT1"))
            for change, value in (("owner_id", self.b.student_id), ("id", uuid.uuid4())):
                self.denied(f"UPDATE academics_classsession SET {change}=%s WHERE id=%s", [value, self.class_a.pk])
        # Another student's course is "not found", as for assignments: it does not even admit it exists.
        with self.assertRaises(RecordNotFound):
            class_sessions.create(self.a, course_id=self.course_b.pk, weekday=1, start_time=time(9),
                                  end_time=time(10), kind="lecture", venue="")

    def test_deleting_a_course_removes_its_classes(self):
        course = courses.retrieve(self.a, self.course_a.pk)
        # The seeded assignment protects the course; remove it first, as a student would.
        from academics.services import assignments
        assignments.delete(self.a, self.task_a.pk, version=1)
        courses.delete(self.a, course.pk, version=course.record_version)
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT count(*) FROM academics_classsession"), [(0,)])

    def test_startup_check_rejects_weakened_timetable(self):
        for weaken, restore in (
            ("ALTER TABLE academics_classsession NO FORCE ROW LEVEL SECURITY",
             "ALTER TABLE academics_classsession FORCE ROW LEVEL SECURITY"),
            ("GRANT TRUNCATE ON academics_classsession TO {role}",
             "REVOKE TRUNCATE ON academics_classsession FROM {role}"),
        ):
            self.migrator(weaken)
            try:
                with self.assertRaises(ImproperlyConfigured):
                    require_runtime_role(connections["runtime"])
            finally:
                self.migrator(restore)
        require_runtime_role(connections["runtime"])
