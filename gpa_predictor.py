import math

from gpa import GRADE_POINTS


def predict_gpa(courses):
    if not courses:
        print("\nYou have no courses to predict a GPA for.\n")
        return

    valid_courses = []
    for number, course in enumerate(courses, start=1):
        if not isinstance(course, dict):
            print(f"Skipping Course {number}: the course record is invalid.")
            continue

        name = course.get("name") or course.get("code") or f"Course {number}"
        units = course.get("credit_units")
        if not str(course.get("code") or "").strip():
            print(f"Skipping {name}: the course code is missing.")
            continue
        if (isinstance(units, bool) or not isinstance(units, (int, float))
                or units <= 0 or not math.isfinite(units)):
            print(f"Skipping {name}: credit units must be a positive, finite number.")
            continue
        valid_courses.append(course)

    if not valid_courses:
        print("\nNo courses with valid credit units are available for prediction.\n")
        return

    # Keep hypothetical grades here, never in the actual course records.
    predicted_grades = {}
    print("\nGPA PREDICTOR")
    print("A = 5, B = 4, C = 3, D = 2, E = 1, F = 0")
    print("Predictions are temporary and do not change your saved grades.")

    while True:
        total_points = 0
        total_units = 0
        for number, course in enumerate(valid_courses):
            previous_grade = predicted_grades.get(number)
            hint = f", Enter to keep predicted {previous_grade}" if previous_grade else ""
            while True:
                grade = input(
                    f"Predicted grade for {course['code']} "
                    f"({course['credit_units']} units{hint}, Q to cancel): "
                ).strip().upper()
                if grade == "Q":
                    print("\nGPA prediction cancelled.\n")
                    return
                if grade == "" and previous_grade:
                    grade = previous_grade
                if grade in GRADE_POINTS:
                    break
                print("Invalid grade. Please enter A, B, C, D, E, or F.")

            predicted_grades[number] = grade
            total_points += GRADE_POINTS[grade] * course["credit_units"]
            total_units += course["credit_units"]

        print(f"\nTotal credit units: {total_units}")
        print(f"Predicted grade points: {total_points}")
        print(f"Predicted GPA: {total_points / total_units:.2f}\n")

        while True:
            choice = input("R to change predicted grades and recalculate, or Q to return to menu: ").strip().upper()
            if choice == "Q":
                return
            if choice == "R":
                break
            print("Please enter R or Q.")
