"""Read-only academic rules shared by the CLI and web interface."""
import math
from decimal import Decimal, InvalidOperation

GRADE_POINTS = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}


def validate_courses(courses):
    """Return normalized course details without changing the saved records."""
    if not isinstance(courses, list):
        raise ValueError("Course data must be a list.")
    warnings = []
    semesters = {}
    seen_codes = set()
    for number, course in enumerate(courses, start=1):
        if not isinstance(course, dict):
            warnings.append(f"Skipping Course {number}: invalid course record.")
            continue

        code = course.get("code")
        if not isinstance(code, str) or not code.strip():
            warnings.append(f"Skipping Course {number}: missing or invalid course code.")
            continue
        code = code.strip().upper()
        units = course.get("credit_units")
        if (isinstance(units, bool) or not isinstance(units, (int, float))
                or units <= 0):
            warnings.append(f"Skipping {code}: credit units must be a positive number.")
            continue
        try:
            finite_units = math.isfinite(units)
        except OverflowError:
            finite_units = False
        if not finite_units:
            warnings.append(f"Skipping {code}: credit units are too large or not finite.")
            continue

        saved_grade = course.get("grade")
        grade = saved_grade.strip().upper() if isinstance(saved_grade, str) else saved_grade
        if grade is not None and grade != "":
            if not isinstance(grade, str) or grade not in GRADE_POINTS:
                warnings.append(f"Skipping {code}: invalid saved grade.")
                continue
        if code in seen_codes:
            warnings.append(f"Skipping duplicate course {code}: already included.")
            continue
        seen_codes.add(code)

        semester = course.get("semester")
        if not isinstance(semester, str) or not semester.strip():
            semester = "Unassigned"
        semesters.setdefault(semester, []).append((code, units, grade))

    return semesters, warnings


def academic_summary(courses):
    semesters, warnings = validate_courses(courses)
    result = {"points": Decimal(0), "units": Decimal(0), "graded": 0,
              "ungraded": 0, "semesters": [], "warnings": warnings}
    for semester, records in semesters.items():
        row = {"semester": semester, "points": Decimal(0), "units": Decimal(0),
               "graded": 0, "ungraded": 0}
        for code, units, grade in records:
            if not grade:
                row["ungraded"] += 1
                continue
            units = Decimal(str(units))
            row["points"] += GRADE_POINTS[grade] * units
            row["units"] += units
            row["graded"] += 1
        row["gpa"] = row["points"] / row["units"] if row["units"] else None
        result["semesters"].append(row)
        for field in ("points", "units", "graded", "ungraded"):
            result[field] += row[field]
    result["gpa"] = result["points"] / result["units"] if result["units"] else None
    return result


def predicted_summary(courses, grades):
    semesters, warnings = validate_courses(courses)
    hypothetical = []
    for semester, records in semesters.items():
        for code, units, actual_grade in records:
            grade = grades.get(code)
            if not isinstance(grade, str) or grade not in GRADE_POINTS:
                raise ValueError(f"Choose a predicted grade for {code}.")
            hypothetical.append({"code": code, "credit_units": units,
                                 "semester": semester, "grade": grade})
    result = academic_summary(hypothetical)
    result["warnings"] = warnings
    return result


def target_plan(courses, target, remaining):
    try:
        target = Decimal(str(target))
        remaining = Decimal(str(remaining))
    except InvalidOperation:
        raise ValueError("Enter valid numbers for target CGPA and remaining credits.")
    if not target.is_finite() or not 0 <= target <= 5:
        raise ValueError("Target CGPA must be between 0.00 and 5.00.")
    if not remaining.is_finite() or remaining <= 0:
        raise ValueError("Remaining credits must be greater than zero and finite.")
    # Reject extreme input outside ordinary numeric range before arithmetic.
    if remaining < Decimal("1e-300") or remaining > Decimal("1e300"):
        raise ValueError("Remaining credits are too large or too small to calculate safely.")
    current = academic_summary(courses)
    total = current["units"] + remaining
    required = (target * total - current["points"]) / remaining
    status = "impossible" if required > 5 else "guaranteed" if required <= 0 else "achievable"
    return {"current": current, "total": total, "required": required, "status": status}

