"""AI records services: limits, day boundary, consent-token races, closing rules and startup checks."""
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Event, Thread, current_thread
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from psycopg import sql
from academics import services
from academics.models import StudyAiRequest, StudyAiResult
from academics.ownership import OwnershipRequired, require_runtime_role
from academics.services import (AiLimitReached, AiRecords, AiRequestClosed, InvalidRecord, RecordNotFound, ai,
                                ai_day_range, materials)
from .base import StudentSecurityCase

FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15}
RESULT = {"points": ["Synthetic point"]}
# A fixed clock (noon in Lagos) so no test depends on the real time of day.
NOON_LAGOS = datetime(2026, 11, 14, 11, 0, tzinfo=dt_timezone.utc)


def token(label):
    return hashlib.sha256(label.encode()).hexdigest()


class StudyAiServiceTests(StudentSecurityCase):
    def setUp(self):
        self.now = NOON_LAGOS
        clock = patch("django.utils.timezone.now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        super().setUp()
        self.material_a = materials.create(self.a, course_id=self.course_a.pk, title="A notes", **FACTS)
        self.material_b = materials.create(self.b, course_id=self.course_b.pk, title="B notes", **FACTS)

    def reserve(self, identity=None, label=None, tool="summary"):
        return ai.reserve(identity or self.a, tool=tool, provider="gemini", model="synthetic-model-1",
                          characters_sent=120, truncated=False, consent_token_hash=token(label or str(uuid.uuid4())))

    def used(self, count, identity=None):
        """`count` finished requests (failed, so none is in flight)."""
        for _ in range(count):
            request, _ = self.reserve(identity)
            ai.fail(identity or self.a, request.pk, "network")

    def migrator(self, statement):
        role = connections["runtime"].settings_dict["USER"]
        with connections["default"].cursor() as cursor:
            cursor.execute(sql.SQL(statement).format(role=sql.Identifier(role)))

    # --- consent token and the ledger -------------------------------------------------

    def test_same_consent_token_returns_the_existing_request_and_counts_once(self):
        first, created = self.reserve(label="once")
        again, created_again = self.reserve(label="once")
        self.assertEqual((created, created_again, again.pk), (True, False, first.pk))
        self.assertEqual(ai.find_request(self.a, token("once")).pk, first.pk)
        self.assertIsNone(ai.find_request(self.b, token("once")))
        self.assertEqual(ai.usage(self.a)["used_today"], 1)

    def test_the_51st_request_of_the_day_is_refused_whatever_the_earlier_outcomes(self):
        self.used(48)
        request, _ = self.reserve()
        ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result=RESULT)
        interrupted, _ = self.reserve()
        self.now += timedelta(minutes=3)
        with self.assertRaises(AiLimitReached) as refused:
            self.reserve()
        self.assertEqual(refused.exception.reason, "daily")
        self.assertEqual(ai.get_request(self.a, interrupted.pk).status, "interrupted")
        self.assertEqual(ai.usage(self.a)["used_today"], 50)
        self.assertEqual(ai.usage(self.b)["used_today"], 0)
        self.reserve(self.b)

    def test_deleting_a_material_keeps_the_count_and_deletes_only_its_results(self):
        other = materials.create(self.a, course_id=self.course_a.pk, title="Other notes", **FACTS)
        for material in (self.material_a, self.material_a, other):
            request, _ = self.reserve()
            ai.succeed(self.a, request.pk, material_id=material.pk, result=RESULT)
        material = materials.retrieve(self.a, self.material_a.pk)
        materials.delete(self.a, material.pk, version=material.record_version)
        self.assertEqual(ai.usage(self.a)["used_today"], 3)
        self.assertEqual(ai.usage(self.a)["results"], 1)
        self.assertEqual(len(ai.results_for(self.a, other.pk)), 1)

    def test_daily_count_resets_at_lagos_midnight_not_utc(self):
        # 23:59 in Lagos (UTC+1) on 14 Nov is 22:59 UTC.
        late = datetime(2026, 11, 14, 22, 59, tzinfo=dt_timezone.utc)
        self.now = late
        self.used(50)
        with self.assertRaises(AiLimitReached):
            self.reserve()
        self.now = late + timedelta(seconds=59)
        with self.assertRaises(AiLimitReached):
            self.reserve()
        self.now = late + timedelta(minutes=1)  # 00:00 Lagos
        self.reserve()
        self.assertEqual(ai.usage(self.a)["used_today"], 1)
        start, end = ai_day_range(late)
        self.assertEqual((start.isoformat(), end - start), ("2026-11-14T00:00:00+01:00", timedelta(days=1)))

    def test_saved_result_cap_is_refused_before_anything_is_sent(self):
        request, _ = self.reserve()
        ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result=RESULT)
        with patch.object(services, "MAX_AI_RESULTS_PER_STUDENT", 1):
            with self.assertRaises(AiLimitReached) as refused:
                self.reserve()
        self.assertEqual(refused.exception.reason, "results")
        self.assertEqual(ai.usage(self.a)["used_today"], 1)

    def test_one_request_in_flight_and_stale_ones_become_interrupted(self):
        first, _ = self.reserve()
        with self.assertRaises(AiLimitReached) as refused:
            self.reserve()
        self.assertEqual(refused.exception.reason, "busy")
        self.now += timedelta(minutes=3)
        second, created = self.reserve()
        self.assertTrue(created)
        self.assertEqual(ai.get_request(self.a, first.pk).status, "interrupted")
        # A late answer for the interrupted request saves nothing and cannot fail it either.
        with self.assertRaises(AiRequestClosed):
            ai.succeed(self.a, first.pk, material_id=self.material_a.pk, result=RESULT)
        with self.assertRaises(AiRequestClosed):
            ai.fail(self.a, first.pk, "timeout")
        self.assertEqual(ai.results_for(self.a, self.material_a.pk), [])
        self.assertEqual(ai.get_request(self.a, first.pk).status, "interrupted")

    # --- closing a request ------------------------------------------------------------

    def test_succeed_saves_the_result_and_closes_the_request_once(self):
        request, _ = self.reserve(tool="answer")
        saved = ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result={"answer": "Synthetic",
                           "not_covered": False}, question="What is synthetic data?", shape_version=1)
        self.assertEqual((saved.tool, saved.question, ai.get_request(self.a, request.pk).status),
                         ("answer", "What is synthetic data?", "succeeded"))
        self.assertEqual(ai.get_result(self.a, saved.pk).result["answer"], "Synthetic")
        with self.assertRaises(AiRequestClosed):
            ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result=RESULT, question="Again?")

    def test_invalid_results_save_nothing_and_leave_the_request_in_progress(self):
        request, _ = self.reserve()
        for name, changes in {
            "other student's material": {"material_id": self.material_b.pk},
            "question on a summary": {"question": "Why?"},
            "too large": {"result": {"points": ["x" * 70000]}},
            "not JSON": {"result": {"points": {1, 2}}},
            "shape version": {"shape_version": 0},
        }.items():
            with self.subTest(name):
                values = {"material_id": self.material_a.pk, "result": RESULT} | changes
                with self.assertRaises((InvalidRecord, RecordNotFound)):
                    ai.succeed(self.a, request.pk, **values)
                self.assertEqual(ai.get_request(self.a, request.pk).status, "sent")
        self.assertEqual(ai.usage(self.a)["results"], 0)
        # The caller then records the failure ("save"); unknown categories are refused.
        with self.assertRaises(InvalidRecord):
            ai.fail(self.a, request.pk, "mystery")
        ai.fail(self.a, request.pk, "save")
        self.assertEqual(ai.get_request(self.a, request.pk).error_category, "save")

    def test_reserve_refuses_values_outside_the_fixed_lists(self):
        for name, changes in {"tool": {"tool": "essay"}, "provider": {"provider": "other"},
                              "model": {"model": "Bad Model"}, "characters": {"characters_sent": 0},
                              "characters type": {"characters_sent": "120"}, "truncated": {"truncated": 1},
                              "token": {"consent_token_hash": "short"}}.items():
            with self.subTest(name):
                values = {"tool": "summary", "provider": "gemini", "model": "synthetic-model-1",
                          "characters_sent": 120, "truncated": False, "consent_token_hash": token(name)} | changes
                with self.assertRaises(InvalidRecord):
                    ai.reserve(self.a, **values)
        self.assertEqual(ai.usage(self.a)["used_today"], 0)

    def test_other_students_rows_are_not_found_and_forged_identities_are_refused(self):
        request, _ = self.reserve()
        saved = ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result=RESULT)
        for call in (lambda: ai.get_request(self.b, request.pk), lambda: ai.get_result(self.b, saved.pk),
                     lambda: ai.delete_result(self.b, saved.pk), lambda: ai.fail(self.b, request.pk, "network")):
            with self.assertRaises(RecordNotFound):
                call()
        self.assertEqual(ai.results_for(self.b, self.material_a.pk), [])
        for identity in (None, self.a.student_id, {"student_id": self.a.student_id}):
            with self.assertRaises(OwnershipRequired):
                ai.usage(identity)
            with self.assertRaises(OwnershipRequired):
                ai.reserve(identity, tool="summary", provider="gemini", model="synthetic-model-1",
                           characters_sent=120, truncated=False, consent_token_hash=token("forged"))

    def test_deleting_a_result_keeps_its_ledger_row(self):
        request, _ = self.reserve()
        saved = ai.succeed(self.a, request.pk, material_id=self.material_a.pk, result=RESULT)
        ai.delete_result(self.a, saved.pk)
        with self.assertRaises(RecordNotFound):
            ai.get_result(self.a, saved.pk)
        self.assertEqual(ai.get_request(self.a, request.pk).status, "succeeded")
        self.assertEqual(ai.usage(self.a)["used_today"], 1)

    # --- two real connections ---------------------------------------------------------

    def wait_for_advisory_locks(self, granted, waiting):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connections["default"].cursor() as cursor:
                cursor.execute("""SELECT count(*) FILTER (WHERE granted), count(*) FILTER (WHERE NOT granted)
                                  FROM pg_locks l JOIN pg_database d ON d.oid = l.database
                                  WHERE l.locktype = 'advisory' AND d.datname = current_database()""")
                if cursor.fetchone() == (granted, waiting):
                    return
            time.sleep(0.05)
        self.fail(f"advisory locks never reached granted={granted}, waiting={waiting}")

    def race(self, labels):
        """Two reservations. The first stops after its checks, holding the lock just before
        its insert, until the second is waiting for that same lock (stale marking takes no
        lock, so the second is blocked before its own checks); then the first commits."""
        original_clean, reached, release, results = StudyAiRequest.full_clean, Event(), Event(), {}

        def held_clean(request, *args, **kwargs):
            if current_thread().name == "first":
                reached.set()
                release.wait(10)
            return original_clean(request, *args, **kwargs)

        def run(name, label):
            try:
                request, created = self.reserve(label=label)
                results[name] = (request.pk, created)
            except AiLimitReached as error:
                results[name] = error.reason
            finally:
                connections.close_all()

        with patch.object(StudyAiRequest, "full_clean", held_clean):
            first = Thread(target=run, args=("first", labels[0]), name="first", daemon=True)
            first.start()
            self.assertTrue(reached.wait(10))
            self.wait_for_advisory_locks(granted=1, waiting=0)
            second = Thread(target=run, args=("second", labels[1]), name="second", daemon=True)
            second.start()
            self.wait_for_advisory_locks(granted=1, waiting=1)
            release.set()
            first.join(15)
            second.join(15)
        return results

    def test_two_simultaneous_sends_with_one_token_create_one_request(self):
        results = self.race(["same", "same"])
        self.assertTrue(results["first"][1])
        self.assertEqual(results["second"], (results["first"][0], False))
        self.assertEqual(ai.usage(self.a)["used_today"], 1)

    def test_two_simultaneous_requests_at_49_cannot_both_pass(self):
        self.used(49)
        results = self.race(["one", "two"])
        self.assertTrue(results["first"][1])
        self.assertIn(results["second"], ("busy", "daily"))
        self.assertEqual(ai.usage(self.a)["used_today"], 50)

    def test_a_unique_token_violation_returns_the_existing_request(self):
        first, _ = self.reserve(label="fallback")
        ai.fail(self.a, first.pk, "network")
        # Make the in-lock lookup miss once, so the insert hits the unique token constraint.
        with patch.object(AiRecords, "_existing", return_value=None):
            again, created = self.reserve(label="fallback")
        self.assertEqual((again.pk, created), (first.pk, False))
        self.assertEqual(ai.usage(self.a)["used_today"], 1)

    def test_reserve_refuses_to_run_inside_another_transaction(self):
        from academics.ownership import student_transaction
        with self.assertRaises(RuntimeError), student_transaction(self.a):
            self.reserve()
        self.assertEqual(ai.usage(self.a)["used_today"], 0)

    # --- startup checks ---------------------------------------------------------------

    def test_startup_check_rejects_missing_rls_or_stray_grants_on_ai_tables(self):
        for table in ("academics_studyairequest", "academics_studyairesult"):
            self.migrator(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            try:
                with self.assertRaises(ImproperlyConfigured):
                    require_runtime_role(connections["runtime"])
            finally:
                self.migrator(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for grant, revoke in (
            ("GRANT UPDATE (result) ON academics_studyairesult TO {role}",
             "REVOKE UPDATE (result) ON academics_studyairesult FROM {role}"),
            ("GRANT DELETE ON academics_studyairequest TO {role}",
             "REVOKE DELETE ON academics_studyairequest FROM {role}"),
            ("GRANT UPDATE (tool) ON academics_studyairequest TO {role}",
             "REVOKE UPDATE (tool) ON academics_studyairequest FROM {role}"),
            ("GRANT UPDATE (created_at) ON academics_studyairequest TO {role}",
             "REVOKE UPDATE (created_at) ON academics_studyairequest FROM {role}"),
            ("GRANT TRUNCATE ON academics_studyairequest TO {role}",
             "REVOKE TRUNCATE ON academics_studyairequest FROM {role}"),
            ("GRANT TRUNCATE ON academics_studyairesult TO {role}",
             "REVOKE TRUNCATE ON academics_studyairesult FROM {role}"),
            ("GRANT REFERENCES ON academics_studyairesult TO {role}",
             "REVOKE REFERENCES ON academics_studyairesult FROM {role}"),
        ):
            with self.subTest(grant=grant):
                self.migrator(grant)
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        require_runtime_role(connections["runtime"])
                finally:
                    self.migrator(revoke)
        require_runtime_role(connections["runtime"])

    def test_models_keep_no_file_text_question_or_response_in_the_ledger(self):
        columns = {field.name for field in StudyAiRequest._meta.get_fields() if field.concrete}
        self.assertEqual(columns, {"id", "created_at", "updated_at", "owner", "tool", "provider", "model", "status",
                                   "characters_sent", "truncated", "consent_token_hash", "error_category"})
        self.assertFalse(any(field.name == "material" for field in StudyAiRequest._meta.get_fields()))
        self.assertEqual(StudyAiResult._meta.get_field("material").remote_field.on_delete.__name__, "CASCADE")
