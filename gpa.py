def calculate_gpa(courses):

    if len(courses) == 0:
        print("\nYou have no courses.\n")
        return

    grade_points = {
        "A": 5,
        "B": 4,
        "C": 3,
        "D": 2,
        "E": 1,
        "F": 0
    }

    total_points = 0
    total_units = 0

    print("\n================================")
    print("          GPA CALCULATOR")
    print("================================")
    print("A = 5, B = 4, C = 3")
    print("D = 2, E = 1, F = 0")
    print()

    for number, course in enumerate(courses, start=1):

        course_name = course.get("name") or course.get("code") or f"Course {number}"

        if not str(course.get("code") or "").strip():
            print(f"Skipping {course_name}: the course code is missing.\n")
            continue

        credit_units = course.get("credit_units")
        if isinstance(credit_units, bool) or not isinstance(credit_units, (int, float)):
            print(f"Skipping {course_name}: credit units must be a number.\n")
            continue

        while True:
            grade = input(
                f"Grade for {course['code']} "
                f"({course['credit_units']} units, or Q to cancel): "
            ).strip().upper()

            if grade == "Q":
                print("\nGPA calculation cancelled.\n")
                return

            if grade in grade_points:
                break

            print(
                "Invalid grade. "
                "Please enter A, B, C, D, E, or F."
            )

        points = grade_points[grade]

        total_points += points * course["credit_units"]
        total_units += course["credit_units"]

    if total_units == 0:
        print("\nCannot calculate GPA because total credit units are zero.\n")
        return

    gpa = total_points / total_units

    print("\n================================")
    print("          GPA RESULT")
    print("================================")
    print(f"Total credit units: {total_units}")
    print(f"Total grade points: {total_points}")
    print(f"GPA: {gpa:.2f}")
    print("================================\n")
