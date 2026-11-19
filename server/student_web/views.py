from functools import wraps
from django.contrib import messages
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.conf import settings as django_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from decimal import ROUND_CEILING, Decimal
from academic_logic import (CLASS_NAMES, DEFAULT_CLASS_BANDS, GRADE_POINTS, academic_summary, class_standing, course_breakdown,
                            predicted_summary, projected_cgpa, target_plan)
from academics import queries, services
from academics.ownership import OwnershipRequired
from accounts.views import student_required
from . import charts, data, export, forms, search, study_plan
from .upload_validation import describe_size
from .data import present
from .context import DISPLAY_COOKIE, display_theme


def error_page(request, title, detail, status):
    response = render(request, 'student_web/error.html', {'title': title, 'detail': detail}, status=status)
    add_never_cache_headers(response)
    return response


def protected(methods=('GET',)):
    def decorate(view):
        @wraps(view)
        def safe(request, identity, *args, **kwargs):
            try:
                return view(request, identity, *args, **kwargs)
            except services.RecordNotFound:
                return error_page(request, 'Record not found', 'This record is unavailable. Return to your workspace to continue.', 404)
            except queries.WorkspaceLimit as error:
                return error_page(request, 'Workspace limit', str(error), 413)
            except OwnershipRequired:
                return error_page(request, 'Please sign in again', 'Your session is no longer valid. Sign in before continuing.', 403)
            except (services.InvalidRecord, ValueError, TypeError):
                return error_page(request, 'Check your request', 'These details could not be accepted. Reload the page and try again.', 400)
            except DatabaseError:
                return error_page(request, 'Please try again', 'Your operation could not be completed. Please try again later.', 503)
        return never_cache(require_http_methods(methods)(student_required(safe)))
    return decorate


def page_context(page, parameters):
    query = parameters.copy()
    result = {'page': page}
    for key, number in (('previous_url', page.previous), ('next_url', page.next)):
        query['page'] = number
        result[key] = '?' + query.urlencode()
    return result


@protected()
def dashboard(request, identity):
    today = timezone.localdate()
    workspace = data.snapshot(identity, today)
    selector = forms.SemesterFilter(request.GET, semesters=workspace['semesters'])
    if not selector.is_valid():
        return error_page(request, 'Choose a semester', 'Choose one of your semesters from the dashboard selector.', 400)
    selected = selector.cleaned_data['semester']
    current = next((row for row in workspace['summary']['semesters'] if row['semester'] == selected), None)
    # Today's classes: ones already over are dimmed; the next one (or the one in progress) is marked.
    now = timezone.localtime().time()
    upcoming = [item for item in workspace['today_classes'] if item.end_time > now]
    workspace['next_class'] = upcoming[0].pk if upcoming else None
    workspace['now'] = now
    names = dict(forms.AI_TOOL_CHOICES)
    for item in workspace['ai_panel']['recent']:
        item['tool_name'] = names.get(item['tool'], item['tool'])
    return render(request, 'student_web/dashboard.html', {**workspace, 'selector': selector, 'current': current,
                  'current_selected': bool(selected), 'today': today})


@protected()
def semester_list(request, identity):
    form = forms.PageForm(request.GET)
    if not form.is_valid():
        return error_page(request, 'Invalid page', 'Choose a page number from 1 to 10,000.', 400)
    page = queries.page(identity, 'semester', number=form.cleaned_data['page'] or 1)
    return render(request, 'student_web/semesters.html', page_context(page, request.GET))


@protected()
def course_list(request, identity):
    selector = forms.CourseFilter(request.GET, semesters=queries.options(identity, 'semester'))
    if not selector.is_valid():
        return render(request, 'student_web/courses.html', {'filter': selector}, status=400)
    page = queries.page(identity, 'course', number=selector.cleaned_data['page'] or 1,
                        semester_id=selector.cleaned_data['semester'], search=selector.cleaned_data['q'])
    return render(request, 'student_web/courses.html', {**page_context(page, request.GET), 'filter': selector})


@protected()
def assignment_list(request, identity):
    selector = forms.AssignmentFilter(request.GET)
    if not selector.is_valid():
        return render(request, 'student_web/assignments.html', {'filter': selector}, status=400)
    today = timezone.localdate()
    page = queries.page(identity, 'assignment', number=selector.cleaned_data['page'] or 1,
                        status=selector.cleaned_data['status'] or 'all', sort=selector.cleaned_data['sort'] or 'due',
                        today=today, search=selector.cleaned_data['q'])
    return render(request, 'student_web/assignments.html', {**page_context(page, request.GET), 'filter': selector,
                  'today': today})


KINDS = {
    'semester': (services.semesters, forms.SemesterForm, 'semester-list'),
    'course': (services.courses, forms.CourseForm, 'course-list'),
    'assignment': (services.assignments, forms.AssignmentForm, 'assignment-list'),
    'material': (services.materials, None, 'material-list'),
    'session': (services.class_sessions, forms.ClassSessionForm, 'timetable'),
    'plan': (services.study_plans, None, 'study-plans'),
}
# What the pages call each kind ("session" is a "class" to the student).
KIND_LABELS = {'session': 'class', 'plan': 'study plan'}


def edit_form(kind, request, identity, record):
    service, form_type, _ = KINDS[kind]
    initial = {name: getattr(record, name) for name in service.fields} if record else {}
    if record:
        initial['version'] = record.record_version
    kwargs = {'initial': initial}
    if kind == 'course':
        kwargs['semesters'] = queries.options(identity, 'semester')
    elif kind in ('assignment', 'session'):
        kwargs['courses'] = queries.options(identity, 'course')
    form = form_type(request.POST if request.method == 'POST' else None, **kwargs)
    if record:
        forms.versioned(form)
    return form


@protected(('GET', 'POST'))
def edit(request, identity, kind, identifier=None):
    if kind not in KINDS:
        raise services.RecordNotFound()
    service, _, destination = KINDS[kind]
    record = service.retrieve(identity, identifier) if identifier else None
    form = edit_form(kind, request, identity, record)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            values = dict(form.cleaned_data)
            version = values.pop('version', None)
            try:
                if record:
                    service.update(identity, record.pk, version=version, **values)
                else:
                    service.create(identity, **values)
            except services.RecordConflict:
                form.add_error(None, 'This record changed in another tab. Reload the latest version before trying again. Your submitted values are shown below.')
                status = 409
            except services.InvalidRecord:
                if kind == 'course' and queries.code_in_use(identity, values['original_code'], record.pk if record else None):
                    form.add_error('original_code', 'You already have a course with this code. Codes must be unique across your semesters.')
                else:
                    form.add_error(None, 'These details could not be saved. Check the fields and try again.')
                status = 400
            else:
                messages.success(request, KIND_LABELS.get(kind, kind).capitalize() + ' saved.')
                return redirect('student_web:' + destination)
        else:
            status = 400
    parent_empty = ((kind == 'course' and len(form.fields['semester_id'].choices) == 1)
                    or (kind in ('assignment', 'session') and len(form.fields['course_id'].choices) == 1))
    return render(request, 'student_web/edit.html', {'form': form, 'kind': kind, 'record': record,
                  'kind_label': KIND_LABELS.get(kind, kind),
                  'parent_empty': parent_empty, 'conflict': status == 409,
                  'cancel_url': reverse('student_web:' + destination)}, status=status)


@protected(('GET', 'POST'))
def delete(request, identity, kind, identifier):
    if kind not in KINDS:
        raise services.RecordNotFound()
    service, _, destination = KINDS[kind]
    record = service.retrieve(identity, identifier)
    form = forms.DeleteForm(request.POST if request.method == 'POST' else None, initial={'version': record.record_version})
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                service.delete(identity, record.pk, version=form.cleaned_data['version'])
            except services.RecordConflict:
                form.add_error(None, 'This record changed. Reload the latest version before confirming deletion.')
                status = 409
            except services.InvalidRecord:
                detail = {'semester': 'This semester still contains courses. Move or remove them before deleting the semester.',
                          'course': 'This course still has assignments or study materials. Remove them before deleting the course.',
                          'assignment': 'This assignment could not be deleted. Reload and try again.',
                          'material': 'This material could not be deleted. Reload and try again.',
                          'session': 'This class could not be deleted. Reload and try again.',
                          'plan': 'This study plan could not be deleted. Reload and try again.'}
                form.add_error(None, detail[kind])
                status = 400
            else:
                messages.success(request, KIND_LABELS.get(kind, kind).capitalize() + ' deleted.')
                return redirect('student_web:' + destination)
        else:
            status = 400
    if kind == 'session':
        course = services.courses.retrieve(identity, record.course_id)
        label = f'{course.normalized_code} on {record.get_weekday_display()} at {record.start_time:%H:%M}'
    elif kind == 'plan':
        course = services.courses.retrieve(identity, record.course_id)
        label = f'the {course.normalized_code} study plan (exam {record.exam_date:%d %b %Y}) and all its topics'
    else:
        label = record.label if kind == 'semester' else record.name if kind == 'course' else record.title
    return render(request, 'student_web/delete.html', {'form': form, 'kind': kind, 'record_label': label,
                  'kind_label': KIND_LABELS.get(kind, kind),
                  'conflict': status == 409, 'cancel_url': reverse('student_web:' + destination)}, status=status)


@protected()
def material_list(request, identity):
    courses = {course.pk: course for course in queries.options(identity, 'course')}
    storage = services.materials.storage(identity)
    rows = [{'material': item, 'course': courses.get(item.course_id), 'stored': item.pk in storage['ids']}
            for item in services.materials.list(identity)]
    return render(request, 'student_web/materials.html', {'rows': rows, 'storage': storage})


@protected()
def study_plans(request, identity):
    """All study plans, soonest exam first, with progress."""
    return render(request, 'student_web/study_plans.html', {'plans': queries.study_plans(identity),
                  'today': timezone.localdate()})


@protected(('GET', 'POST'))
def study_plan_create(request, identity):
    today = timezone.localdate()
    courses = queries.options(identity, 'course')
    form = forms.StudyPlanForm(request.POST if request.method == 'POST' else None, courses=courses, today=today)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            values = form.cleaned_data
            dates = study_plan.spread(len(values['topics']), today, values['exam_date'], values['review_days'])
            try:
                plan = services.study_plans.create_with_topics(
                    identity, course_id=values['course_id'], exam_date=values['exam_date'],
                    review_days=values['review_days'], topics=list(zip(values['topics'], dates)))
            except (services.InvalidRecord, services.RecordNotFound):
                form.add_error(None, 'This plan could not be saved. Check the fields and try again.')
                status = 400
            else:
                messages.success(request, 'Study plan saved.')
                return redirect('student_web:study-plan', plan.pk)
        else:
            status = 400
    return render(request, 'student_web/study_plan_form.html', {'form': form, 'courses_empty': not courses},
                  status=status)


@protected()
def study_plan_detail(request, identity, identifier):
    plan, topics = queries.study_plan(identity, identifier)
    today = timezone.localdate()
    return render(request, 'student_web/study_plan.html', {
        **data.plan_days(plan, topics, today), 'plan': plan, 'today': today, 'topic_form': forms.TopicForm()})


@protected(('POST',))
def study_plan_replan(request, identity, identifier):
    """Share unfinished topics out again over the days left (nothing done is moved)."""
    plan, topics = queries.study_plan(identity, identifier)
    form = forms.VersionForm(request.POST)
    today = timezone.localdate()
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Reload the study plan and try again.', 400)
    if plan.exam_date <= today:
        return error_page(request, 'Exam day has come', 'This exam is today or over, so there are no days left to plan.', 400)
    unfinished = [topic for topic in topics if not topic.done]
    unfinished.sort(key=lambda topic: (topic.position, topic.pk))
    dates = study_plan.spread(len(unfinished), today, plan.exam_date, plan.review_days)
    try:
        services.study_plans.replan(identity, plan.pk, version=form.cleaned_data['version'],
                                    dates={topic.pk: day for topic, day in zip(unfinished, dates)})
    except services.RecordConflict:
        return error_page(request, 'Please reload', 'This plan changed in another tab. Reload it and try again.', 409)
    messages.success(request, f'Re-planned {len(unfinished)} unfinished topic{"s" if len(unfinished) != 1 else ""} from today.')
    return redirect('student_web:study-plan', plan.pk)


@protected(('POST',))
def study_topic_add(request, identity, identifier):
    plan, topics = queries.study_plan(identity, identifier)
    form = forms.TopicForm(request.POST)
    today = timezone.localdate()
    if not form.is_valid():
        return error_page(request, 'Check your topic', form.errors['title'][0] if 'title' in form.errors
                          else 'Reload the study plan and try again.', 400)
    if len(topics) >= study_plan.MAX_TOPICS:
        return error_page(request, 'Plan is full', f'A plan holds at most {study_plan.MAX_TOPICS} topics.', 400)
    days = study_plan.study_days(today, plan.exam_date, plan.review_days)
    services.study_topics.create(identity, plan_id=plan.pk, title=form.cleaned_data['title'],
                                 position=max((topic.position for topic in topics), default=-1) + 1,
                                 planned_date=days[-1] if days else today)
    messages.success(request, 'Topic added.')
    return redirect('student_web:study-plan', plan.pk)


@protected(('POST',))
def study_topic_done(request, identity, identifier):
    topic = services.study_topics.retrieve(identity, identifier)
    form = forms.TopicDoneForm(request.POST)
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Reload the study plan and try again.', 400)
    try:
        services.study_topics.update(identity, topic.pk, version=form.cleaned_data['version'],
                                     done=form.cleaned_data['done'])
    except services.RecordConflict:
        return error_page(request, 'Please reload', 'This topic changed in another tab. Reload the plan and try again.', 409)
    return redirect(reverse('student_web:study-plan', args=[topic.plan_id]) + f'#topic-{topic.pk}')


@protected(('POST',))
def study_topic_delete(request, identity, identifier):
    topic = services.study_topics.retrieve(identity, identifier)
    form = forms.VersionForm(request.POST)
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Reload the study plan and try again.', 400)
    try:
        services.study_topics.delete(identity, topic.pk, version=form.cleaned_data['version'])
    except services.RecordConflict:
        return error_page(request, 'Please reload', 'This topic changed in another tab. Reload the plan and try again.', 409)
    messages.success(request, 'Topic removed.')
    return redirect('student_web:study-plan', topic.plan_id)


@protected()
def timetable(request, identity):
    """The student's weekly classes, Monday to Sunday, with today highlighted."""
    days, clashes = data.timetable_days(queries.timetable(identity))
    return render(request, 'student_web/timetable.html', {'days': days, 'clashes': clashes,
                  'today': timezone.localdate().weekday(), 'has_classes': any(day['classes'] for day in days)})


@protected()
def material_search(request, identity):
    """Find words in all of the student's own study files (their saved text)."""
    form = forms.MaterialSearchForm(request.GET if request.GET else None)
    context = {'form': form, 'results': None}
    if not request.GET:
        return render(request, 'student_web/material_search.html', context)
    if not form.is_valid():
        return render(request, 'student_web/material_search.html', context, status=400)
    waiting = search.prepare(identity)
    words = form.cleaned_data['q']
    found, no_text = services.search_texts.search(identity, words)
    results = []
    for material, text in found[:services.MAX_SEARCH_RESULTS]:
        pieces, count = search.snippets(text, words)
        results.append({'material': material, 'pieces': pieces, 'count': count})
    context.update(results=results, more=len(found) > services.MAX_SEARCH_RESULTS, waiting=waiting,
                   no_text=no_text, words=words)
    return render(request, 'student_web/material_search.html', context)


def upload_too_large(request):
    try:
        return int(request.META.get('CONTENT_LENGTH') or 0) > django_settings.FILE_UPLOAD_MAX_MEMORY_SIZE
    except ValueError:
        return True


@protected(('GET', 'POST'))
def material_upload(request, identity):
    if request.method == 'POST' and upload_too_large(request):
        return error_page(request, 'File too large',
                          f'Choose a PDF or TXT file no larger than {describe_size(forms.upload_cap())}.', 413)
    courses = queries.options(identity, 'course')
    bound = (request.POST, request.FILES) if request.method == 'POST' else ()
    form = forms.MaterialUploadForm(*bound, courses=courses)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            try:
                material = services.materials.create_with_file(
                    identity, title=form.cleaned_data['title'], course_id=form.cleaned_data['course_id'],
                    original_filename=form.file_facts['original_filename'],
                    file_type=form.file_facts['file_type'], content=form.file_content)
            except services.StorageQuotaExceeded:
                form.add_error('file', 'Your study material storage is full (50 files or 200 MiB). '
                                       'Delete materials you no longer need to make room.')
                status = 400
            except services.InvalidRecord:
                form.add_error(None, 'This material could not be saved. Check the fields and try again.')
                status = 400
            else:
                # Save its text for search now (if the reader is busy, the search page does it later).
                search.save_text(identity, material.pk, form.file_content, form.file_facts['file_type'])
                messages.success(request, 'Material checked and stored privately.')
                return redirect('student_web:material-list')
        else:
            status = 400
    return render(request, 'student_web/material_upload.html', {'form': form, 'courses_empty': not courses},
                  status=status)


@protected()
def material_download(request, identity, identifier):
    try:
        material, content = services.materials.read_file(identity, identifier)
    except services.StoredFileDamaged:
        return error_page(request, 'File unavailable', 'This stored file failed an integrity check, so it was '
                          'not sent. Delete it and upload it again.', 500)
    content_type = 'application/pdf' if material.file_type == 'pdf' else 'text/plain; charset=utf-8'
    response = HttpResponse(content, content_type=content_type)
    # Always download, never display inside the site; stop type guessing and active content.
    response['Content-Disposition'] = content_disposition_header(True, material.original_filename)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response


@protected(('POST',))
def assignment_status(request, identity, identifier):
    record = services.assignments.retrieve(identity, identifier)
    form = forms.StatusForm(request.POST)
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Reload the assignment list and try again.', 400)
    try:
        services.assignments.update(identity, record.pk, version=form.cleaned_data['version'],
                                     completed=form.cleaned_data['completed'] == 'true')
    except services.RecordConflict:
        return error_page(request, 'Assignment changed', 'Another tab updated this assignment. Reload the list before changing its status.', 409)
    messages.success(request, 'Assignment status updated.')
    return redirect('student_web:assignment-list')


@protected()
def overview(request, identity):
    workspace = data.standing(identity)
    return render(request, 'student_web/overview.html', {**workspace, **standing_context(workspace)})


def class_bands(identity):
    """(bands, profile, custom): the student's own class bands, or the common guide if none are saved."""
    profile = services.profiles.current(identity)
    bands, custom = _bands_of(profile)
    return bands, profile, custom


def _bands_of(profile):
    """(bands, custom) for a profile (or None): its own five values, or the common guide."""
    values = [getattr(profile, name) for name in services.CLASS_BAND_FIELDS] if profile else []
    if values and all(value is not None for value in values):
        return tuple(values), True
    return DEFAULT_CLASS_BANDS, False


def class_standing_view(cgpa, bands, custom):
    """Where the actual CGPA sits among the bands, with bar geometry (percent of 0-5) for display."""
    standing = class_standing(cgpa, bands)
    rows = list(reversed(standing['bands']))  # lowest class first, left to right on the bar
    segments = [{'name': 'Below Pass', 'left': 0, 'width': float(rows[0]['low']) * 20, 'tone': 0}]
    for index, row in enumerate(rows, 1):
        top = row['high'] if row['high'] is not None else Decimal(5)
        segments.append({'name': row['name'], 'left': float(row['low']) * 20, 'width': float(top - row['low']) * 20,
                         'tone': index})
    gap = standing['gap']
    # Round the distance up, so "0.01 more" is never shown when a little more is really needed.
    gap = None if gap is None else gap.quantize(Decimal('0.01'), rounding=ROUND_CEILING)
    return {**standing, 'segments': [s for s in segments if s['width'] > 0], 'gap': gap, 'custom': custom,
            'marker': None if cgpa is None else float(cgpa) * 20,
            # Near either end the label lines up with the bar's edge instead of centring past it.
            'marker_side': '' if cgpa is None or 0.6 <= cgpa <= 4.4 else (' at-start' if cgpa < 1 else ' at-end')}


def standing_context(workspace):
    """Chart, step-by-step breakdown, grade scale and class standing for the saved grades (read-only)."""
    breakdown = present(course_breakdown(workspace['records']), workspace['labels'])
    bands, custom = _bands_of(workspace.get('profile'))  # no profile read: the common guide
    return {'chart': charts.semester_chart(workspace['summary']), 'breakdown': breakdown,
            'grade_scale': sorted(GRADE_POINTS.items(), key=lambda item: -item[1]),
            'standing': class_standing_view(workspace['summary']['gpa'], bands, custom)}


@protected(('GET', 'POST'))
def predictor(request, identity):
    workspace = data.snapshot(identity)
    # GET only changes which courses are displayed; no hypothetical state is stored.
    selector = forms.SemesterFilter(request.GET, semesters=workspace['semesters'])
    if not selector.is_valid():
        return render(request, 'student_web/predictor.html', {'filter': selector}, status=400)
    selected = selector.cleaned_data['semester']
    available = [c for c in workspace['courses'] if not selected or str(c.semester_id) == selected]
    result = None
    note = ''
    form = None
    status = 200
    try:
        form = forms.PredictorForm(request.POST if request.method == 'POST' else None, courses=available)
    except queries.WorkspaceLimit as error:
        note = str(error)
    if request.method == 'POST' and form:
        if form.is_valid():
            grades = {c.normalized_code: form.cleaned_data['grade_' + c.pk.hex] for c in available
                      if form.cleaned_data['grade_' + c.pk.hex]}
            records = [row for row in workspace['records'] if row['code'] in grades]
            result = data.present(predicted_summary(records, grades), workspace['labels'])
        else:
            status = 400
    return render(request, 'student_web/predictor.html', {'form': form, 'filter': selector, 'result': result,
                  'note': note, 'available': available}, status=status)


@protected(('GET', 'POST'))
def planner(request, identity):
    workspace = data.standing(identity)
    bands, custom = _bands_of(workspace['profile'])
    initial = {}
    if request.method == 'GET' and request.GET:
        # "Aim for a class" buttons: fill the target with that class's lowest CGPA. Nothing is saved.
        aim = forms.AimForm(request.GET)
        if not aim.is_valid():
            return render(request, 'student_web/planner.html', {**workspace, 'form': forms.PlannerForm(), 'result': None,
                          'projection_form': forms.ProjectionForm(), 'aims': _aims(bands), 'aim_error': True}, status=400)
        initial['target'] = bands[aim.cleaned_data['aim']]
    form = forms.PlannerForm(request.POST if request.method == 'POST' else None, initial=initial)
    result = None
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            result = target_plan(workspace['records'], form.cleaned_data['target'], form.cleaned_data['remaining'])
        else:
            status = 400
    return render(request, 'student_web/planner.html', {**workspace, 'form': form, 'result': result,
                  'projection_form': forms.ProjectionForm(), 'aims': _aims(bands), 'aims_custom': custom}, status=status)


def _aims(bands):
    return [{'index': index, 'name': name, 'low': low} for index, (name, low) in enumerate(zip(CLASS_NAMES, bands))]


@protected(('POST',))
def planner_projection(request, identity):
    """Graduation predictor: read-only, nothing hypothetical is saved."""
    workspace = data.standing(identity)
    form = forms.ProjectionForm(request.POST)
    projection = None
    status = 200
    if form.is_valid():
        projection = projected_cgpa(workspace['records'], form.cleaned_data['expected'], form.cleaned_data['remaining'])
    else:
        status = 400
    bands, custom = _bands_of(workspace['profile'])
    return render(request, 'student_web/planner.html', {**workspace, 'form': forms.PlannerForm(), 'result': None,
                  'projection_form': form, 'projection': projection, 'aims': _aims(bands), 'aims_custom': custom},
                  status=status)


@protected()
def standing_print(request, identity):
    """One-page printable summary of the saved grades (read-only)."""
    workspace = data.standing(identity)
    return render(request, 'student_web/standing_print.html',
                  {**workspace, **standing_context(workspace), 'printed_on': timezone.localdate()})


@protected()
def settings(request, identity):
    form = forms.DisplayForm(initial={'theme': display_theme(request)})
    profile = services.profiles.current(identity)
    matric = profile.matric_number if profile else ''
    # Show the last four characters only when at least half of the value stays hidden.
    masked = ('\u2022' * 6 + matric[-4:]) if len(matric) >= 8 else ('\u2022' * 6 if matric else '')
    bands, custom = _bands_of(profile)
    return render(request, 'student_web/settings.html', {'display_form': form, 'profile': profile,
                  'masked_matric': masked, 'storage': services.materials.storage(identity),
                  'class_bands': list(zip(CLASS_NAMES, bands)), 'class_bands_custom': custom})


@protected()
def data_export(request, identity):
    records = queries.export_records(identity)
    now = timezone.now()
    body = export.document(records, {'username': request.user.username, 'email': request.user.email}, now)
    response = HttpResponse(body, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = content_disposition_header(True, f'ucc-my-data-{timezone.localdate(now):%Y-%m-%d}.json')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response


@protected(('GET', 'POST'))
def profile_edit(request, identity):
    profile = services.profiles.current(identity)
    initial = {name: getattr(profile, name) for name in services.PROFILE_FIELDS} if profile else {}
    if profile:
        initial['version'] = profile.record_version
    form = forms.ProfileForm(request.POST if request.method == 'POST' else None, initial=initial)
    if profile:
        forms.versioned(form)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            values = dict(form.cleaned_data)
            version = values.pop('version', None)
            try:
                if profile:
                    services.profiles.update(identity, profile.pk, version=version, **values)
                else:
                    services.profiles.create(identity, **values)
            except services.RecordConflict:
                form.add_error(None, 'Your profile changed in another tab. Reload it before saving again.')
                status = 409
            except services.InvalidRecord:
                form.add_error(None, 'These details could not be saved. Check the fields and try again.')
                status = 400
            else:
                messages.success(request, 'Profile saved.')
                return redirect('student_web:settings')
        else:
            status = 400
    return render(request, 'student_web/profile.html', {'form': form}, status=status)


@protected(('GET', 'POST'))
def class_bands_edit(request, identity):
    """Edit the student's own class-of-degree bands (a guide; their handbook decides)."""
    bands, profile, custom = class_bands(identity)
    initial = dict(zip(forms.ClassBandsForm.FIELDS, bands))
    if profile:
        initial['version'] = profile.record_version
    form = forms.ClassBandsForm(request.POST if request.method == 'POST' else None, initial=initial)
    if profile:
        forms.versioned(form)
    status = 200
    if request.method == 'POST':
        if form.is_valid():
            values = dict(form.cleaned_data)
            version = values.pop('version', None)
            try:
                if profile:
                    services.profiles.update(identity, profile.pk, version=version, **values)
                else:
                    services.profiles.create(identity, **values)
            except services.RecordConflict:
                form.add_error(None, 'Your profile changed in another tab. Reload this page before saving again.')
                status = 409
            except services.InvalidRecord:
                form.add_error(None, 'These bands could not be saved. Check the numbers and try again.')
                status = 400
            else:
                messages.success(request, 'Class bands saved.')
                return redirect('student_web:settings')
        else:
            status = 400
    return render(request, 'student_web/class_bands.html', {'form': form, 'custom': custom,
                  'defaults': list(zip(CLASS_NAMES, DEFAULT_CLASS_BANDS)),
                  'reset_form': forms.versioned(forms.StrictForm(initial={'version': profile.record_version}))
                  if profile and custom else None}, status=status)


@protected(('POST',))
def class_bands_reset(request, identity):
    """Go back to the common guide: clear the student's own bands."""
    _, profile, custom = class_bands(identity)
    form = forms.versioned(forms.StrictForm(request.POST))
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Reload the class bands page and try again.', 400)
    if profile and custom:
        try:
            services.profiles.update(identity, profile.pk, version=form.cleaned_data['version'],
                                     **dict.fromkeys(services.CLASS_BAND_FIELDS))
        except services.RecordConflict:
            return error_page(request, 'Please reload', 'Your profile changed in another tab. Reload the class bands '
                              'page and try again.', 409)
    messages.success(request, 'Class bands reset to the common guide.')
    return redirect('student_web:settings')


@protected(('POST',))
def display_preference(request, identity):
    form = forms.DisplayForm(request.POST)
    if not form.is_valid():
        return error_page(request, 'Check your request', 'Choose System, Light or Dark and try again.', 400)
    theme = form.cleaned_data['theme']
    response = redirect('student_web:settings')
    response.set_cookie(DISPLAY_COOKIE, theme, max_age=365 * 24 * 60 * 60, httponly=True, samesite='Lax',
                        secure=django_settings.SESSION_COOKIE_SECURE)
    messages.success(request, 'Display set to ' + dict(form.fields['theme'].choices)[theme].split(' (')[0] + '.')
    return response


def csrf_failure(request, reason=''):
    return error_page(request, 'Please reload this form', 'The form could not be verified. Reload the page and try again.', 403)


def forbidden(request, exception=None):
    return error_page(request, 'Access unavailable', 'This operation is not permitted. Return to your workspace to continue.', 403)


def bad_request(request, exception=None):
    return error_page(request, 'Check your request', 'The request could not be accepted. Reload the page and try again.', 400)


def not_found(request, exception=None):
    return error_page(request, 'Page not found', 'Choose a page from the navigation to continue.', 404)


def server_error(request):
    return error_page(request, 'Please try again', 'The operation could not be completed. Please try again later.', 500)
