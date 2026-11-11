"""Bounded, owner-scoped read services for server-rendered pages.

All data is evaluated inside the existing signed student transaction. Never return
querysets or use the migration connection. Mutations remain in academics.services.
"""
from dataclasses import dataclass
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Count, Q
from .models import Assignment, Course, Semester
from .ownership import database_alias, require_identity, student_transaction
from .services import InvalidRecord, RecordNotFound, record_id

PAGE_SIZE = 25
MAX_COURSES = 1000
MAX_SEMESTERS = 200
MAX_PREDICTION_COURSES = 200
MODELS = {'semester': Semester, 'course': Course, 'assignment': Assignment}


class WorkspaceLimit(ValueError):
    pass


@dataclass(frozen=True)
class RecordPage:
    items: list
    total: int
    number: int
    pages: int

    @property
    def has_previous(self):
        return self.number > 1

    @property
    def has_next(self):
        return self.number < self.pages

    @property
    def previous(self):
        return self.number - 1

    @property
    def next(self):
        return self.number + 1


def _records(model, owner):
    return model.objects.using(database_alias()).filter(owner_id=owner)


def options(identity, kind):
    if kind not in ('semester', 'course'):
        raise InvalidRecord()
    with student_transaction(identity):
        records = _records(MODELS[kind], require_identity(identity))
        limit = MAX_SEMESTERS if kind == 'semester' else MAX_COURSES
        if kind == 'course':
            records = records.order_by('normalized_code', 'id')
        rows = list(records[:limit + 1])
        if len(rows) > limit:
            raise WorkspaceLimit(f'This selector supports up to {limit} {kind}s. No records were changed.')
        return rows


def page(identity, kind, *, number=1, semester_id=None, status='all', sort='due', today=None):
    if kind not in MODELS or type(number) is not int or not 1 <= number <= 10000:
        raise InvalidRecord()
    with student_transaction(identity):
        owner = require_identity(identity)
        records = _records(MODELS[kind], owner)
        if kind == 'course':
            records = records.select_related('semester').order_by(
                'semester__display_order', 'semester__created_at', 'semester_id', 'normalized_code', 'id')
            if semester_id:
                records = records.filter(semester_id=record_id(semester_id))
        elif kind == 'assignment':
            records = records.select_related('course')
            if status not in ('all', 'pending', 'completed', 'upcoming', 'overdue') or sort not in ('due', 'latest'):
                raise InvalidRecord()
            if status != 'all':
                records = records.filter(completed=(status == 'completed'))
            if status in ('upcoming', 'overdue'):
                if today is None:
                    raise InvalidRecord()
                records = records.filter(**{'due_date__gte' if status == 'upcoming' else 'due_date__lt': today})
            records = records.order_by('-due_date' if sort == 'latest' else 'due_date', 'id')
        paginator = Paginator(records, PAGE_SIZE)
        try:
            selected = paginator.page(number)
        except EmptyPage:
            raise RecordNotFound() from None
        return RecordPage(list(selected.object_list), paginator.count, selected.number, paginator.num_pages)


def academic_snapshot(identity):
    """One bounded course read with joined semester metadata; no float conversion."""
    with student_transaction(identity):
        owner = require_identity(identity)
        records = list(_records(Course, owner).select_related('semester').order_by(
            'semester__display_order', 'semester__created_at', 'semester_id', 'created_at', 'id')[:MAX_COURSES + 1])
        semesters = list(_records(Semester, owner)[:MAX_SEMESTERS + 1])
        if len(records) > MAX_COURSES or len(semesters) > MAX_SEMESTERS:
            raise WorkspaceLimit('Analysis supports up to 1,000 courses and 200 semesters. No partial GPA is shown; your records are unchanged.')
        return semesters, records


def assignment_metrics(identity, today):
    with student_transaction(identity):
        records = _records(Assignment, require_identity(identity))
        counts = records.aggregate(total_count=Count('id'), completed_count=Count('id', filter=Q(completed=True)),
                                   pending_count=Count('id', filter=Q(completed=False)),
                                   overdue_count=Count('id', filter=Q(completed=False, due_date__lt=today)))
        totals = {key.removesuffix('_count'): value for key, value in counts.items()}
        upcoming = list(records.filter(completed=False, due_date__gte=today).select_related('course').order_by('due_date', 'id')[:5])
        return totals, upcoming


def code_in_use(identity, code, exclude=None):
    with student_transaction(identity):
        records = _records(Course, require_identity(identity)).filter(normalized_code=code.strip(' ').upper())
        if exclude is not None:
            records = records.exclude(pk=record_id(exclude))
        return records.exists()
