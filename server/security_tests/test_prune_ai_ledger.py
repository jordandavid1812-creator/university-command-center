"""prune_ai_ledger really deletes old rows without results, keeps the rest, and restores forced RLS."""
import hashlib
import io
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from django.core.management import CommandError, call_command
from django.db import connections
from academics.services import ai, materials
from .base import StudentSecurityCase

FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15}
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=dt_timezone.utc)


class PruneLedgerTests(StudentSecurityCase):
    def request_at(self, when, label, identity=None, with_result=False):
        with patch("django.utils.timezone.now", return_value=when):
            request, _ = ai.reserve(identity or self.a, tool="summary", provider="gemini", model="synthetic-model-1",
                                    characters_sent=10, truncated=False,
                                    consent_token_hash=hashlib.sha256(label.encode()).hexdigest())
            if with_result:
                ai.succeed(identity or self.a, request.pk, material_id=self.material.pk, result={"points": ["x"]})
            else:
                ai.fail(identity or self.a, request.pk, "network")
        return request.pk

    def forced(self):
        with connections["default"].cursor() as cursor:
            cursor.execute("""SELECT relname, relforcerowsecurity FROM pg_class
                              WHERE relname IN ('academics_studyairequest', 'academics_studyairesult') ORDER BY relname""")
            return cursor.fetchall()

    def exists(self, identity, pk):
        try:
            ai.get_request(identity, pk)
            return True
        except Exception:
            return False

    def setUp(self):
        super().setUp()
        self.material = materials.create(self.a, course_id=self.course_a.pk, title="A notes", **FACTS)
        self.old = self.request_at(NOW - timedelta(days=400), "old")
        self.old_b = self.request_at(NOW - timedelta(days=400), "old-b", identity=self.b)
        self.old_with_result = self.request_at(NOW - timedelta(days=400), "old-result", with_result=True)
        self.recent = self.request_at(NOW - timedelta(days=30), "recent")

    def test_old_rows_without_results_are_actually_removed_and_rls_is_restored(self):
        output = io.StringIO()
        call_command("prune_ai_ledger", stdout=output)
        self.assertEqual(output.getvalue().strip(), "Removed 2 AI ledger rows older than 365 days.")
        self.assertFalse(self.exists(self.a, self.old))
        self.assertFalse(self.exists(self.b, self.old_b))
        self.assertTrue(self.exists(self.a, self.old_with_result))
        self.assertTrue(self.exists(self.a, self.recent))
        self.assertEqual(self.forced(), [("academics_studyairequest", True), ("academics_studyairesult", True)])
        call_command("prune_ai_ledger", stdout=output)  # idempotent
        self.assertTrue(self.exists(self.a, self.recent))

    def test_the_runtime_role_is_refused_and_nothing_changes(self):
        with self.assertRaises(CommandError):
            call_command("prune_ai_ledger", database="runtime", stdout=io.StringIO())
        self.assertTrue(self.exists(self.a, self.old))
        self.assertEqual(self.forced(), [("academics_studyairequest", True), ("academics_studyairesult", True)])
