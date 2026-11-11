"""The supported synchronous academic write/read boundary.

Each operation requires a trusted capability, filters by owner and runs under RLS.
Return evaluated records/lists; never return a lazy queryset outside the transaction.
"""
import uuid
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import F
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from .models import Assignment, Course, Semester
from .ownership import database_alias, require_identity, student_transaction


class RecordNotFound(LookupError):
    def __init__(self):
        super().__init__("Record not found.")


class RecordConflict(Exception):
    def __init__(self):
        super().__init__("Record has changed; reload and try again.")


class InvalidRecord(ValueError):
    def __init__(self):
        super().__init__("Invalid record.")


def record_id(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise RecordNotFound() from None


def expected_version(value):
    if type(value) is not int or not 1 <= value < 2**63 - 1:
        raise InvalidRecord()
    return value


class StudentRecords:
    """Fixed model/field allowlists; owner, IDs, versions and timestamps are server-owned."""
    def __init__(self, model, fields, relation=None):
        self.model = model
        self.fields = frozenset(fields)
        self.relation = relation

    def _records(self, owner):
        return self.model.objects.using(database_alias()).filter(owner_id=owner)

    def _get(self, owner, identifier, lock=False):
        records = self._records(owner)
        if lock:
            records = records.select_for_update()
        try:
            return records.get(pk=record_id(identifier))
        except self.model.DoesNotExist:
            raise RecordNotFound() from None

    def _validate_changes(self, owner, changes):
        if not changes.keys() <= self.fields:
            raise InvalidRecord()
        values = dict(changes)
        if self.relation:
            field, model = self.relation
            if field in values:
                identifier = record_id(values[field])
                if not model.objects.using(database_alias()).filter(pk=identifier, owner_id=owner).exists():
                    raise RecordNotFound()
                values[field] = identifier
        return values

    def _validate_record(self, record):
        # Owner came from the trusted capability. Runtime has NO account table
        # privileges; its FK and the signed RLS function check identity in SQL.
        # All other fields/shared validators still run; DB checks stay authoritative.
        try:
            record.full_clean(exclude=["owner"], validate_unique=False)
        except ValidationError:
            raise InvalidRecord() from None

    def list(self, identity):
        with student_transaction(identity):
            owner = require_identity(identity)
            records = self._records(owner)
            if self.model is not Semester:
                records = records.order_by("created_at", "id")
            return list(records)

    def retrieve(self, identity, identifier):
        with student_transaction(identity):
            return self._get(require_identity(identity), identifier)

    def create(self, identity, **fields):
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                values = self._validate_changes(owner, fields)
                record = self.model(owner_id=owner, **values)
                record._state.db = database_alias()
                self._validate_record(record)
                self.model.objects.using(database_alias()).bulk_create([record])
                return record
        except IntegrityError:
            # Do not leak constraint details/identifiers across the service boundary.
            raise InvalidRecord() from None

    def update(self, identity, identifier, *, version, **fields):
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                version = expected_version(version)
                record = self._get(owner, identifier)
                if record.record_version != version:
                    raise RecordConflict()
                values = self._validate_changes(owner, fields)
                for name, value in values.items():
                    setattr(record, name, value)
                self._validate_record(record)
                values = {name: getattr(record, name) for name in values}
                if "original_code" in values:
                    values["normalized_code"] = record.normalized_code
                # checked_grade may turn a blank or lower-case grade into NULL/A-F.
                if "actual_grade" in values:
                    values["actual_grade"] = record.actual_grade
                values.update(record_version=F("record_version") + 1, updated_at=timezone.now())
                changed = self._records(owner).filter(pk=record.pk, record_version=version).update(**values)
                if changed != 1:
                    raise RecordConflict()
                return self._get(owner, record.pk)
        except IntegrityError:
            raise InvalidRecord() from None

    def delete(self, identity, identifier, *, version):
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                version = expected_version(version)
                record = self._get(owner, identifier, lock=True)
                if record.record_version != version:
                    raise RecordConflict()
                record.delete(using=database_alias())
        except (ProtectedError, IntegrityError):
            raise InvalidRecord() from None


semesters = StudentRecords(Semester, {"label", "display_order"})
courses = StudentRecords(Course, {"semester_id", "original_code", "name", "credit_units", "actual_grade"},
                         ("semester_id", Semester))
assignments = StudentRecords(Assignment, {"course_id", "title", "due_date", "completed"},
                             ("course_id", Course))
