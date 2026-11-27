"""Adapt PostgreSQL records to the established pure academic engine."""
from datetime import timedelta
from academic_logic import academic_summary
from grading_policy import SCALES
from academics.models import WEEKDAYS
from academics.queries import WEEK_DAYS, WEEK_LIMIT, academic_snapshot, dashboard_reads, standing_snapshot


def snapshot(identity, today=None):
    """Records for the analysis pages. Given today (the dashboard), the same verified read also
    returns assignment totals, upcoming work and the greeting name, in one transaction."""
    if today is None:
        return workspace(*academic_snapshot(identity))
    (semesters, courses, totals, upcoming, greeting_name, ai_panel, due, classes, study,
     scale, bands, studied, started) = dashboard_reads(identity, today)
    return {**workspace(semesters, courses, scale), 'band_values': bands, 'totals': totals, 'upcoming': upcoming, 'greeting_name': greeting_name,
            'ai_panel': ai_panel, 'week': due_this_week(due, today), 'today_classes': classes, 'show_today_classes': True,
            'today_study': study,
            'getting_started': getting_started(semesters, courses, totals, started, ai_panel),
            'streak': study_streak(studied, today), 'study_day_count': len(studied),
            'has_materials': bool(started.get('materials'))}


def study_streak(days, today):
    """The study streak from the Lagos calendar days with study activity (last 60 days). The streak
    counts back from today, or from yesterday while today is still open ("keep it going"). Also the
    best run in the window and the last seven days for the dashboard dots."""
    from datetime import timedelta
    days = {day for day in days if day <= today}
    end = today if today in days else today - timedelta(days=1)
    current = 0
    while end - timedelta(days=current) in days:
        current += 1
    best = run = 0
    for offset in range(60, -1, -1):
        run = run + 1 if today - timedelta(days=offset) in days else 0
        best = max(best, run)
    week = [{'date': today - timedelta(days=offset), 'active': today - timedelta(days=offset) in days,
             'label': f"{today - timedelta(days=offset):%a}"[:2], 'today': offset == 0} for offset in range(6, -1, -1)]
    return {'current': current, 'best': best, 'today_done': today in days, 'week': week,
            'active_week': sum(day['active'] for day in week), 'any': bool(days)}


def getting_started(semesters, courses, totals, started, ai_panel):
    """The dashboard's "Get started" checklist for new students: six first steps, each done or not,
    from records the dashboard already read. It disappears once every step is done."""
    steps = [
        ('semester', 'Create your first semester', 'Group your courses by semester.', bool(semesters),
         'student_web:semester-create', 'Create semester'),
        ('course', 'Add a course with its grade', 'Your GPA and CGPA appear straight away.',
         any(course.actual_grade for course in courses), 'student_web:course-create', 'Add course'),
        ('assignment', 'Add an assignment', 'Never miss a deadline: it shows in "Due this week".',
         bool(totals.get('total')), 'student_web:assignment-create', 'Add assignment'),
        ('timetable', 'Add your timetable', "See today's classes here every day.", started['classes'],
         'student_web:session-create', 'Add a class'),
        ('notes', 'Upload your lecture notes', 'PDF or text, up to the size shown on the upload page.',
         started['materials'], 'student_web:material-upload', 'Upload notes'),
        ('ai', 'Make a quiz or flashcards', 'Open a file in Study materials, then choose Study tools.',
         bool(ai_panel.get('recent')), 'student_web:material-list', 'Open study materials'),
    ]
    # A button is offered only when it can work: a course needs a semester; assignments, classes and
    # notes need a course; study tools need an uploaded file. Otherwise the step says what comes first.
    blocked = {'course': None if semesters else 'Create a semester first.',
               'assignment': None if courses else 'Add a course first.',
               'timetable': None if courses else 'Add a course first.',
               'notes': None if courses else 'Add a course first.',
               'ai': None if started['materials'] else 'Upload your notes first.'}
    rows = [{'key': key, 'title': title, 'hint': blocked.get(key) or hint, 'done': done, 'url': url, 'action': action,
             'blocked': bool(blocked.get(key)) and not done}
            for key, title, hint, done, url, action in steps]
    done = sum(row['done'] for row in rows)
    # The next step is the first one that is not done and can be done now.
    upcoming = next((row['key'] for row in rows if not row['done'] and not row['blocked']), None)
    return {'steps': rows, 'done': done, 'total': len(rows), 'percent': round(100 * done / len(rows)),
            'complete': done == len(rows), 'next': upcoming}


def plan_days(plan, topics, today):
    """Each planned day (earliest topic or today, up to the day before the exam) with its topics,
    plus progress and the revision days. Unfinished topics on past days are overdue. An empty
    revision day is shown once, as a revision day, not also as an empty study day."""
    from datetime import timedelta
    from .study_plan import review_dates
    first = min([today] + [topic.planned_date for topic in topics])
    last = max([plan.exam_date - timedelta(days=1)] + [topic.planned_date for topic in topics])
    review = review_dates(today, plan.exam_date, plan.review_days)
    by_day = {}
    for topic in topics:
        by_day.setdefault(topic.planned_date, []).append({'topic': topic, 'overdue': not topic.done and topic.planned_date < today})
    days = []
    day = first
    while day <= last:
        if day in by_day or (day >= today and day not in review):
            days.append({'date': day, 'topics': by_day.get(day, []), 'is_today': day == today, 'past': day < today})
        day += timedelta(days=1)
    done = sum(topic.done for topic in topics)
    return {'days': days, 'done': done, 'total': len(topics),
            'percent': round(100 * done / len(topics)) if topics else 0,
            'overdue': sum(1 for topic in topics if not topic.done and topic.planned_date < today),
            'days_left': (plan.exam_date - today).days,
            'review': [day for day in review if day not in by_day]}


def timetable_days(classes):
    """Monday to Sunday, each with its classes in time order. A class that starts before the
    previous one on the same day has ended is marked as a clash (shown as a warning only)."""
    days = [{'weekday': number, 'name': name, 'classes': []} for number, name in WEEKDAYS]
    for item in classes:
        days[item.weekday]['classes'].append({'item': item, 'clash': False})
    clashes = 0
    for day in days:
        latest_end = None
        for row in day['classes']:
            if latest_end is not None and row['item'].start_time < latest_end:
                row['clash'] = True
                clashes += 1
            latest_end = max(latest_end, row['item'].end_time) if latest_end else row['item'].end_time
    return days, clashes


def due_this_week(assignments, today):
    """Seven days from today, each with its pending assignments, plus counts for the reminder
    pop-up. The counts hold no titles, so a pop-up never shows course work on a lock screen."""
    more = len(assignments) > WEEK_LIMIT
    assignments = assignments[:WEEK_LIMIT]
    days = []
    for offset in range(WEEK_DAYS):
        day = today + timedelta(days=offset)
        label = 'Today' if offset == 0 else 'Tomorrow' if offset == 1 else f'{day:%a} {day.day} {day:%b}'  # %-d fails on Windows
        items = [item for item in assignments if item.due_date == day]
        # Course codes once each, A to Z (a stable order); titles stay in "Upcoming deadlines" (five at most).
        codes = sorted({item.course.normalized_code for item in items})
        days.append({'date': day, 'label': label, 'items': items, 'codes': codes})
    return {'days': days, 'total': len(assignments), 'more': more,
            'counts': {'date': today.isoformat(), 'today': len(days[0]['items']), 'tomorrow': len(days[1]['items']),
                       'week': len(assignments)}}


def standing(identity):
    """Records for the GPA, print and planner pages, plus the profile holding the class bands."""
    semesters, courses, profile = standing_snapshot(identity)
    return {**workspace(semesters, courses, profile.grading_scale if profile else 'five'), 'profile': profile}


# What each scale looks like on the pages. The 5-point texts are exactly the ones used before.
SCALE_TEXT = {
    'five': {'code': 'five', 'name': '5-point', 'max': '5.00', 'top': 5, 'letters': 'A=5, B=4, C=3, D=2, E=1 and F=0',
             'points': 'A=5, B=4, C=3, D=2, E=1, F=0'},
    'four': {'code': 'four', 'name': '4-point', 'max': '4.00', 'top': 4, 'letters': 'A=4, B=3, C=2, D=1 and F=0',
             'points': 'A=4, B=3, C=2, D=1, F=0'},
}


def scale_of(code):
    """(policy, display texts) for a student's saved scale code."""
    return SCALES[code], SCALE_TEXT[code]


def workspace(semesters, courses, scale='five'):
    # Joined metadata also handles a semester created concurrently with this read.
    labels = {str(item.pk): item for item in semesters}
    labels.update({str(item.semester_id): item.semester for item in courses})
    records = [{'code': item.normalized_code, 'name': item.name, 'credit_units': item.credit_units,
                'grade': item.actual_grade, 'semester': str(item.semester_id)} for item in courses]
    policy, text = scale_of(scale)
    summary = present(academic_summary(records, policy=policy), labels)
    return {'semesters': semesters, 'courses': courses, 'records': records, 'summary': summary, 'labels': labels,
            'policy': policy, 'scale': text}


def present(summary, labels):
    for row in summary['semesters']:
        semester = labels.get(row['semester'])
        row['label'] = semester.label if semester else 'Unassigned'
        row['display_order'] = semester.display_order if semester else None
    return summary



# Scholar levels for the Command Centre: XP thresholds and names (owner's choice).
LEVELS = ((0, 'Fresher'), (100, 'Scholar'), (250, 'Rising Star'), (500, "Dean's List"), (900, 'Distinction'),
          (1500, 'First Class Legend'))


def scholar_level(xp):
    """(level number from 1, name, XP at this level's start, the next level or None)."""
    number = max(i for i, (low, _) in enumerate(LEVELS) if xp >= low)
    low, name = LEVELS[number]
    following = LEVELS[number + 1] if number + 1 < len(LEVELS) else None
    return number + 1, name, low, following


def command_centre(ws, today):
    """The dashboard's Command Centre: Today's Mission (three small steps), XP and level, and the
    numbers the "what if" grade picker needs. All from records the dashboard already read: nothing
    new is stored and no query is added."""
    from django.urls import reverse
    streak, totals, week, ai = ws['streak'], ws['totals'], ws['week'], ws['ai_panel']
    topics, summary, policy = ws['today_study'], ws['summary'], ws['policy']
    due_today = week['days'][0]['items'] if week else []
    mission = []
    if topics:
        first = topics[0]
        mission.append({'key': 'study', 'done': streak['today_done'], 'title': 'Study one topic',
                        'detail': f'{first.title} ({first.plan.course.normalized_code})',
                        'url': reverse('student_web:study-plan', args=[first.plan_id])})
    else:
        mission.append({'key': 'study', 'done': streak['today_done'], 'title': 'Study for a few minutes',
                        'detail': 'Any quiz, saved mistake, ticked topic or finished task counts',
                        'url': reverse('student_web:material-list')})
    if due_today or totals['overdue']:
        task = due_today[0] if due_today else None
        mission.append({'key': 'deadline', 'done': False,
                        'title': f'Finish {task.title}' if task else 'Clear an overdue task',
                        'detail': task.course.normalized_code if task else f"{totals['overdue']} overdue",
                        'url': reverse('student_web:assignment-list') + ('?status=overdue' if not task else '')})
    else:
        mission.append({'key': 'deadline', 'done': True, 'title': 'No deadline today',
                        'detail': 'A head start on your week', 'url': reverse('student_web:assignment-list')})
    if ws.get('has_materials'):
        mission.append({'key': 'practise', 'done': ai['used_today'] > 0, 'title': 'Practise with a quiz',
                        'detail': '5 questions from your own notes', 'url': reverse('student_web:material-list')})
    else:
        mission.append({'key': 'practise', 'done': False, 'title': 'Upload one lecture note',
                        'detail': 'Then turn it into a quiz in seconds', 'url': reverse('student_web:material-upload')})
    done = sum(item['done'] for item in mission)
    xp = (10 * ws.get('study_day_count', 0) + 15 * totals['completed'] + 20 * summary['graded']
          + 5 * len(ws['courses']) + 5 * streak['best'])
    number, name, low, following = scholar_level(xp)
    level = {'number': number, 'name': name, 'xp': xp,
             'next_name': following[1] if following else None,
             'to_next': following[0] - xp if following else 0,
             'percent': round(100 * (xp - low) / (following[0] - low)) if following else 100}
    # The "what if" picker: graded totals and the ungraded courses (first record per code, like the summary).
    graded = {row['code'] for row in ws['records'] if row['grade']}
    seen, open_courses = set(), []
    for row in ws['records']:
        if not row['grade'] and row['code'] not in graded and row['code'] not in seen:
            seen.add(row['code'])
            open_courses.append({'code': row['code'], 'name': row['name'], 'units': float(row['credit_units'])})
    standing = ws.get('standing')
    whatif = {'points': float(summary['points']), 'units': float(summary['units']), 'max': float(policy.maximum),
              'grades': {letter: float(value) for letter, value in policy.grade_points.items()},
              'courses': open_courses[:12],
              'bands': [{'name': row['name'], 'low': float(row['low'])} for row in standing['bands']] if standing else []}
    return {'mission': mission, 'done': done, 'total': len(mission), 'left': len(mission) - done, 'level': level, 'whatif': whatif,
            'ring': round(100 * done / len(mission))}
