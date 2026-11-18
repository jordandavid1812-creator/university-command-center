"""Study plans and topics: owner-only through forced RLS, same-owner links (plan to course, topic to
plan), column-limited updates, removed with their course, and refused by the startup check if
weakened."""
import uuid
from datetime import date
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DatabaseError, transaction
from psycopg import sql
from academics.ownership import require_runtime_role, student_transaction
from academics.services import RecordConflict, RecordNotFound, assignments, courses, study_plans, study_topics
from .base import StudentSecurityCase

EXAM = date(2026, 12, 20)


class StudyPlanSecurityTests(StudentSecurityCase):
    def setUp(self):
        super().setUp()
        self.plan_a = study_plans.create_with_topics(self.a, course_id=self.course_a.pk, exam_date=EXAM, review_days=1,
                                                     topics=[("OSI model", date(2026, 12, 1)), ("TCP", date(2026, 12, 2))])
        self.plan_b = study_plans.create_with_topics(self.b, course_id=self.course_b.pk, exam_date=EXAM, review_days=0,
                                                     topics=[("B topic", date(2026, 12, 1))])

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

    def test_rls_is_forced_on_both_tables_and_each_student_sees_only_their_own(self):
        for table in ("academics_studyplan", "academics_studytopic"):
            rows = self.sql(f"""SELECT c.relrowsecurity, c.relforcerowsecurity, p.polcmd FROM pg_class c
                                JOIN pg_policy p ON p.polrelid=c.oid WHERE c.relname='{table}'""")
            self.assertEqual(rows, [(True, True, "*")], table)
            self.assertEqual(self.sql(f"SELECT id FROM {table}"), [])
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT title FROM academics_studytopic ORDER BY position"), [("OSI model",), ("TCP",)])
            self.assertEqual(self.sql("UPDATE academics_studytopic SET done=true WHERE plan_id=%s", [self.plan_b.pk]), 0)
            self.assertEqual(self.sql("DELETE FROM academics_studyplan WHERE id=%s", [self.plan_b.pk]), 0)
        with self.assertRaises(RecordNotFound):
            study_topics.create(self.a, plan_id=self.plan_b.pk, title="Sneaky", position=9, planned_date=EXAM)

    def test_links_and_columns_are_enforced_in_the_database(self):
        with student_transaction(self.a):
            self.denied("""INSERT INTO academics_studytopic (id, owner_id, plan_id, title, position, planned_date, done,
                           record_version, created_at, updated_at) VALUES (%s, %s, %s, 'x', 0, %s, false, 1, now(), now())""",
                        [uuid.uuid4(), self.a.student_id, self.plan_b.pk, EXAM])
            self.denied("""INSERT INTO academics_studyplan (id, owner_id, course_id, exam_date, review_days, record_version,
                           created_at, updated_at) VALUES (%s, %s, %s, %s, 1, 1, now(), now())""",
                        [uuid.uuid4(), self.a.student_id, self.course_b.pk, EXAM])
            for statement in ("UPDATE academics_studytopic SET plan_id=%s", "UPDATE academics_studyplan SET course_id=%s",
                              "UPDATE academics_studyplan SET owner_id=%s"):
                self.denied(statement, [uuid.uuid4()])
            self.denied("UPDATE academics_studyplan SET review_days=4")
            self.denied("UPDATE academics_studytopic SET title=' padded'")

    def test_replan_moves_only_unfinished_topics_and_checks_the_version(self):
        osi, tcp = study_topics.list(self.a)
        study_topics.update(self.a, osi.pk, version=osi.record_version, done=True)
        study_plans.replan(self.a, self.plan_a.pk, version=1, dates={osi.pk: date(2026, 12, 9), tcp.pk: date(2026, 12, 9)})
        osi, tcp = sorted(study_topics.list(self.a), key=lambda t: t.position)
        self.assertEqual((osi.planned_date, tcp.planned_date), (date(2026, 12, 1), date(2026, 12, 9)))
        with self.assertRaises(RecordConflict):
            study_plans.replan(self.a, self.plan_a.pk, version=1, dates={})
        with self.assertRaises(RecordNotFound):
            study_plans.replan(self.a, self.plan_b.pk, version=1, dates={})

    def test_deleting_a_course_removes_its_plans_and_topics(self):
        assignments.delete(self.a, self.task_a.pk, version=1)
        course = courses.retrieve(self.a, self.course_a.pk)
        courses.delete(self.a, course.pk, version=course.record_version)
        with student_transaction(self.a):
            self.assertEqual(self.sql("SELECT count(*) FROM academics_studyplan"), [(0,)])
            self.assertEqual(self.sql("SELECT count(*) FROM academics_studytopic"), [(0,)])

    def test_startup_check_rejects_weakened_planner_tables(self):
        for table in ("academics_studyplan", "academics_studytopic"):
            for weaken, restore in ((f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY", f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"),
                                    (f"GRANT TRUNCATE ON {table} TO {{role}}", f"REVOKE TRUNCATE ON {table} FROM {{role}}")):
                with self.subTest(table=table, weaken=weaken):
                    self.migrator(weaken)
                    try:
                        with self.assertRaises(ImproperlyConfigured):
                            require_runtime_role(connections["runtime"])
                    finally:
                        self.migrator(restore)
        require_runtime_role(connections["runtime"])
