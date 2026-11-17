"""Read-only academic rules shared by the CLI and web interface."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

GRADE_POINTS = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}
MIN_CREDITS = Decimal("0.0001")
MAX_CREDITS = Decimal("1000000")
DECIMAL_STEP = Decimal("0.0001")


def decimal_input(value):
    """Parse a bounded numeric input without converting it through float."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Please enter a valid number.")
    text = str(value).strip()
    if not text or len(text) > 128:
        raise ValueError("Please enter a valid number of at most 128 characters.")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError("Please enter a valid number.")
    if not number.is_finite():
        raise ValueError("Please enter a finite number.")
    return number


def checked_credits(value, allow_zero=False):
    number = decimal_input(value)
    if allow_zero and number == 0:
        return number
    if not MIN_CREDITS <= number <= MAX_CREDITS:
        raise ValueError("Credit units must be greater than zero, from 0.0001 to 1000000.")
    with localcontext() as context:
        context.prec = 50
        if number != number.quantize(DECIMAL_STEP):
            raise ValueError("Credit units can have at most four decimal places.")
    return number


def checked_target(value):
    number = decimal_input(value)
    if not 0 <= number <= 5:
        raise ValueError("Please enter a number from 0.00 to 5.00.")
    with localcontext() as context:
        context.prec = 50
        if number != number.quantize(DECIMAL_STEP):
            raise ValueError("Target CGPA can have at most four decimal places.")
    return number


def checked_grade(value, allow_ungraded=True):
    if value is None and allow_ungraded:
        return None
    if not isinstance(value, str):
        raise ValueError("Grades must be letters A to F.")
    grade = value.strip().upper()
    if grade == "" and allow_ungraded:
        return None
    if grade not in GRADE_POINTS:
        raise ValueError("Grades must be letters A to F.")
    return grade


def weighted_gpa(points, units):
    if not units:
        return None
    with localcontext() as context:
        context.prec = 28
        return points / units


def validate_courses(courses, check_saved_grades=True):
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
            name = course.get("name") or f"Course {number}"
            warnings.append(f"Skipping {name}: missing or invalid course code.")
            continue
        code = code.strip().upper()
        units = course.get("credit_units")
        # PostgreSQL uses exact Decimal credits; JSON int/float behavior stays unchanged.
        if isinstance(units, bool) or not isinstance(units, (int, float, Decimal)):
            warnings.append(f"Skipping {code}: credit units must be a positive number.")
            continue
        try:
            checked_credits(units)
        except ValueError as error:
            warnings.append(f"Skipping {code}: {error}")
            continue

        try:
            grade = checked_grade(course.get("grade"))
        except ValueError:
            if check_saved_grades:
                warnings.append(f"Skipping {code}: invalid saved grade.")
                continue
            grade = None
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
    with localcontext() as context:
        context.prec = 50
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
            row["gpa"] = weighted_gpa(row["points"], row["units"])
            result["semesters"].append(row)
            for field in ("points", "units", "graded", "ungraded"):
                result[field] += row[field]
        result["gpa"] = weighted_gpa(result["points"], result["units"])
        return result


def predicted_summary(courses, grades):
    if not isinstance(grades, dict):
        raise ValueError("Predicted grades must be a mapping of course codes to grades.")
    semesters, warnings = validate_courses(courses, check_saved_grades=False)
    hypothetical = []
    for semester, records in semesters.items():
        for code, units, actual_grade in records:
            try:
                grade = checked_grade(grades.get(code), allow_ungraded=False)
            except ValueError:
                raise ValueError(f"Choose a predicted grade for {code}.")
            hypothetical.append({"code": code, "credit_units": units,
                                 "semester": semester, "grade": grade})
    result = academic_summary(hypothetical)
    result["warnings"] = warnings
    return result


def target_plan(courses, target, remaining):
    target = checked_target(target)
    remaining = checked_credits(remaining)
    current = academic_summary(courses)
    with localcontext() as context:
        context.prec = 50
        total = current["units"] + remaining
        # Equivalent to the original formula, with less subtractive cancellation.
        required = target + (target * current["units"] - current["points"]) / remaining
    status = "impossible" if required > 5 else "guaranteed" if required <= 0 else "achievable"
    return {"current": current, "total": total, "required": required, "status": status}


def course_breakdown(courses):
    """Step-by-step working behind academic_summary: each valid course's grade points and
    quality points (points x units), per semester and overall. Same validation and duplicate
    rules as academic_summary; ungraded courses are listed but count towards nothing."""
    with localcontext() as context:
        context.prec = 50
        semesters, warnings = validate_courses(courses)
        result = {"semesters": [], "points": Decimal(0), "units": Decimal(0), "warnings": warnings}
        for semester, records in semesters.items():
            row = {"semester": semester, "courses": [], "points": Decimal(0), "units": Decimal(0)}
            for code, units, grade in records:
                units = Decimal(str(units))
                if grade:
                    quality = GRADE_POINTS[grade] * units
                    row["points"] += quality
                    row["units"] += units
                    row["courses"].append({"code": code, "units": units, "grade": grade,
                                           "grade_points": GRADE_POINTS[grade], "quality_points": quality})
                else:
                    row["courses"].append({"code": code, "units": units, "grade": None,
                                           "grade_points": None, "quality_points": None})
            row["gpa"] = weighted_gpa(row["points"], row["units"])
            result["semesters"].append(row)
            result["points"] += row["points"]
            result["units"] += row["units"]
        result["gpa"] = weighted_gpa(result["points"], result["units"])
        return result


def projected_cgpa(courses, expected, remaining):
    """Final CGPA if the student averages `expected` (0-5) over `remaining` credits they supply.
    Read-only planning: actual grades stay fixed and nothing hypothetical is saved."""
    expected = checked_target(expected)
    remaining = checked_credits(remaining)
    current = academic_summary(courses)
    with localcontext() as context:
        context.prec = 50
        total = current["units"] + remaining
        projected = (current["points"] + expected * remaining) / total
    return {"current": current, "expected": expected, "remaining": remaining, "total": total,
            "projected": projected}


def validate_assignments(assignments, courses=None):
    """Return (original index, record) pairs; never repair or rewrite records."""
    if not isinstance(assignments, list):
        raise ValueError("Assignment data must be a list.")
    codes = None
    if courses is not None:
        codes = {course["code"].strip().upper() for course in courses
                 if isinstance(course, dict) and isinstance(course.get("code"), str) and course["code"].strip()}
    valid = []
    warnings = []
    for index, record in enumerate(assignments):
        message = f"Assignment {index + 1} needs attention and was excluded from pending counts."
        if not isinstance(record, dict):
            warnings.append(message)
            continue
        title, code, due = (record.get(key) for key in ("title", "course_code", "due_date"))
        if (not isinstance(title, str) or not title.strip() or not isinstance(code, str)
                or not code.strip() or type(record.get("completed")) is not bool):
            warnings.append(message)
            continue
        try:
            if not isinstance(due, str) or date.fromisoformat(due).isoformat() != due:
                raise ValueError("Invalid date")
        except ValueError:
            warnings.append(message)
            continue
        if codes is not None and code.strip().upper() not in codes:
            warnings.append(message)
            continue
        valid.append((index, record))
    return valid, warnings

