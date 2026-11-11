from storage import save_data
from decimal import Decimal, localcontext
from academic_logic import GRADE_POINTS, checked_credits, weighted_gpa


def calculate_gpa(courses):

    if not isinstance(courses, list):
        print("\nCourse data must be a list.\n")
        return
    if len(courses) == 0:
        print("\nYou have no courses.\n")
        return

    grade_points = GRADE_POINTS

    total_points = Decimal(0)
    total_units = Decimal(0)
    entered_grades = []
    semester_totals = {}
    seen_codes = set()

    print("\n================================")
    print("          GPA CALCULATOR")
    print("================================")
    print("A = 5, B = 4, C = 3")
    print("D = 2, E = 1, F = 0")
    print()

    for number, course in enumerate(courses, start=1):

        if not isinstance(course, dict):
            print(f"Skipping Course {number}: invalid course record.\n")
            continue

        course_name = course.get("name") or course.get("code") or f"Course {number}"

        if not isinstance(course.get("code"), str) or not course["code"].strip():
            print(f"Skipping {course_name}: the course code is missing.\n")
            continue

        credit_units = course.get("credit_units")
        if isinstance(credit_units, bool) or not isinstance(credit_units, (int, float)):
            print(f"Skipping {course_name}: credit units must be a number.\n")
            continue
        try:
            units = checked_credits(credit_units, allow_zero=True)
        except ValueError as error:
            print(f"Skipping {course_name}: {error}\n")
            continue
        code = course["code"].strip().upper()
        if code in seen_codes:
            print(f"Skipping duplicate course {code}: already included.\n")
            continue
        seen_codes.add(code)

        saved_grade = str(course.get("grade", "")).strip().upper()
        saved_hint = ""
        if saved_grade in grade_points:
            saved_hint = f"saved grade: {saved_grade}, Enter to keep, "

        while True:
            grade = input(
                f"Grade for {course['code']} "
                f"({course['credit_units']} units, {saved_hint}or Q to cancel): "
            ).strip().upper()

            if grade == "Q":
                print("\nGPA calculation cancelled.\n")
                return

            if grade == "" and saved_grade in grade_points:
                grade = saved_grade

            if grade in grade_points:
                break

            print(
                "Invalid grade. "
                "Please enter A, B, C, D, E, or F."
            )

        points = grade_points[grade]
        entered_grades.append((course, grade))

        semester = course.get("semester") or "Unassigned"
        if not isinstance(semester, str):
            semester = "Unassigned"
        totals = semester_totals.setdefault(semester, {"points": 0, "units": 0})
        with localcontext() as context:
            context.prec = 50
            total_points += points * units
            total_units += units
            totals["points"] += points * units
            totals["units"] += units

    if total_units == 0:
        print("\nCannot calculate GPA because total credit units are zero.\n")
        return

    gpa = weighted_gpa(total_points, total_units)

    for course, grade in entered_grades:
        course["grade"] = grade
    save_data("courses.json", courses)

    print("\n================================")
    print("          GPA RESULT")
    print("================================")
    for semester, totals in semester_totals.items():
        if totals["units"] == 0:
            print(f"{semester}: cannot calculate GPA because credit units are zero.")
        else:
            semester_gpa = weighted_gpa(totals["points"], totals["units"])
            print(f"{semester} GPA: {semester_gpa:.2f}")
    print()
    print(f"Total credit units: {total_units}")
    print(f"Total grade points: {total_points}")
    print(f"Cumulative GPA: {gpa:.2f}")
    print("================================\n")
