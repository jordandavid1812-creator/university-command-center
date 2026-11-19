"""Build the "Download my data" JSON document from already-read records. No I/O here."""
import json
from academics.services import CLASS_BAND_FIELDS

FORMAT = "university-command-center-export"
VERSION = 1


def _when(value):
    return value.isoformat() if value else None


def document(records, account, exported_at):
    profile = records["profile"]
    data = {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": exported_at.isoformat(),
        "account": {"username": account["username"], "email": account["email"]},
        "profile": None if profile is None else {
            "display_name": profile.display_name, "institution": profile.institution,
            "programme": profile.programme, "level": profile.level, "matric_number": profile.matric_number,
            "grading_scale": profile.grading_scale,
            # Own class-of-degree bands as exact decimal strings, or null when the common guide is used.
            "class_bands": None if profile.first_class_min is None else {
                name: str(getattr(profile, name)) for name in CLASS_BAND_FIELDS},
        },
        "semesters": [{"id": str(s.pk), "label": s.label, "display_order": s.display_order,
                       "created_at": _when(s.created_at)} for s in records["semesters"]],
        "courses": [{"id": str(c.pk), "semester_id": str(c.semester_id), "code": c.original_code,
                     "name": c.name, "credit_units": str(c.credit_units), "actual_grade": c.actual_grade,
                     "created_at": _when(c.created_at)} for c in records["courses"]],
        "assignments": [{"id": str(a.pk), "course_id": str(a.course_id), "title": a.title,
                         "due_date": a.due_date.isoformat(), "completed": a.completed} for a in records["assignments"]],
        "timetable": [{"id": str(c.pk), "course_id": str(c.course_id), "day": c.get_weekday_display(),
                       "start": c.start_time.strftime("%H:%M"), "end": c.end_time.strftime("%H:%M"),
                       "type": c.kind, "venue": c.venue} for c in records.get("classes", [])],
        "study_plans": [{"id": str(p.pk), "course_id": str(p.course_id), "exam_date": p.exam_date.isoformat(),
                         "review_days": p.review_days,
                         "topics": [{"title": t.title, "planned_date": t.planned_date.isoformat(), "done": t.done}
                                    for t in records.get("topics", []) if t.plan_id == p.pk]}
                        for p in records.get("plans", [])],
        "study_materials": [{"id": str(m.pk), "course_id": str(m.course_id), "title": m.title,
                             "original_filename": m.original_filename, "file_type": m.file_type,
                             "size_bytes": m.size_bytes, "file_stored": m.pk in records["stored"],
                             "created_at": _when(m.created_at)} for m in records["materials"]],
        "ai_results": [{"id": str(r.pk), "material_id": str(r.material_id), "request_id": str(r.request_id),
                        "tool": r.tool, "question": r.question, "result": r.result, "shape_version": r.shape_version,
                        "created_at": _when(r.created_at)} for r in records["ai_results"]],
        "ai_requests": [{"id": str(r.pk), "tool": r.tool,  # no AI company or model names (owner decision)
                         "status": r.status, "error_category": r.error_category,
                         "characters_sent": r.characters_sent, "truncated": r.truncated,
                         "created_at": _when(r.created_at)} for r in records["ai_requests"]],
        "notes": "Study file contents are not included; download each stored file from Study materials.",
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
