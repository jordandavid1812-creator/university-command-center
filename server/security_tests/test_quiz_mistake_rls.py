"""Mistake bank: raw SQL as the runtime role under forced RLS. Each student sees and changes only
their own mistakes; a mistake can point only at the same student's saved quiz; the website can
never edit one; and the startup check refuses a runtime role that could."""
import hashlib
import uuid
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError, transaction
from psycopg import sql
from academics.ownership import require_runtime_role, student_transaction
from academics.services import InvalidRecord, RecordNotFound, ai, materials, mistakes
from .base import StudentSecurityCase

FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15}
QUIZ = {"questions": [{"question": f"Synthetic {n}?", "options": ["A", "B", "C", "D"], "correct": n % 4,
                       "reason": "Synthetic."} for n in range(5)]}


def token(label):
    return hashlib.sha256(label.encode()).hexdigest()


class QuizMistakeSecurityTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, identity, statement, parameters=None):
        with self.assertRaises(DatabaseError):
            with student_transaction(identity):  # its own atomic block rolls back
                self.sql(statement, parameters)

    def quiz(self, identity, course, label):
        material = materials.create(identity, course_id=course.pk, title=f"{label} notes", **FACTS)
        request, _ = ai.reserve(identity, tool="quiz", provider="gemini", model="synthetic-model-1",
                                characters_sent=100, truncated=False, consent_token_hash=token(label))
        return ai.succeed(identity, request.pk, material_id=material.pk, result=QUIZ)

    def setUp(self):
        super().setUp()
        self.quiz_a = self.quiz(self.a, self.course_a, "a")
        self.quiz_b = self.quiz(self.b, self.course_b, "b")
        mistakes.add(self.a, self.quiz_a.pk, [0, 2], 5)
        mistakes.add(self.b, self.quiz_b.pk, [1], 5)

    def test_rls_is_forced_and_each_student_sees_only_their_own(self):
        row = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c
                          WHERE c.relname = 'academics_quizmistake'""")
        self.assertEqual(row, [(True, True)])
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT question_index FROM academics_quizmistake ORDER BY 1"), [(0,), (2,)])
        with student_transaction(self.b):
            self.assertEqual(self.sql("SELECT question_index FROM academics_quizmistake ORDER BY 1"), [(1,)])
            self.assertEqual(self.sql("DELETE FROM academics_quizmistake WHERE result_id = %s", [self.quiz_a.pk]), 0)
        self.assertEqual(self.sql("SELECT count(*) FROM academics_quizmistake"), [(0,)])  # no signed context

    def test_a_mistake_can_point_only_at_your_own_quiz(self):
        statement = """INSERT INTO academics_quizmistake (id, owner_id, result_id, question_index, created_at, updated_at)
                       VALUES (%s, %s, %s, 3, now(), now())"""
        self.denied(self.b, statement, [uuid.uuid4(), self.b.student_id, self.quiz_a.pk])  # same-owner FK
        self.denied(self.b, statement, [uuid.uuid4(), self.a.student_id, self.quiz_a.pk])  # RLS WITH CHECK
        with self.assertRaises(RecordNotFound):
            mistakes.add(self.b, self.quiz_a.pk, [3], 5)

    def test_mistakes_are_never_edited_and_stay_in_range(self):
        self.denied(self.a, "UPDATE academics_quizmistake SET question_index = 4")
        self.denied(self.a, """INSERT INTO academics_quizmistake (id, owner_id, result_id, question_index, created_at, updated_at)
                               VALUES (%s, %s, %s, 60, now(), now())""", [uuid.uuid4(), self.a.student_id, self.quiz_a.pk])
        self.denied(self.a, """INSERT INTO academics_quizmistake (id, owner_id, result_id, question_index, created_at, updated_at)
                               VALUES (%s, %s, %s, 0, now(), now())""", [uuid.uuid4(), self.a.student_id, self.quiz_a.pk])
        for bad in ([5], [-1], [], ["1"]):
            with self.subTest(bad=bad), self.assertRaises(InvalidRecord):
                mistakes.add(self.a, self.quiz_a.pk, bad, 5)

    def test_deleting_the_quiz_or_account_removes_its_mistakes(self):
        ai.delete_result(self.a, self.quiz_a.pk)
        self.assertEqual(mistakes.list(self.a), [])
        self.assertEqual(len(mistakes.list(self.b)), 1)

    def test_startup_check_refuses_a_runtime_role_that_could_edit_mistakes(self):
        role = connections["runtime"].settings_dict["USER"]
        with connections["default"].cursor() as cursor:
            cursor.execute(sql.SQL("GRANT UPDATE (question_index) ON academics_quizmistake TO {}").format(sql.Identifier(role)))
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections["runtime"])
        finally:
            with connections["default"].cursor() as cursor:
                cursor.execute(sql.SQL("REVOKE UPDATE (question_index) ON academics_quizmistake FROM {}").format(sql.Identifier(role)))
        require_runtime_role(connections["runtime"])

    def test_startup_check_refuses_when_rls_is_switched_off(self):
        with connections["default"].cursor() as cursor:
            cursor.execute("ALTER TABLE academics_quizmistake NO FORCE ROW LEVEL SECURITY")
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections["runtime"])
        finally:
            with connections["default"].cursor() as cursor:
                cursor.execute("ALTER TABLE academics_quizmistake FORCE ROW LEVEL SECURITY")
