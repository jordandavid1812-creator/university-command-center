"""Read-only academic rules shared by the CLI and web interface."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from grading_policy import LEGACY_POLICY, checked_policy

# Historical public dictionary for CLI/forms; calculations use the immutable policy.
GRADE_POINTS = {grade: int(points) for grade, points in LEGACY_POLICY.grade_points.items()}
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


def checked_target(value, *, policy=LEGACY_POLICY):
    policy = checked_policy(policy)
    number = decimal_input(value)
    if not 0 <= number <= policy.maximum:
        if policy is LEGACY_POLICY:
            raise ValueError("Please enter a number from 0.00 to 5.00.")
        raise ValueError(f"Please enter a number from 0 to {policy.maximum}.")
    with localcontext() as context:
        context.prec = 50
        if number != number.quantize(DECIMAL_STEP):
            raise ValueError("Target CGPA can have at most four decimal places.")
    return number


def checked_grade(value, allow_ungraded=True, *, policy=LEGACY_POLICY):
    policy = checked_policy(policy)
    message = ("Grades must be letters A to F." if policy is LEGACY_POLICY
               else "Grade must be included in the selected policy.")
    if value is None and allow_ungraded:
        return None
    if not isinstance(value, str):
        raise ValueError(message)
    grade = value.strip().upper()
    if grade == "" and allow_ungraded:
        return None
    if grade not in policy.grade_points:
        raise ValueError(message)
    return grade


def weighted_gpa(points, units):
    if not units:
        return None
    with localcontext() as context:
        context.prec = 28
        return points / units


def validate_courses(courses, check_saved_grades=True, *, policy=LEGACY_POLICY):
    """Return normalized course details without changing the saved records."""
    policy = checked_policy(policy)
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
            grade = checked_grade(course.get("grade"), policy=policy)
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


def academic_summary(courses, *, policy=LEGACY_POLICY):
    with localcontext() as context:
        context.prec = 50
        semesters, warnings = validate_courses(courses, policy=policy)
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
                row["points"] += policy.grade_points[grade] * units
                row["units"] += units
                row["graded"] += 1
            row["gpa"] = weighted_gpa(row["points"], row["units"])
            result["semesters"].append(row)
            for field in ("points", "units", "graded", "ungraded"):
                result[field] += row[field]
        result["gpa"] = weighted_gpa(result["points"], result["units"])
        return result


def predicted_summary(courses, grades, *, policy=LEGACY_POLICY):
    if not isinstance(grades, dict):
        raise ValueError("Predicted grades must be a mapping of course codes to grades.")
    semesters, warnings = validate_courses(courses, check_saved_grades=False, policy=policy)
    hypothetical = []
    for semester, records in semesters.items():
        for code, units, actual_grade in records:
            try:
                grade = checked_grade(grades.get(code), allow_ungraded=False, policy=policy)
            except ValueError:
                raise ValueError(f"Choose a predicted grade for {code}.")
            hypothetical.append({"code": code, "credit_units": units,
                                 "semester": semester, "grade": grade})
    result = academic_summary(hypothetical, policy=policy)
    result["warnings"] = warnings
    return result


def target_plan(courses, target, remaining, *, policy=LEGACY_POLICY):
    target = checked_target(target, policy=policy)
    remaining = checked_credits(remaining)
    current = academic_summary(courses, policy=policy)
    with localcontext() as context:
        context.prec = 50
        total = current["units"] + remaining
        # Equivalent to the original formula, with less subtractive cancellation.
        required = target + (target * current["units"] - current["points"]) / remaining
    status = "impossible" if required > policy.maximum else "guaranteed" if required <= 0 else "achievable"
    return {"current": current, "total": total, "required": required, "status": status}


def course_breakdown(courses, *, policy=LEGACY_POLICY):
    """Step-by-step working behind academic_summary: each valid course's grade points and
    quality points (points x units), per semester and overall. Same validation and duplicate
    rules as academic_summary; ungraded courses are listed but count towards nothing."""
    with localcontext() as context:
        context.prec = 50
        semesters, warnings = validate_courses(courses, policy=policy)
        result = {"semesters": [], "points": Decimal(0), "units": Decimal(0), "warnings": warnings}
        for semester, records in semesters.items():
            row = {"semester": semester, "courses": [], "points": Decimal(0), "units": Decimal(0)}
            for code, units, grade in records:
                units = Decimal(str(units))
                if grade:
                    quality = policy.grade_points[grade] * units
                    row["points"] += quality
                    row["units"] += units
                    row["courses"].append({"code": code, "units": units, "grade": grade,
                                           "grade_points": policy.grade_points[grade], "quality_points": quality})
                else:
                    row["courses"].append({"code": code, "units": units, "grade": None,
                                           "grade_points": None, "quality_points": None})
            row["gpa"] = weighted_gpa(row["points"], row["units"])
            result["semesters"].append(row)
            result["points"] += row["points"]
            result["units"] += row["units"]
        result["gpa"] = weighted_gpa(result["points"], result["units"])
        return result


def projected_cgpa(courses, expected, remaining, *, policy=LEGACY_POLICY):
    """Final CGPA if the student averages `expected` (within the selected scale) over `remaining` credits they supply.
    Read-only planning: actual grades stay fixed and nothing hypothetical is saved."""
    expected = checked_target(expected, policy=policy)
    remaining = checked_credits(remaining)
    current = academic_summary(courses, policy=policy)
    with localcontext() as context:
        context.prec = 50
        total = current["units"] + remaining
        projected = (current["points"] + expected * remaining) / total
    return {"current": current, "expected": expected, "remaining": remaining, "total": total,
            "projected": projected}


# Class of degree: the lowest CGPA for each class, highest class first. These defaults are a
# common Nigerian 5-point guide only. Each student can edit theirs, and their own university's
# handbook decides their actual class; nothing here decides graduation or classification rules.
CLASS_NAMES = ("First Class", "Second Class Upper", "Second Class Lower", "Third Class", "Pass")
DEFAULT_CLASS_BANDS = (Decimal("4.50"), Decimal("3.50"), Decimal("2.40"), Decimal("1.50"), Decimal("1.00"))


def checked_bands(values, *, policy=LEGACY_POLICY):
    """Five class minimums, highest class first: each from 0 to the scale's maximum with at most
    four decimal places, and each strictly lower than the class above it."""
    if not isinstance(values, (list, tuple)) or len(values) != len(CLASS_NAMES):
        raise ValueError("Enter a lowest CGPA for each of the five classes.")
    bands = tuple(checked_target(value, policy=policy) for value in values)
    if any(higher <= lower for higher, lower in zip(bands, bands[1:])):
        raise ValueError("Each class needs a lower minimum than the class above it.")
    return bands


def class_standing(cgpa, bands=DEFAULT_CLASS_BANDS, *, policy=LEGACY_POLICY):
    """Which band the actual CGPA falls in, and how far it is below the next band up.

    Uses the unrounded CGPA. Read-only: it describes the student's own bands and never
    decides a classification. `cgpa` is None when nothing is graded yet."""
    bands = checked_bands(bands, policy=policy)
    rows = [{"name": name, "low": low, "high": None if index == 0 else bands[index - 1]}
            for index, (name, low) in enumerate(zip(CLASS_NAMES, bands))]
    if cgpa is None:
        return {"bands": rows, "cgpa": None, "current": None, "next": None, "gap": None}
    cgpa = Decimal(cgpa)
    current = next((row for row in rows if cgpa >= row["low"]), None)
    if current is None:
        upward = rows[-1]
    else:
        index = rows.index(current)
        upward = rows[index - 1] if index else None
    with localcontext() as context:
        context.prec = 50
        gap = None if upward is None else upward["low"] - cgpa
    return {"bands": rows, "cgpa": cgpa, "current": current, "next": upward, "gap": gap}


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

