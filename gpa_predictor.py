from academic_logic import GRADE_POINTS, validate_courses, predicted_summary


def predict_gpa(courses):
    if not isinstance(courses, list):
        print("\nCourse data must be a list.\n")
        return
    if not courses:
        print("\nYou have no courses to predict a GPA for.\n")
        return

    semesters, warnings = validate_courses(courses, check_saved_grades=False)
    for warning in warnings:
        print(warning)
    valid_courses = [{"code": code, "credit_units": units}
                     for records in semesters.values() for code, units, actual in records]

    if not valid_courses:
        print("\nNo courses with valid credit units are available for prediction.\n")
        return

    # Keep hypothetical grades here, never in the actual course records.
    predicted_grades = {}
    print("\nGPA PREDICTOR")
    print("A = 5, B = 4, C = 3, D = 2, E = 1, F = 0")
    print("Predictions are temporary and do not change your saved grades.")

    while True:
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
        grades = {course["code"]: predicted_grades[number] for number, course in enumerate(valid_courses)}
        result = predicted_summary(valid_courses, grades)
        print(f"\nTotal credit units: {result['units']:g}")
        print(f"Predicted grade points: {result['points']:g}")
        print(f"Predicted GPA: {result['gpa']:.2f}\n")

        while True:
            choice = input("R to change predicted grades and recalculate, or Q to return to menu: ").strip().upper()
            if choice == "Q":
                return
            if choice == "R":
                break
            print("Please enter R or Q.")
