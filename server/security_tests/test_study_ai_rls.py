"""AI ledger and results: raw SQL as the runtime role under forced RLS, grants and constraints."""
import hashlib
import json
import uuid
from django.db import connections, DatabaseError, transaction
from academics.ownership import student_transaction
from academics.services import ai, materials
from .base import StudentSecurityCase

FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15}


def token(label):
    return hashlib.sha256(label.encode()).hexdigest()


class StudyAiRlsTests(StudentSecurityCase):
    def sql(self, statement, parameters=None):
        with connections["runtime"].cursor() as cursor:
            cursor.execute(statement, parameters)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def denied(self, statement, parameters=None, identity=None):
        with self.assertRaises(DatabaseError):
            if identity is None:
                with transaction.atomic(using="runtime"):
                    self.sql(statement, parameters)
            else:
                with student_transaction(identity):  # its own atomic block rolls back
                    self.sql(statement, parameters)

    def insert_request(self, owner, **overrides):
        values = {"id": uuid.uuid4(), "owner_id": owner, "tool": "summary", "provider": "gemini",
                  "model": "synthetic-model-1", "status": "failed", "characters_sent": 100, "truncated": False,
                  "consent_token_hash": token(str(uuid.uuid4())), "error_category": "network"}
        values.update(overrides)
        columns = ", ".join(values) + ", created_at, updated_at"
        marks = ", ".join(["%s"] * len(values)) + ", now(), now()"
        return f"INSERT INTO academics_studyairequest ({columns}) VALUES ({marks})", list(values.values())

    def insert_result(self, owner, material, request, **overrides):
        values = {"id": uuid.uuid4(), "owner_id": owner, "material_id": material, "request_id": request,
                  "tool": "summary", "question": "", "result": json.dumps({"points": ["Synthetic"]}),
                  "shape_version": 1}
        values.update(overrides)
        columns = ", ".join(values) + ", created_at, updated_at"
        marks = ", ".join(["%s"] * len(values)) + ", now(), now()"
        return f"INSERT INTO academics_studyairesult ({columns}) VALUES ({marks})", list(values.values())

    def make(self, identity, material, label):
        request, _ = ai.reserve(identity, tool="summary", provider="gemini", model="synthetic-model-1",
                                characters_sent=100, truncated=False, consent_token_hash=token(label))
        result = ai.succeed(identity, request.pk, material_id=material.pk, result={"points": ["Synthetic"]})
        return request, result

    def setUp(self):
        super().setUp()
        self.material_a = materials.create(self.a, course_id=self.course_a.pk, title="A notes", **FACTS)
        self.material_b = materials.create(self.b, course_id=self.course_b.pk, title="B notes", **FACTS)
        self.request_a, self.result_a = self.make(self.a, self.material_a, "a")
        self.request_b, self.result_b = self.make(self.b, self.material_b, "b")

    def test_rls_is_enabled_forced_and_covers_all_commands(self):
        for table in ("academics_studyairequest", "academics_studyairesult"):
            with self.subTest(table=table):
                rows = self.sql("""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd,
                           p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
                           FROM pg_class c JOIN pg_policy p ON p.polrelid=c.oid WHERE c.relname=%s""", [table])
                self.assertEqual(rows, [(True, True, '*', True, True)])

    def test_no_context_sees_and_changes_nothing(self):
        for table in ("academics_studyairequest", "academics_studyairesult"):
            self.assertEqual(self.sql(f"SELECT id FROM {table}"), [])
        self.assertEqual(self.sql("DELETE FROM academics_studyairesult"), 0)
        self.assertEqual(self.sql("UPDATE academics_studyairequest SET status='interrupted'"), 0)
        self.denied(*self.insert_request(self.a.student_id))

    def test_student_reads_only_own_rows(self):
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT id FROM academics_studyairequest"), [(self.request_a.pk,)])
            self.assertEqual(self.sql("SELECT id FROM academics_studyairesult"), [(self.result_a.pk,)])
            self.assertEqual(self.sql("DELETE FROM academics_studyairesult WHERE id=%s", [self.result_b.pk]), 0)
            self.assertEqual(self.sql("UPDATE academics_studyairequest SET status='interrupted' WHERE id=%s",
                                      [self.request_b.pk]), 0)

    def test_cannot_write_rows_for_another_student_or_link_their_records(self):
        self.denied(*self.insert_request(self.b.student_id), identity=self.a)
        spare, _ = ai.reserve(self.a, tool="summary", provider="grok", model="synthetic-model-1",
                              characters_sent=10, truncated=False, consent_token_hash=token("spare"))
        ai.fail(self.a, spare.pk, "network")
        # Another student's material, or another student's request, breaks the same-owner keys.
        self.denied(*self.insert_result(self.a.student_id, self.material_b.pk, spare.pk), identity=self.a)
        self.denied(*self.insert_result(self.a.student_id, self.material_a.pk, self.request_b.pk), identity=self.a)
        self.denied(*self.insert_result(self.b.student_id, self.material_b.pk, self.request_b.pk), identity=self.a)

    def test_ledger_is_never_deleted_and_only_status_fields_change(self):
        in_flight, _ = ai.reserve(self.a, tool="quiz", provider="grok", model="synthetic-model-1",
                                  characters_sent=10, truncated=False, consent_token_hash=token("flight"))
        with student_transaction(self.a):
            self.assertEqual(self.sql("""UPDATE academics_studyairequest SET status='failed',
                                         error_category='network', updated_at=now() WHERE id=%s""",
                                      [in_flight.pk]), 1)
        self.denied("DELETE FROM academics_studyairequest WHERE id=%s", [self.request_a.pk], identity=self.a)
        for column, value in (("tool", "quiz"), ("provider", "grok"), ("characters_sent", 1),
                              ("created_at", "2020-01-01"), ("consent_token_hash", token("x")), ("owner_id", self.b.student_id)):
            with self.subTest(column=column):
                self.denied(f"UPDATE academics_studyairequest SET {column}=%s WHERE id=%s", [value, self.request_a.pk],
                            identity=self.a)

    def test_results_are_never_updated(self):
        for column, value in (("result", json.dumps({"points": ["Changed"]})), ("question", "Why?"),
                              ("material_id", self.material_a.pk), ("updated_at", "2020-01-01")):
            with self.subTest(column=column):
                self.denied(f"UPDATE academics_studyairesult SET {column}=%s WHERE id=%s", [value, self.result_a.pk],
                            identity=self.a)

    def test_runtime_cannot_truncate_either_table(self):
        for table in ("academics_studyairequest", "academics_studyairesult"):
            with self.subTest(table=table):
                self.denied(f"TRUNCATE {table} CASCADE")

    def test_material_with_results_cannot_be_deleted_around_django(self):
        self.denied("DELETE FROM academics_studymaterial WHERE id=%s", [self.material_a.pk], identity=self.a)

    def spare_request(self, tool="summary"):
        """A fresh, finished request of this student, so each result case has its own request."""
        request, _ = ai.reserve(self.a, tool=tool, provider="gemini", model="synthetic-model-1", characters_sent=10,
                                truncated=False, consent_token_hash=token(str(uuid.uuid4())))
        ai.fail(self.a, request.pk, "timeout")
        return request

    def test_check_constraints_refuse_unknown_or_unsafe_values(self):
        # Positive controls: the unchanged baseline rows are accepted, so each refusal below
        # is caused by its one changed value.
        baseline = self.spare_request()
        with student_transaction(self.a):
            self.assertEqual(self.sql(*self.insert_request(self.a.student_id)), 1)
            self.assertEqual(self.sql(*self.insert_result(self.a.student_id, self.material_a.pk, baseline.pk)), 1)
        bad_requests = {
            "tool": {"tool": "essay"}, "provider": {"provider": "other"}, "status": {"status": "done"},
            "category": {"error_category": "mystery"}, "category without failure": {"status": "succeeded"},
            "failure without category": {"error_category": ""}, "model newline": {"model": "synthetic-model\n"},
            "model case": {"model": "Synthetic"}, "no characters": {"characters_sent": 0},
            "too many characters": {"characters_sent": 60001}, "token hash": {"consent_token_hash": "ABC"},
        }
        for name, overrides in bad_requests.items():
            with self.subTest(request=name):
                self.denied(*self.insert_request(self.a.student_id, **overrides), identity=self.a)
        bad_results = {
            "tool": ("summary", {"tool": "essay"}),
            "tool differs from its request": ("quiz", {}),
            "question on summary": ("summary", {"question": "Why?"}),
            "blank question": ("answer", {"tool": "answer", "question": "   "}),
            "shape version": ("summary", {"shape_version": 0}),
            "too large": ("summary", {"result": json.dumps({"points": ["x" * 70000]})}),
        }
        for name, (request_tool, overrides) in bad_results.items():
            with self.subTest(result=name):
                request = self.spare_request(request_tool)
                self.denied(*self.insert_result(self.a.student_id, self.material_a.pk, request.pk, **overrides),
                            identity=self.a)
        answer = self.spare_request("answer")
        with student_transaction(self.a):
            self.assertEqual(self.sql(*self.insert_result(self.a.student_id, self.material_a.pk, answer.pk,
                                                          tool="answer", question="What is synthetic data?")), 1)
