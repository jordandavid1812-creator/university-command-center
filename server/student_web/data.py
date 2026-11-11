"""Adapt PostgreSQL records to the established pure academic engine."""
from academic_logic import academic_summary
from academics.queries import academic_snapshot


def snapshot(identity):
    semesters, courses = academic_snapshot(identity)
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
