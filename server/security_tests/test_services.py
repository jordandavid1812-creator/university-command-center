from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier
import time
import uuid
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from accounts.models import Student
from academics.ownership import (OwnershipRequired, TrustedStudent, identity_for_verified_student,
                                 student_transaction)
from academics.services import assignments, courses, semesters, InvalidRecord, RecordConflict, RecordNotFound
from .base import StudentSecurityCase


class ServiceSecurityTests(StudentSecurityCase):
    def records(self):
        return ((semesters, self.sem_a, self.sem_b, {"label": "Changed"}),
                (courses, self.course_a, self.course_b, {"actual_grade": "F"}),
                (assignments, self.task_a, self.task_b, {"title": "Changed"}))

    def test_lists_and_retrieves_only_own_records(self):
        for service, own, other, _ in self.records():
            with self.subTest(model=service.model.__name__):
                self.assertEqual([row.pk for row in service.list(self.a)], [own.pk])
                self.assertEqual(service.retrieve(self.a, own.pk).owner_id, self.a.student_id)
                self.assertEqual([row.pk for row in service.list(self.b)], [other.pk])

    def test_known_forged_and_nonexistent_ids_have_identical_errors(self):
        for service, own, other, changes in self.records():
            for identifier in (other.pk, uuid.uuid4(), "not-a-uuid", None):
                operations = (
                    lambda: service.retrieve(self.a, identifier),
                    lambda: service.update(self.a, identifier, version=1, **changes),
                    lambda: service.delete(self.a, identifier, version=1),
                )
                for operation in operations:
                    with self.assertRaisesMessage(RecordNotFound, "Record not found."):
                        operation()
            self.assertEqual(service.retrieve(self.b, other.pk).record_version, 1)

    def test_every_operation_requires_trusted_identity(self):
        invalid = (None, self.student_a, self.a.student_id, str(self.a.student_id), {},
                   TrustedStudent(self.b.student_id, self.a.expires_at, self.a.proof),
                   replace(self.a, proof="é" * 64), replace(self.a, expires_at=int(time.time()) - 1))
        for service, own, _, changes in self.records():
            for identity in invalid:
                for operation in (
                    lambda: service.list(identity), lambda: service.retrieve(identity, own.pk),
                    lambda: service.create(identity, **changes),
                    lambda: service.update(identity, own.pk, version=1, **changes),
                    lambda: service.delete(identity, own.pk, version=1),
                ):
                    with self.assertRaises(OwnershipRequired):
                        operation()

    def test_identity_factory_rejects_unsaved_inactive_and_non_principals(self):
        for principal in (None, self.student_a.pk, Student(id=self.student_a.pk),
                          {"id": self.student_a.pk}):
            with self.assertRaises(OwnershipRequired):
                identity_for_verified_student(principal)
        self.student_a.is_active = False
        with self.assertRaises(OwnershipRequired):
            identity_for_verified_student(self.student_a)

    def test_deactivation_revokes_previously_issued_context(self):
        Student.objects.filter(pk=self.student_a.pk).update(is_active=False)
        with self.assertRaises(OwnershipRequired):
            semesters.list(self.a)

    def test_owner_ids_and_server_fields_are_never_accepted(self):
        for service, own, _, changes in self.records():
            for field in ("owner", "owner_id", "id", "record_version", "created_at", "updated_at"):
                with self.assertRaises(InvalidRecord):
                    service.create(self.a, **{**changes, field: self.b.student_id})
                with self.assertRaises(InvalidRecord):
                    service.update(self.a, own.pk, version=1, **{field: self.b.student_id})
            self.assertEqual(service.retrieve(self.a, own.pk).owner_id, self.a.student_id)

    def test_cross_owner_and_missing_parent_have_same_error(self):
        for identifier in (self.sem_b.pk, uuid.uuid4()):
            with self.assertRaises(RecordNotFound):
                courses.update(self.a, self.course_a.pk, version=1, semester_id=identifier)
            with self.assertRaises(RecordNotFound):
                courses.create(self.a, semester_id=identifier, original_code="OTHER", name="Synthetic", credit_units=1)
        for identifier in (self.course_b.pk, uuid.uuid4()):
            with self.assertRaises(RecordNotFound):
                assignments.update(self.a, self.task_a.pk, version=1, course_id=identifier)

    def test_own_crud_preserves_created_timestamp_and_increments_versions(self):
        for service, own, _, changes in self.records():
            changed = service.update(self.a, own.pk, version=1, **changes)
            self.assertEqual(changed.record_version, 2)
            self.assertEqual(changed.created_at, own.created_at)
            self.assertGreater(changed.updated_at, own.updated_at)
        assignments.delete(self.a, self.task_a.pk, version=2)
        courses.delete(self.a, self.course_a.pk, version=2)
        semesters.delete(self.a, self.sem_a.pk, version=2)
        for service, own, other, _ in self.records():
            with self.assertRaises(RecordNotFound):
                service.retrieve(self.a, own.pk)
            self.assertEqual(service.retrieve(self.b, other.pk).record_version, 1)

    def test_code_and_grade_normalization_are_preserved(self):
        row = courses.update(self.a, self.course_a.pk, version=1, original_code=" csc102 ", actual_grade=" f ")
        self.assertEqual((row.original_code, row.normalized_code, row.actual_grade), (" csc102 ", "CSC102", "F"))
        row = courses.update(self.a, row.pk, version=2, actual_grade="")
        self.assertIsNone(row.actual_grade)

    def test_invalid_inputs_do_not_change_version_or_timestamp(self):
        for values in ({"credit_units": Decimal("0.00001")}, {"actual_grade": "G"}, {"name": " "}):
            with self.assertRaises(InvalidRecord):
                courses.update(self.a, self.course_a.pk, version=1, **values)
        row = courses.retrieve(self.a, self.course_a.pk)
        self.assertEqual((row.record_version, row.updated_at), (1, self.course_a.updated_at))

    def test_duplicate_codes_remain_per_owner_and_errors_are_sanitized(self):
        with self.assertRaisesMessage(InvalidRecord, "Invalid record."):
            courses.create(self.a, semester_id=self.sem_a.pk, original_code=" csc101 ", name="Duplicate", credit_units=3)
        self.assertEqual(len(courses.list(self.a)), 1)
        self.assertEqual(len(courses.list(self.b)), 1)

    def test_dependent_records_protect_deletion(self):
        for service, record in ((semesters, self.sem_a), (courses, self.course_a)):
            with self.assertRaises(InvalidRecord):
                service.delete(self.a, record.pk, version=1)

    def test_stale_updates_and_deletes_are_rejected(self):
        for service, own, _, changes in self.records():
            service.update(self.a, own.pk, version=1, **changes)
            with self.assertRaises(RecordConflict):
                service.update(self.a, own.pk, version=1, **changes)
            with self.assertRaises(RecordConflict):
                service.delete(self.a, own.pk, version=1)
            self.assertEqual(service.retrieve(self.a, own.pk).record_version, 2)

    def test_version_is_mandatory_and_must_be_a_positive_integer(self):
        for value in (None, 0, -1, True, "1", 2**63 - 1):
            with self.assertRaises(InvalidRecord):
                courses.update(self.a, self.course_a.pk, version=value, name="Changed")
        with self.assertRaises(TypeError):
            courses.update(self.a, self.course_a.pk, name="Changed")

    def test_multi_record_unit_rolls_back_everything(self):
        with self.assertRaises(RuntimeError):
            with student_transaction(self.a):
                courses.update(self.a, self.course_a.pk, version=1, actual_grade="B")
                assignments.update(self.a, self.task_a.pk, version=1, completed=True)
                semesters.create(self.a, label="Must roll back")
                raise RuntimeError("Synthetic failure")
        course = courses.retrieve(self.a, self.course_a.pk)
        self.assertEqual((course.actual_grade, course.record_version, course.updated_at),
                         (None, 1, self.course_a.updated_at))
        self.assertFalse(assignments.retrieve(self.a, self.task_a.pk).completed)
        self.assertEqual(len(semesters.list(self.a)), 1)

    def test_nested_context_cannot_switch_students(self):
        with student_transaction(self.a):
            with self.assertRaises(OwnershipRequired):
                semesters.list(self.b)
            self.assertEqual([s.pk for s in semesters.list(self.a)], [self.sem_a.pk])

    def test_nested_failure_rolls_back_savepoint_and_outer_unit_can_continue(self):
        with student_transaction(self.a):
            with self.assertRaises(InvalidRecord):
                courses.create(self.a, semester_id=self.sem_a.pk, original_code="CSC101", name="Duplicate", credit_units=3)
            assignments.update(self.a, self.task_a.pk, version=1, completed=True)
        self.assertTrue(assignments.retrieve(self.a, self.task_a.pk).completed)

    def test_unmanaged_outer_transaction_is_rejected(self):
        with transaction.atomic(using="runtime"):
            with self.assertRaises(OwnershipRequired):
                semesters.list(self.a)

    def test_manually_disabled_autocommit_is_rejected(self):
        connection = connections["runtime"]
        connection.set_autocommit(False)
        try:
            with self.assertRaises(OwnershipRequired):
                semesters.list(self.a)
        finally:
            connection.rollback()
            connection.set_autocommit(True)

    def test_raw_sql_outer_transaction_is_rejected(self):
        connection = connections["runtime"]
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
        try:
            with self.assertRaises(OwnershipRequired):
                semesters.list(self.a)
        finally:
            connection.rollback()

    def test_privileged_connection_is_rejected_by_service_boundary(self):
        with override_settings(STUDENT_DB_ALIAS="default"):
            with self.assertRaises(ImproperlyConfigured):
                semesters.list(self.a)

    def test_service_does_not_query_the_migration_connection(self):
        with CaptureQueriesContext(connections["default"]) as captured:
            courses.retrieve(self.a, self.course_a.pk)
            courses.update(self.a, self.course_a.pk, version=1, actual_grade="B")
            semesters.create(self.a, label="Extra")
        self.assertEqual(len(captured), 0)

    def test_simultaneous_updates_have_exactly_one_winner(self):
        barrier = Barrier(2)
        validate = courses._validate_record

        def synchronize(record):
            validate(record)
            barrier.wait(timeout=10)

        def update(grade):
            try:
                row = courses.update(self.a, self.course_a.pk, version=1, actual_grade=grade)
                return ("saved", row.actual_grade)
            except RecordConflict:
                return ("conflict", None)
            finally:
                connections["runtime"].close()

        with patch.object(courses, "_validate_record", side_effect=synchronize):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(update, ("B", "C")))
        self.assertEqual(sorted(status for status, _ in results), ["conflict", "saved"])
        winner = next(grade for status, grade in results if status == "saved")
        row = courses.retrieve(self.a, self.course_a.pk)
        self.assertEqual((row.actual_grade, row.record_version), (winner, 2))
