"""Bounded, owner-scoped read services for server-rendered pages.

All data is evaluated inside the existing signed student transaction. Never return
querysets or use the migration connection. Mutations remain in academics.services.
"""
from dataclasses import dataclass
from datetime import timedelta
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Count, Q
from .models import (Assignment, ClassSession, Course, StudyPlan, StudyTopic, MaterialFile, Semester, StudentProfile, StudyAiRequest, StudyAiResult,
                     StudyMaterial, QuizMistake, MAX_MISTAKES_PER_STUDENT)
from .ownership import database_alias, student_transaction
from .services import (MAX_AI_RESULTS_PER_STUDENT, ai_daily_limit, InvalidRecord, RecordNotFound, ai_day_range,
                       record_id)

PAGE_SIZE = 25
MAX_COURSES = 1000
MAX_SEMESTERS = 200
MAX_PREDICTION_COURSES = 200
MAX_EXPORT_ASSIGNMENTS = 20000
MAX_EXPORT_MATERIALS = 5000
MAX_EXPORT_AI_REQUESTS = 20000
DASHBOARD_RECENT_AI_RESULTS = 5
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
        records = _records(MODELS[kind], identity.student_id)
        limit = MAX_SEMESTERS if kind == 'semester' else MAX_COURSES
        if kind == 'course':
            records = records.order_by('normalized_code', 'id')
        rows = list(records[:limit + 1])
        if len(rows) > limit:
            raise WorkspaceLimit(f'This selector supports up to {limit} {kind}s. No records were changed.')
        return rows


def page(identity, kind, *, number=1, semester_id=None, status='all', sort='due', today=None, search=''):
    if kind not in MODELS or type(number) is not int or not 1 <= number <= 10000:
        raise InvalidRecord()
    if not isinstance(search, str) or len(search) > 80 or (search and kind == 'semester'):
        raise InvalidRecord()
    with student_transaction(identity):
        # The transaction validates the live session and signature before yielding.
        owner = identity.student_id
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
        if search:
            if kind == 'course':
                records = records.filter(Q(normalized_code__icontains=search) | Q(name__icontains=search))
            else:
                records = records.filter(Q(title__icontains=search) | Q(course__normalized_code__icontains=search)
                                         | Q(course__name__icontains=search))
        paginator = Paginator(records, PAGE_SIZE)
        try:
            selected = paginator.page(number)
        except EmptyPage:
            raise RecordNotFound() from None
        return RecordPage(list(selected.object_list), paginator.count, selected.number, paginator.num_pages)


def academic_snapshot(identity):
    """One bounded course read with joined semester metadata; no float conversion."""
    with student_transaction(identity):
        # The transaction validates the live session and signature before yielding.
        return _academic_snapshot(identity.student_id)


def standing_snapshot(identity):
    """The academic snapshot plus the student's own profile (for class bands), in one verified read."""
    with student_transaction(identity):
        owner = identity.student_id
        semesters, records = _academic_snapshot(owner)
        return semesters, records, _records(StudentProfile, owner).first()


def _academic_snapshot(owner):
    records = list(_records(Course, owner).select_related('semester').order_by(
        'semester__display_order', 'semester__created_at', 'semester_id', 'created_at', 'id')[:MAX_COURSES + 1])
    semesters = list(_records(Semester, owner)[:MAX_SEMESTERS + 1])
    if len(records) > MAX_COURSES or len(semesters) > MAX_SEMESTERS:
        raise WorkspaceLimit('Analysis supports up to 1,000 courses and 200 semesters. No partial GPA is shown; your records are unchanged.')
    return semesters, records


def _assignment_metrics(owner, today):
    records = _records(Assignment, owner)
    counts = records.aggregate(total_count=Count('id'), completed_count=Count('id', filter=Q(completed=True)),
                               pending_count=Count('id', filter=Q(completed=False)),
                               overdue_count=Count('id', filter=Q(completed=False, due_date__lt=today)))
    totals = {key.removesuffix('_count'): value for key, value in counts.items()}
    upcoming = list(records.filter(completed=False, due_date__gte=today).select_related('course').order_by('due_date', 'id')[:5])
    return totals, upcoming


WEEK_DAYS = 7
WEEK_LIMIT = 50


def _due_this_week(owner, today):
    """Pending assignments due from today through the next six days (at most WEEK_LIMIT + 1, so
    the page can say when there are more)."""
    return list(_records(Assignment, owner).filter(
        completed=False, due_date__gte=today, due_date__lte=today + timedelta(days=WEEK_DAYS - 1))
        .select_related('course').order_by('due_date', 'id')[:WEEK_LIMIT + 1])


MAX_CLASSES = 300


def _classes(owner, weekday=None):
    records = _records(ClassSession, owner).select_related('course')
    if weekday is not None:
        records = records.filter(weekday=weekday)
    rows = list(records.order_by('weekday', 'start_time', 'end_time', 'id')[:MAX_CLASSES + 1])
    if len(rows) > MAX_CLASSES:
        raise WorkspaceLimit(f'The timetable supports up to {MAX_CLASSES} classes. No records were changed.')
    return rows


MAX_PLANS = 100


def study_plans(identity):
    """The student's study plans with their course and topic counts, soonest exam first."""
    with student_transaction(identity):
        owner = identity.student_id
        return list(_records(StudyPlan, owner).select_related('course')
                    .annotate(topic_count=Count('topics'), done_count=Count('topics', filter=Q(topics__done=True)))
                    .order_by('exam_date', 'id')[:MAX_PLANS])


def study_plan(identity, identifier):
    """One plan with its course and topics (by date, then order), or RecordNotFound."""
    with student_transaction(identity):
        owner = identity.student_id
        try:
            plan = _records(StudyPlan, owner).select_related('course').get(pk=record_id(identifier))
        except StudyPlan.DoesNotExist:
            raise RecordNotFound() from None
        topics = list(_records(StudyTopic, owner).filter(plan_id=plan.pk).order_by('planned_date', 'position', 'id'))
        return plan, topics


def _study_today(owner, today):
    """Unfinished topics planned for today or earlier, with their course, for the dashboard."""
    return list(_records(StudyTopic, owner).filter(done=False, planned_date__lte=today, plan__exam_date__gt=today)
                .select_related('plan__course').order_by('planned_date', 'plan__exam_date', 'position', 'id')[:20])


def timetable(identity):
    """All of the student's weekly classes with their courses, Monday first, in time order."""
    with student_transaction(identity):
        return _classes(identity.student_id)


def assignment_metrics(identity, today):
    with student_transaction(identity):
        return _assignment_metrics(identity.student_id, today)


def dashboard_reads(identity, today):
    """Every dashboard read in ONE verified transaction: records, assignments and greeting name."""
    with student_transaction(identity):
        owner = identity.student_id
        semesters, records = _academic_snapshot(owner)
        totals, upcoming = _assignment_metrics(owner, today)
        name, scale = _records(StudentProfile, owner).values_list('display_name', 'grading_scale').first() or ('', 'five')
        return (semesters, records, totals, upcoming, name or '', _ai_panel(owner), _due_this_week(owner, today),
                _classes(owner, today.weekday()), _study_today(owner, today), scale, _started(owner))


def _started(owner):
    """For the dashboard's "Get started" checklist: whether the student has any study file and any
    timetable class. ONE query (a UNION of two one-row reads, same transaction; nothing else is read),
    so the dashboard keeps its query budget."""
    from django.db.models import CharField, Value
    material = _records(StudyMaterial, owner).values_list(Value('materials', output_field=CharField()))[:1]
    session = _records(ClassSession, owner).values_list(Value('classes', output_field=CharField()))[:1]
    found = {row[0] for row in material.union(session, all=True)}
    return {'materials': 'materials' in found, 'classes': 'classes' in found}


def _ai_panel(owner):
    """Today's AI usage and the most recent saved results (two queries, same transaction)."""
    start, end = ai_day_range()
    used = _records(StudyAiRequest, owner).filter(created_at__gte=start, created_at__lt=end).count()
    recent = list(_records(StudyAiResult, owner).order_by('-created_at', 'id')
                  .values('id', 'tool', 'created_at', 'material__title')[:DASHBOARD_RECENT_AI_RESULTS])
    return {'used_today': used, 'daily_limit': ai_daily_limit(), 'recent': recent}


def code_in_use(identity, code, exclude=None):
    with student_transaction(identity):
        records = _records(Course, identity.student_id).filter(normalized_code=code.strip(' ').upper())
        if exclude is not None:
            records = records.exclude(pk=record_id(exclude))
        return records.exists()


def export_records(identity):
    """Every academic record of one student in ONE verified transaction, or none at all if too large."""
    with student_transaction(identity):
        owner = identity.student_id
        semesters = list(_records(Semester, owner).order_by("display_order", "created_at", "id")[:MAX_SEMESTERS + 1])
        courses = list(_records(Course, owner).order_by("created_at", "id")[:MAX_COURSES + 1])
        assignments = list(_records(Assignment, owner).order_by("due_date", "id")[:MAX_EXPORT_ASSIGNMENTS + 1])
        materials = list(_records(StudyMaterial, owner).order_by("created_at", "id")[:MAX_EXPORT_MATERIALS + 1])
        stored = set(_records(MaterialFile, owner).values_list("material_id", flat=True))
        profile = _records(StudentProfile, owner).first()
        ai_requests = list(_records(StudyAiRequest, owner).order_by("created_at", "id")[:MAX_EXPORT_AI_REQUESTS + 1])
        ai_results = list(_records(StudyAiResult, owner).order_by("created_at", "id")[:MAX_AI_RESULTS_PER_STUDENT + 1])
        classes = list(_records(ClassSession, owner).order_by("weekday", "start_time", "id")[:MAX_CLASSES + 1])
        plans = list(_records(StudyPlan, owner).order_by("exam_date", "id")[:MAX_PLANS + 1])
        topics = list(_records(StudyTopic, owner).order_by("plan_id", "planned_date", "position", "id")[:MAX_PLANS * 60 + 1])
        mistakes = list(_records(QuizMistake, owner).order_by("created_at", "id")[:MAX_MISTAKES_PER_STUDENT + 1])
    if (len(mistakes) > MAX_MISTAKES_PER_STUDENT or len(classes) > MAX_CLASSES or len(plans) > MAX_PLANS or len(topics) > MAX_PLANS * 60 or len(semesters) > MAX_SEMESTERS or len(courses) > MAX_COURSES
            or len(assignments) > MAX_EXPORT_ASSIGNMENTS or len(materials) > MAX_EXPORT_MATERIALS
            or len(ai_requests) > MAX_EXPORT_AI_REQUESTS or len(ai_results) > MAX_AI_RESULTS_PER_STUDENT):
        raise WorkspaceLimit("Your workspace is too large to export in one file. No file was created.")
    return {"semesters": semesters, "courses": courses, "assignments": assignments,
            "materials": materials, "stored": stored, "profile": profile,
            "ai_requests": ai_requests, "ai_results": ai_results, "classes": classes, "plans": plans, "topics": topics,
            "mistakes": mistakes}
