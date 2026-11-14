"""The supported synchronous academic write/read boundary.

Each operation requires a trusted capability, filters by owner and runs under RLS.
Return evaluated records/lists; never return a lazy queryset outside the transaction.
"""
import hashlib
import uuid
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connections
from django.db.models import Count, F, Sum
from django.db.models.functions import Length
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from .models import Assignment, Course, MaterialFile, Semester, StudyMaterial
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


# Per-student storage limits for stored study files (owner decision, step 5).
MAX_FILES_PER_STUDENT = 50
MAX_STORED_BYTES_PER_STUDENT = 200 * 1024 * 1024


def fingerprint(content):
    """SHA-256 of stored file bytes, as 64 lower-case hex characters."""
    return hashlib.sha256(content).hexdigest()


class StoredFileDamaged(Exception):
    def __init__(self):
        super().__init__("A stored file failed its integrity check.")


class StorageQuotaExceeded(Exception):
    def __init__(self):
        super().__init__("Your study material storage is full. Delete materials to make room.")


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


class MaterialRecords(StudentRecords):
    """File facts are set once at upload; afterwards only title and course may change."""
    updatable = frozenset({"course_id", "title"})

    def update(self, identity, identifier, *, version, **fields):
        if not fields.keys() <= self.updatable:
            raise InvalidRecord()
        return super().update(identity, identifier, version=version, **fields)

    def create_with_file(self, identity, *, title, course_id, original_filename, file_type, content):
        """Save a checked material and its bytes together, or neither."""
        if type(content) is not bytes:
            raise InvalidRecord()
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                alias = database_alias()
                with connections[alias].cursor() as cursor:
                    # One upload at a time per student, so two uploads cannot both pass the quota.
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                                   ["ucc-material-quota:" + str(owner)])
                usage = self._records(owner).filter(stored_file__isnull=False).aggregate(
                    count=Count("id"), total=Sum(Length("stored_file__content")))
                if (usage["count"] + 1 > MAX_FILES_PER_STUDENT
                        or (usage["total"] or 0) + len(content) > MAX_STORED_BYTES_PER_STUDENT):
                    raise StorageQuotaExceeded()
                material = self.create(identity, title=title, course_id=course_id, original_filename=original_filename,
                                       file_type=file_type, size_bytes=len(content))
                stored = MaterialFile(owner_id=owner, material_id=material.pk, content=content,
                                      sha256=fingerprint(content))
                stored._state.db = alias
                self._validate_record(stored)
                MaterialFile.objects.using(alias).bulk_create([stored])
                return material
        except IntegrityError:
            raise InvalidRecord() from None

    def read_file(self, identity, identifier):
        """Return (material, bytes) for the owner only; the fingerprint must still match."""
        with student_transaction(identity):
            owner = require_identity(identity)
            material = self._get(owner, identifier)
            try:
                stored = MaterialFile.objects.using(database_alias()).get(owner_id=owner, material_id=material.pk)
            except MaterialFile.DoesNotExist:
                raise RecordNotFound() from None
            content = bytes(stored.content)
            if fingerprint(content) != stored.sha256:
                raise StoredFileDamaged()
            return material, content

    def stored_ids(self, identity):
        """IDs of this student's materials that have a stored file."""
        with student_transaction(identity):
            owner = require_identity(identity)
            return set(MaterialFile.objects.using(database_alias()).filter(owner_id=owner)
                       .values_list("material_id", flat=True))


materials = MaterialRecords(StudyMaterial, {"course_id", "title", "original_filename", "file_type", "size_bytes"},
                            ("course_id", Course))
