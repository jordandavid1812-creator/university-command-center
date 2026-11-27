"""Launch step E: AI limits for the shared key. 10 requests per student and 200 for the whole site
per Lagos day on the public site (settings); the site-wide count lives in academics_aisiteusage,
reachable only from a signed student transaction. Synthetic data, real PostgreSQL."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Thread
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections, transaction
from django.test import override_settings
from psycopg import sql
from academics.models import AiSiteUsage
from django.db.models.query import QuerySet
from academics.ownership import database_alias, require_runtime_role, student_transaction
from academics.services import AiLimitReached, ai, ai_daily_limit, ai_site_limit, materials
from .base import StudentSecurityCase

FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15}
NOON_LAGOS = datetime(2026, 11, 14, 11, 0, tzinfo=dt_timezone.utc)
DAY = NOON_LAGOS.date()


def token(label):
    return hashlib.sha256(label.encode()).hexdigest()


class AiSiteLimitTests(StudentSecurityCase):
    def setUp(self):
        self.now = NOON_LAGOS
        clock = patch("django.utils.timezone.now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        super().setUp()
        self.material_a = materials.create(self.a, course_id=self.course_a.pk, title="A notes", **FACTS)

    def reserve(self, identity=None, label=None):
        return ai.reserve(identity or self.a, tool="summary", provider="gemini", model="synthetic-model-1",
                          characters_sent=120, truncated=False, consent_token_hash=token(label or str(uuid.uuid4())))

    def used(self, count, identity=None):
        for _ in range(count):
            request, _ = self.reserve(identity)
            ai.fail(identity or self.a, request.pk, "network")

    def refused(self, identity=None):
        with self.assertRaises(AiLimitReached) as refusal:
            self.reserve(identity)
        return refusal.exception.reason

    def site_count(self, day=DAY):
        """Read through the website login inside a signed student transaction: row-level security
        is forced, so even the table owner (the migration login) sees no rows without one."""
        with student_transaction(self.a):
            row = AiSiteUsage.objects.using(database_alias()).filter(day=day).first()
        return row.requests if row else 0

    def migrator(self, statement):
        role = connections["runtime"].settings_dict["USER"]
        with connections["default"].cursor() as cursor:
            cursor.execute(sql.SQL(statement).format(role=sql.Identifier(role)))

    def test_local_and_test_profiles_keep_50_and_no_site_limit(self):
        self.assertEqual((ai_daily_limit(), ai_site_limit()), (50, None))
        self.used(2)
        self.assertEqual(self.site_count(), 0)  # nothing counted without a site limit

    @override_settings(UCC_AI_REQUESTS_PER_DAY=10)
    def test_the_11th_request_of_a_student_is_refused(self):
        self.used(10)
        self.assertEqual(self.refused(), "daily")
        self.assertEqual(ai.usage(self.a)["daily_limit"], 10)
        self.used(1, self.b)  # other students are not affected

    @override_settings(UCC_AI_REQUESTS_PER_DAY=10, UCC_AI_SITE_REQUESTS_PER_DAY=3)
    def test_the_site_limit_counts_every_student_together(self):
        self.used(2)
        self.used(1, self.b)
        self.assertEqual(self.site_count(), 3)
        self.assertEqual(self.refused(self.b), "site")
        self.assertEqual(self.refused(), "site")
        self.assertEqual(self.site_count(), 3)
        self.assertEqual(ai.usage(self.b)["used_today"], 1)  # the refusal saved no request

    @override_settings(UCC_AI_REQUESTS_PER_DAY=1, UCC_AI_SITE_REQUESTS_PER_DAY=5)
    def test_refusals_and_repeated_sends_do_not_use_the_site_allowance(self):
        first, _ = self.reserve(label="once")
        again, created = self.reserve(label="once")  # a double click: same request, counted once
        self.assertEqual((again.pk, created), (first.pk, False))
        ai.fail(self.a, first.pk, "network")
        self.assertEqual(self.refused(), "daily")
        self.assertEqual(self.site_count(), 1)

    @override_settings(UCC_AI_SITE_REQUESTS_PER_DAY=2)
    def test_a_failed_insert_rolls_the_site_count_back(self):
        with patch.object(QuerySet, "bulk_create", side_effect=DatabaseError("synthetic")):
            with self.assertRaises(DatabaseError):
                self.reserve()
        self.assertEqual(self.site_count(), 0)

    @override_settings(UCC_AI_SITE_REQUESTS_PER_DAY=2)
    def test_the_site_count_starts_again_at_lagos_midnight(self):
        self.used(2)
        self.assertEqual(self.refused(self.b), "site")
        self.now = datetime(2026, 11, 14, 23, 0, tzinfo=dt_timezone.utc)  # 00:00 on the 15th in Lagos
        self.used(1, self.b)
        self.assertEqual((self.site_count(), self.site_count(DAY + timedelta(days=1))), (2, 1))

    @override_settings(UCC_AI_SITE_REQUESTS_PER_DAY=1)
    def test_two_students_at_the_last_request_cannot_both_pass(self):
        outcomes = {}

        def run(name, identity):
            try:
                self.reserve(identity)
                outcomes[name] = "sent"
            except AiLimitReached as error:
                outcomes[name] = error.reason
            finally:
                connections.close_all()

        threads = [Thread(target=run, args=(name, who), daemon=True) for name, who in (("a", self.a), ("b", self.b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        self.assertEqual(sorted(outcomes.values()), ["sent", "site"])
        self.assertEqual(self.site_count(), 1)

    def test_the_counter_is_invisible_and_unchangeable_without_a_signed_context(self):
        with student_transaction(self.a):
            AiSiteUsage.objects.using(database_alias()).create(day=DAY, requests=7)
        runtime = connections["runtime"]
        with runtime.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM academics_aisiteusage")
            self.assertEqual(cursor.fetchone()[0], 0)  # row-level security: no student context
        with connections["default"].cursor() as cursor:  # the table owner cannot see it either
            cursor.execute("SELECT count(*) FROM academics_aisiteusage")
            self.assertEqual(cursor.fetchone()[0], 0)
        for statement in ("INSERT INTO academics_aisiteusage (day, requests) VALUES ('2026-01-01', 0)",
                          "UPDATE academics_aisiteusage SET requests = 0",
                          "DELETE FROM academics_aisiteusage"):
            with self.subTest(statement=statement):
                try:
                    with transaction.atomic(using="runtime"), runtime.cursor() as cursor:
                        cursor.execute(statement)
                        changed = cursor.rowcount
                except DatabaseError:
                    changed = 0
                self.assertEqual(changed, 0)
        self.assertEqual(self.site_count(), 7)

    def test_startup_check_rejects_missing_rls_or_stray_grants_on_the_counter(self):
        self.migrator("ALTER TABLE academics_aisiteusage NO FORCE ROW LEVEL SECURITY")
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections["runtime"])
        finally:
            self.migrator("ALTER TABLE academics_aisiteusage FORCE ROW LEVEL SECURITY")
        for grant, revoke in (
            ("GRANT DELETE ON academics_aisiteusage TO {role}", "REVOKE DELETE ON academics_aisiteusage FROM {role}"),
            ("GRANT TRUNCATE ON academics_aisiteusage TO {role}", "REVOKE TRUNCATE ON academics_aisiteusage FROM {role}"),
            ("GRANT UPDATE (day) ON academics_aisiteusage TO {role}",
             "REVOKE UPDATE (day) ON academics_aisiteusage FROM {role}"),
        ):
            with self.subTest(grant=grant):
                self.migrator(grant)
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        require_runtime_role(connections["runtime"])
                finally:
                    self.migrator(revoke)
        require_runtime_role(connections["runtime"])
