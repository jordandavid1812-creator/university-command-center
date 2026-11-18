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
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .models import (AI_ERROR_CATEGORIES, MAX_AI_RESULT_BYTES, Assignment, ClassSession, Course, MaterialFile, MaterialText,
                     Semester, StudentProfile, StudyAiRequest, StudyAiResult, StudyMaterial)
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
class_sessions = StudentRecords(ClassSession, {"course_id", "weekday", "start_time", "end_time", "kind", "venue"},
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

    def storage(self, identity):
        """Stored-file IDs plus usage against the per-student quota, in one transaction."""
        with student_transaction(identity):
            owner = require_identity(identity)
            files = MaterialFile.objects.using(database_alias()).filter(owner_id=owner)
            ids = set(files.values_list("material_id", flat=True))
            used = files.aggregate(total=Sum(Length("content")))["total"] or 0
        return {"ids": ids, "files": len(ids), "bytes": used,
                "max_files": MAX_FILES_PER_STUDENT, "max_bytes": MAX_STORED_BYTES_PER_STUDENT,
                "max_mib": MAX_STORED_BYTES_PER_STUDENT // (1024 * 1024)}

    def stored_ids(self, identity):
        """IDs of this student's materials that have a stored file."""
        with student_transaction(identity):
            owner = require_identity(identity)
            return set(MaterialFile.objects.using(database_alias()).filter(owner_id=owner)
                       .values_list("material_id", flat=True))


materials = MaterialRecords(StudyMaterial, {"course_id", "title", "original_filename", "file_type", "size_bytes"},
                            ("course_id", Course))


class ProfileRecords(StudentRecords):
    """At most one profile per student (unique owner); profiles are edited, never deleted."""

    def current(self, identity):
        with student_transaction(identity):
            return self._records(require_identity(identity)).first()

    def delete(self, identity, identifier, *, version):
        raise InvalidRecord()


MAX_SEARCH_RESULTS = 50


class SearchTexts:
    """The saved text of each stored study file, for search. Written once, never edited; it goes
    when its material is deleted. Everything runs as the signed-in student under forced RLS."""

    def missing(self, identity, limit):
        """IDs of stored files with no saved text yet, oldest first, and how many there are."""
        with student_transaction(identity):
            owner = require_identity(identity)
            waiting = MaterialFile.objects.using(database_alias()).filter(
                owner_id=owner, material__search_text__isnull=True)
            return list(waiting.order_by("material__created_at", "material_id")
                        .values_list("material_id", flat=True)[:limit]), waiting.count()

    def save(self, identity, material_id, *, text="", truncated=False, problem=""):
        """Save a file's text (or why it has none) once. A second save of the same file does nothing."""
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                alias = database_alias()
                if MaterialText.objects.using(alias).filter(owner_id=owner, material_id=material_id).exists():
                    return
                row = MaterialText(owner_id=owner, material_id=material_id, text=text, truncated=truncated,
                                   problem=problem)
                row._state.db = alias
                # As in StudentRecords._validate_record: the owner comes from the signed capability and
                # the runtime role cannot read accounts; its FK and RLS check the owner in SQL.
                row.full_clean(exclude=["owner"], validate_unique=False)
                MaterialText.objects.using(alias).bulk_create([row])
        except ValidationError:
            raise InvalidRecord() from None
        except IntegrityError:
            # Two tabs saving the same file at once: the first one won, which is fine.
            with student_transaction(identity):
                if not MaterialText.objects.using(database_alias()).filter(
                        owner_id=require_identity(identity), material_id=material_id).exists():
                    raise InvalidRecord() from None

    def search(self, identity, words):
        """(material, text) for this student's files whose text contains `words` (any letter case,
        taken literally), by title, at most MAX_SEARCH_RESULTS + 1; and counts of files without text."""
        with student_transaction(identity):
            owner = require_identity(identity)
            texts = MaterialText.objects.using(database_alias()).filter(owner_id=owner)
            found = list(texts.filter(problem="", text__icontains=words)
                         .select_related("material", "material__course")
                         .order_by("material__title", "material_id")[:MAX_SEARCH_RESULTS + 1])
            no_text = texts.exclude(problem="").count()
            return [(row.material, row.text) for row in found], no_text


search_texts = SearchTexts()


PROFILE_FIELDS = {"display_name", "institution", "programme", "level", "matric_number"}
CLASS_BAND_FIELDS = ("first_class_min", "second_upper_min", "second_lower_min", "third_class_min", "pass_min")
profiles = ProfileRecords(StudentProfile, PROFILE_FIELDS | set(CLASS_BAND_FIELDS))


# AI study assistant records (docs/AI_STUDY_ASSISTANT_PLAN.md, stage 1). No provider code here.
AI_REQUESTS_PER_DAY = 50
MAX_AI_RESULTS_PER_STUDENT = 500
AI_DAY_ZONE = ZoneInfo("Africa/Lagos")
AI_STALE_AFTER = timedelta(minutes=2)
_AI_CATEGORIES = frozenset(code for code, _ in AI_ERROR_CATEGORIES)


class AiLimitReached(Exception):
    """Refused before anything is sent. `reason` is "daily", "results" or "busy"."""
    def __init__(self, reason):
        super().__init__("AI request refused: " + reason)
        self.reason = reason


class AiRequestClosed(Exception):
    """The request is no longer in progress (for example it was marked interrupted); nothing was saved."""
    def __init__(self):
        super().__init__("This AI request is no longer in progress.")


def ai_day_range(now=None):
    """[start, end) of the current local day (Africa/Lagos) as aware datetimes."""
    local = (now or timezone.now()).astimezone(AI_DAY_ZONE)
    start = datetime.combine(local.date(), time.min, tzinfo=AI_DAY_ZONE)
    return start, start + timedelta(days=1)


class AiRecords:
    """Ledger and saved results. Owner, IDs, status and timestamps are server-owned."""

    def _requests(self, owner):
        return StudyAiRequest.objects.using(database_alias()).filter(owner_id=owner)

    def _results(self, owner):
        return StudyAiResult.objects.using(database_alias()).filter(owner_id=owner)

    def _lock(self, owner):
        with connections[database_alias()].cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ["ucc-ai-reserve:" + str(owner)])

    def _mark_stale(self, owner, now):
        self._requests(owner).filter(status="sent", created_at__lt=now - AI_STALE_AFTER).update(
            status="interrupted", updated_at=now)

    def _existing(self, owner, consent_token_hash):
        return self._requests(owner).filter(consent_token_hash=consent_token_hash).first()

    def find_request(self, identity, consent_token_hash):
        """The request already made with this consent token, or None."""
        with student_transaction(identity):
            return self._requests(require_identity(identity)).filter(
                consent_token_hash=consent_token_hash).first()

    def reserve(self, identity, *, tool, provider, model, characters_sent, truncated, consent_token_hash):
        """Record one request before anything is sent. Returns (request, created).

        Must be the outermost call (not inside another transaction), so its two steps
        commit separately:
        1. In its own transaction, this student's stale in-flight requests become
           interrupted. A refusal in step 2 therefore cannot undo it. No advisory lock
           is needed here: it only touches rows over two minutes old, and row locks make
           two concurrent markings safe (the second finds nothing left to mark).
        2. Under a per-student lock: an existing request with the same consent token is
           returned unchanged (created=False), so a repeated Send never sends twice.
           Otherwise the in-flight, daily and saved-result limits are checked, in that
           order, and the new row is inserted.
        """
        if connections[database_alias()].in_atomic_block:
            raise RuntimeError("ai.reserve must not run inside another transaction.")
        with student_transaction(identity):
            self._mark_stale(require_identity(identity), timezone.now())
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                self._lock(owner)
                existing = self._existing(owner, consent_token_hash)
                if existing is not None:
                    return existing, False
                now = timezone.now()
                if self._requests(owner).filter(status="sent").exists():
                    raise AiLimitReached("busy")
                start, end = ai_day_range(now)
                if self._requests(owner).filter(created_at__gte=start, created_at__lt=end).count() >= AI_REQUESTS_PER_DAY:
                    raise AiLimitReached("daily")
                if self._results(owner).count() >= MAX_AI_RESULTS_PER_STUDENT:
                    raise AiLimitReached("results")
                if type(characters_sent) is not int or type(truncated) is not bool:
                    raise InvalidRecord()
                request = StudyAiRequest(owner_id=owner, tool=tool, provider=provider, model=model,
                                         characters_sent=characters_sent, truncated=truncated,
                                         consent_token_hash=consent_token_hash)
                request._state.db = database_alias()
                try:
                    request.full_clean(exclude=["owner"], validate_unique=False)
                except ValidationError:
                    raise InvalidRecord() from None
                StudyAiRequest.objects.using(database_alias()).bulk_create([request])
                return request, True
        except IntegrityError:
            # The lock makes this unreachable for one student, but if the unique token
            # constraint ever fires, return the request that already used the token.
            existing = self.find_request(identity, consent_token_hash)
            if existing is not None:
                return existing, False
            raise InvalidRecord() from None

    def _close(self, owner, request_id, **values):
        """Close an in-progress request: RecordNotFound if it is not this student's,
        AiRequestClosed if it is no longer in progress."""
        identifier = record_id(request_id)
        changed = self._requests(owner).filter(pk=identifier, status="sent").update(
            updated_at=timezone.now(), **values)
        if changed != 1:
            if not self._requests(owner).filter(pk=identifier).exists():
                raise RecordNotFound()
            raise AiRequestClosed()

    def fail(self, identity, request_id, category, status_class=""):
        """Mark an in-progress request failed (RecordNotFound / AiRequestClosed as in _close)."""
        if category not in _AI_CATEGORIES or status_class not in ("", "3xx", "4xx", "5xx"):
            raise InvalidRecord()
        with student_transaction(identity):
            self._close(require_identity(identity), request_id, status="failed", error_category=category,
                        status_class=status_class)

    def succeed(self, identity, request_id, *, material_id, result, question="", shape_version=1):
        """Save a checked result and mark its request succeeded, both or neither.

        Only a request still in progress can succeed; otherwise AiRequestClosed and nothing is saved.
        """
        try:
            size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            raise InvalidRecord() from None
        if size > MAX_AI_RESULT_BYTES:
            raise InvalidRecord()
        try:
            with student_transaction(identity):
                owner = require_identity(identity)
                request = self._requests(owner).filter(pk=record_id(request_id)).first()
                if request is None:
                    raise RecordNotFound()
                self._close(owner, request.pk, status="succeeded")
                saved = StudyAiResult(owner_id=owner, material_id=record_id(material_id), request_id=request.pk,
                                      tool=request.tool, question=question, result=result,
                                      shape_version=shape_version)
                saved._state.db = database_alias()
                try:
                    saved.full_clean(exclude=["owner"], validate_unique=False)
                except ValidationError:
                    raise InvalidRecord() from None
                StudyAiResult.objects.using(database_alias()).bulk_create([saved])
                return saved
        except IntegrityError:
            raise InvalidRecord() from None

    def get_request(self, identity, identifier):
        with student_transaction(identity):
            try:
                return self._requests(require_identity(identity)).get(pk=record_id(identifier))
            except StudyAiRequest.DoesNotExist:
                raise RecordNotFound() from None

    def get_result(self, identity, identifier):
        with student_transaction(identity):
            try:
                return self._results(require_identity(identity)).get(pk=record_id(identifier))
            except StudyAiResult.DoesNotExist:
                raise RecordNotFound() from None

    def result_for_request(self, identity, request_id):
        """The saved result of one of this student's requests, or None (never saved or deleted)."""
        with student_transaction(identity):
            return self._results(require_identity(identity)).filter(request_id=record_id(request_id)).first()

    def results_for(self, identity, material_id):
        """Saved results for one of the student's materials, newest first."""
        with student_transaction(identity):
            return list(self._results(require_identity(identity)).filter(material_id=record_id(material_id))
                        .order_by("-created_at", "id"))

    def delete_result(self, identity, identifier):
        """Delete one saved result (its ledger row stays and still counts)."""
        with student_transaction(identity):
            owner = require_identity(identity)
            deleted, _ = self._results(owner).filter(pk=record_id(identifier)).delete()
            if not deleted:
                raise RecordNotFound()

    def usage(self, identity):
        with student_transaction(identity):
            owner = require_identity(identity)
            start, end = ai_day_range()
            return {"used_today": self._requests(owner).filter(created_at__gte=start, created_at__lt=end).count(),
                    "daily_limit": AI_REQUESTS_PER_DAY, "results": self._results(owner).count(),
                    "max_results": MAX_AI_RESULTS_PER_STUDENT}


ai = AiRecords()
