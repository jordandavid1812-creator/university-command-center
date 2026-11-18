"""Adapt PostgreSQL records to the established pure academic engine."""
from datetime import timedelta
from academic_logic import academic_summary
from academics.models import WEEKDAYS
from academics.queries import WEEK_DAYS, WEEK_LIMIT, academic_snapshot, dashboard_reads, standing_snapshot


def snapshot(identity, today=None):
    """Records for the analysis pages. Given today (the dashboard), the same verified read also
    returns assignment totals, upcoming work and the greeting name, in one transaction."""
    if today is None:
        return workspace(*academic_snapshot(identity))
    semesters, courses, totals, upcoming, greeting_name, ai_panel, due, classes = dashboard_reads(identity, today)
    return {**workspace(semesters, courses), 'totals': totals, 'upcoming': upcoming, 'greeting_name': greeting_name,
            'ai_panel': ai_panel, 'week': due_this_week(due, today), 'today_classes': classes, 'show_today_classes': True}


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
    return {**workspace(semesters, courses), 'profile': profile}


def workspace(semesters, courses):
    # Joined metadata also handles a semester created concurrently with this read.
    labels = {str(item.pk): item for item in semesters}
    labels.update({str(item.semester_id): item.semester for item in courses})
    records = [{'code': item.normalized_code, 'name': item.name, 'credit_units': item.credit_units,
                'grade': item.actual_grade, 'semester': str(item.semester_id)} for item in courses]
    summary = present(academic_summary(records), labels)
    return {'semesters': semesters, 'courses': courses, 'records': records, 'summary': summary, 'labels': labels}


def present(summary, labels):
    for row in summary['semesters']:
        semester = labels.get(row['semester'])
        row['label'] = semester.label if semester else 'Unassigned'
        row['display_order'] = semester.display_order if semester else None
    return summary

