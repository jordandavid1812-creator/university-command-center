import math

from gpa import GRADE_POINTS


def get_valid_semester_courses(courses):
    """Return normalized course details without changing the saved records."""
    semesters = {}
    seen_codes = set()
    for number, course in enumerate(courses, start=1):
        if not isinstance(course, dict):
            print(f"Skipping Course {number}: invalid course record.")
            continue

        code = course.get("code")
        if not isinstance(code, str) or not code.strip():
            print(f"Skipping Course {number}: missing or invalid course code.")
            continue
        code = code.strip().upper()
        units = course.get("credit_units")
        if (isinstance(units, bool) or not isinstance(units, (int, float))
                or units <= 0):
            print(f"Skipping {code}: credit units must be a positive number.")
            continue
        try:
            finite_units = math.isfinite(units)
        except OverflowError:
            finite_units = False
        if not finite_units:
            print(f"Skipping {code}: credit units are too large or not finite.")
            continue

        saved_grade = course.get("grade")
        grade = saved_grade.strip().upper() if isinstance(saved_grade, str) else saved_grade
        if grade is not None and grade != "":
            if not isinstance(grade, str) or grade not in GRADE_POINTS:
                print(f"Skipping {code}: invalid saved grade.")
                continue
        if code in seen_codes:
            print(f"Skipping duplicate course {code}: already included.")
            continue
        seen_codes.add(code)

        semester = course.get("semester")
        if not isinstance(semester, str) or not semester.strip():
            semester = "Unassigned"
        semesters.setdefault(semester, []).append((code, units, grade))

    return semesters


def show_academic_overview(courses):
    print("\nACADEMIC PERFORMANCE OVERVIEW")
    if not isinstance(courses, list):
        print("Course data must be a list. No overview is available.\n")
        return
    if not courses:
        print("You have no courses yet.\n")
        return

    semesters = get_valid_semester_courses(courses)

    total_points = 0
    total_units = 0
    completed = 0
    ungraded = 0
    comparison = []
    for semester, semester_courses in semesters.items():
        print(f"\n{semester}:")
        semester_points = 0
        semester_units = 0
        for code, units, grade in semester_courses:
            if grade is None or grade == "":
                print(f"  {code}: no saved grade (excluded from GPA)")
                ungraded += 1
                continue
            print(f"  {code}: saved grade {grade}, {units:g} credit units")
            semester_points += GRADE_POINTS[grade] * units
            semester_units += units
            completed += 1

        if semester_units:
            gpa = semester_points / semester_units
            print(f"  Semester GPA: {gpa:.2f}")
            bar = "#" * round(gpa * 4)
            comparison.append(f"{semester}: [{bar:<20}] {gpa:.2f}")
        else:
            print("  Semester GPA: N/A (no graded courses)")
            comparison.append(f"{semester}: N/A (no graded courses)")
        total_points += semester_points
        total_units += semester_units

    print(f"\nTotal completed courses (saved grades, including F): {completed}")
    print(f"Courses without saved grades: {ungraded}")
    print(f"Attempted credit units (graded courses only): {total_units:g}")
    if total_units:
        print(f"Cumulative GPA: {total_points / total_units:.2f}")
    else:
        print("Cumulative GPA: N/A (no graded courses)")
    print("\nSemester GPA comparison (# = approximately 0.25 GPA points):")
    print("Semesters stay in record order; this may not be chronological.")
    for line in comparison:
        print(line)
    print()
