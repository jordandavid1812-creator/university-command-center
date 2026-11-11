"""Synthetic records only. Run with manage.py test, never SQLite."""
import os
from pathlib import Path
import subprocess
import sys
from datetime import date
from decimal import Decimal
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, SimpleTestCase
from django.urls import resolve, Resolver404
from accounts.models import Student
from academics.models import Assignment, Course, Semester


class SetupTests(SimpleTestCase):
    def run_check(self, changes):
        env = os.environ.copy()
        env.pop("DJANGO_SETTINGS_MODULE", None)
        for name, value in changes.items():
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[2] / "manage.py"), "check"],
            env=env, capture_output=True, text=True,
        )

    def test_missing_secret_fails_closed(self):
        result = self.run_check({"DJANGO_SECRET_KEY": None})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set DJANGO_SECRET_KEY", result.stderr)

    def test_future_production_settings_are_disabled(self):
        result = self.run_check({"DJANGO_SETTINGS_MODULE": "config.settings.production"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production deployment is not approved", result.stderr)

    def test_test_database_cannot_equal_development_database(self):
        result = self.run_check({"DJANGO_SETTINGS_MODULE": "config.settings.test",
                                 "PGTESTDATABASE": os.environ["PGDATABASE"]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PGTESTDATABASE must differ", result.stderr)

    def test_postgresql_is_required(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertFalse(settings.DEBUG)
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.Student")

    def test_no_application_or_account_routes(self):
        for path in ("/", "/admin/", "/login/", "/register/"):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)


class RecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = Student.objects.create_user("synthetic-one")
        cls.other = Student.objects.create_user("synthetic-two")
        cls.semester = Semester.objects.create(owner=cls.owner, label="First", display_order=2)
        cls.other_semester = Semester.objects.create(owner=cls.other, label="Second", display_order=0)

    def course(self, **changes):
        values = dict(owner=self.owner, semester=self.semester, original_code="CSC101",
                      name="Synthetic Computing", credit_units=Decimal("3"))
        values.update(changes)
        return Course(**values)

    def assignment(self, course, **changes):
        values = dict(owner=self.owner, course=course, title="Synthetic task", due_date=date(2026, 11, 11))
        values.update(changes)
        return Assignment(**values)

    def rejected_by_database(self, operation):
        with self.assertRaises(IntegrityError), transaction.atomic():
            operation()

    def test_uuid_identity_and_timestamps(self):
        course = self.course()
        course.save()
        task = self.assignment(course)
        task.save()
        for record in (self.owner, self.semester, course, task):
            self.assertIsInstance(record.pk, uuid.UUID)
            self.assertIsNotNone(record.created_at)
            self.assertIsNotNone(record.updated_at)
        self.assertFalse(self.owner.has_usable_password())
        self.assertFalse(task.completed)
        self.assertEqual((task.record_version, course.record_version), (1, 1))

    def test_updates_preserve_identity_and_creation_time(self):
        course = self.course()
        course.save()
        previous = (course.pk, course.created_at, course.updated_at)
        course.name = "Updated synthetic name"
        course.save()
        self.assertEqual((course.pk, course.created_at), previous[:2])
        self.assertGreaterEqual(course.updated_at, previous[2])

    def test_original_and_normalized_codes(self):
        course = self.course(original_code=" cSc101 ")
        course.save()
        course.refresh_from_db()
        self.assertEqual(course.original_code, " cSc101 ")
        self.assertEqual(course.normalized_code, "CSC101")

    def test_duplicate_normalized_code_same_owner_rejected(self):
        self.course().save()
        with self.assertRaises(ValidationError):
            self.course(original_code=" csc101 ").save()
        self.rejected_by_database(lambda: Course.objects.bulk_create([
            self.course(normalized_code="CSC101")]))

    def test_same_code_different_owners_allowed(self):
        self.course().save()
        self.course(owner=self.other, semester=self.other_semester).save()
        self.assertEqual(Course.objects.count(), 2)

    def test_all_actual_grades_and_ungraded(self):
        for index, grade in enumerate([None, "A", "B", "C", "D", "E", "F"]):
            record = self.course(original_code=f"CSC{index}", actual_grade=grade)
            record.save()
            record.refresh_from_db()
            self.assertEqual(record.actual_grade, grade)

    def test_shared_grade_normalization(self):
        record = self.course(actual_grade=" f ")
        record.save()
        self.assertEqual(record.actual_grade, "F")
        record.actual_grade = ""
        record.save()
        self.assertIsNone(record.actual_grade)

    def test_invalid_model_grades(self):
        for grade in ("G", "AA", 1, True):
            with self.subTest(grade=grade), self.assertRaises(ValidationError):
                self.course(actual_grade=grade).save()

    def test_invalid_database_grades(self):
        record = self.course()
        record.save()
        for grade in ("G", "", "a"):
            with self.subTest(grade=grade):
                self.rejected_by_database(lambda: Course.objects.filter(pk=record.pk).update(actual_grade=grade))

    def test_credit_boundaries(self):
        for index, value in enumerate(("0.0001", "3.1250", "1000000")):
            record = self.course(original_code=f"BOUND{index}", credit_units=Decimal(value))
            record.save()
            record.refresh_from_db()
            self.assertEqual(record.credit_units, Decimal(value))

    def test_invalid_model_credits(self):
        for value in ("0", "-1", "1000000.0001", "0.00001", "3.00001", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.course(credit_units=Decimal(value)).save()

    def test_invalid_database_credits_without_rounding(self):
        record = self.course()
        record.save()
        for value in ("0", "-1", "1000000.0001", "0.00001", "3.00001", "NaN", "Infinity"):
            with self.subTest(value=value):
                self.rejected_by_database(lambda: connection.cursor().execute(
                    "UPDATE academics_course SET credit_units = %s::numeric WHERE id = %s", [value, record.pk]))
        record.refresh_from_db()
        self.assertEqual(record.credit_units, Decimal(3))

    def test_cross_owner_course_model_validation(self):
        with self.assertRaises(ValidationError):
            self.course(semester=self.other_semester).save()

    def test_cross_owner_assignment_model_validation(self):
        course = self.course(owner=self.other, semester=self.other_semester)
        course.save()
        with self.assertRaises(ValidationError):
            self.assignment(course).save()

    def test_database_rejects_cross_owner_course_insert(self):
        self.rejected_by_database(lambda: Course.objects.bulk_create([
            self.course(semester=self.other_semester, normalized_code="CSC101")]))

    def test_database_rejects_cross_owner_assignment_insert(self):
        course = self.course()
        course.save()
        self.rejected_by_database(lambda: Assignment.objects.bulk_create([
            self.assignment(course, owner=self.other)]))

    def test_database_rejects_cross_owner_reparenting(self):
        course = self.course()
        course.save()
        self.assignment(course).save()
        self.rejected_by_database(lambda: Course.objects.filter(pk=course.pk).update(semester=self.other_semester))
        self.rejected_by_database(lambda: Course.objects.filter(pk=course.pk).update(owner=self.other, semester=self.other_semester))
        self.rejected_by_database(lambda: Semester.objects.filter(pk=self.semester.pk).update(owner=self.other))
        self.rejected_by_database(lambda: Assignment.objects.update(owner=self.other))

    def test_normalization_cannot_be_bypassed(self):
        record = self.course()
        record.save()
        self.rejected_by_database(lambda: Course.objects.filter(pk=record.pk).update(normalized_code="csc101"))
        self.rejected_by_database(lambda: Course.objects.filter(pk=record.pk).update(original_code="OTHER"))
        self.rejected_by_database(lambda: Course.objects.filter(pk=record.pk).update(original_code="é", normalized_code="É"))

    def test_record_version_must_be_positive(self):
        record = self.course()
        record.save()
        task = self.assignment(record)
        task.save()
        for model in (Course, Assignment):
            self.rejected_by_database(lambda: model.objects.update(record_version=0))

    def test_nonempty_required_text(self):
        for values in ({"name": " "}, {"original_code": " "}):
            with self.assertRaises(ValidationError):
                self.course(**values).save()
        course = self.course()
        course.save()
        with self.assertRaises(ValidationError):
            self.assignment(course, title=" ").save()
        self.rejected_by_database(lambda: Course.objects.update(name=" "))
        self.rejected_by_database(lambda: Semester.objects.update(label=" "))

    def test_assignment_fields_are_validated(self):
        course = self.course()
        course.save()
        for values in ({"due_date": "invalid"}, {"completed": "invalid"}):
            with self.assertRaises(ValidationError):
                self.assignment(course, **values).save()

    def test_explicit_semester_order(self):
        earlier = Semester.objects.create(owner=self.owner, label="Z", display_order=0)
        self.assertEqual(list(self.owner.semesters.all()), [earlier, self.semester])
        self.rejected_by_database(lambda: Semester.objects.update(display_order=-1))

    def test_deletion_is_protected_until_dependents_removed(self):
        course = self.course()
        course.save()
        task = self.assignment(course)
        task.save()
        for record in (self.owner, self.semester, course):
            with self.assertRaises(ProtectedError):
                record.delete()
        self.rejected_by_database(lambda: connection.cursor().execute(
            "DELETE FROM academics_course WHERE id = %s", [course.pk]))
        task.delete()
        course.delete()
        self.semester.delete()
        self.owner.delete()

    def test_missing_foreign_keys_are_rejected(self):
        self.rejected_by_database(lambda: Course.objects.bulk_create([
            self.course(semester_id=uuid.uuid4(), normalized_code="CSC101")]))
        self.rejected_by_database(lambda: Assignment.objects.bulk_create([
            Assignment(owner=self.owner, course_id=uuid.uuid4(), title="Synthetic",
                       due_date=date(2026, 11, 11))]))

    def test_database_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")
