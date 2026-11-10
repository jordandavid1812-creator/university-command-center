from storage import load_data

from courses import (
    add_course,
    list_courses,
    remove_course,
    edit_course
)

from assignments import (
    add_assignment,
    list_assignments,
    mark_assignment_complete,
    remove_assignment
)

from gpa import calculate_gpa
from gpa_predictor import predict_gpa


COURSES_FILE = "courses.json"
ASSIGNMENTS_FILE = "assignments.json"


courses = load_data(COURSES_FILE)
assignments = load_data(ASSIGNMENTS_FILE)


def show_menu():
    print("========================================")
    print("       UNIVERSITY COMMAND CENTER")
    print("========================================")
    print("COURSES")
    print("1. Add course")
    print("2. List courses")
    print("3. Remove course")
    print("4. Edit course")
    print("----------------------------------------")
    print("ASSIGNMENTS")
    print("5. Add assignment")
    print("6. List assignments")
    print("7. Mark assignment complete")
    print("8. Remove assignment")
    print("----------------------------------------")
    print("ACADEMIC")
    print("9. Calculate GPA")
    print("11. GPA Predictor")
    print("----------------------------------------")
    print("10. Exit")
    print("========================================")


while True:

    show_menu()

    choice = input("Choose an option: ").strip()

    if choice == "1":
        add_course(courses)

    elif choice == "2":
        list_courses(courses)

    elif choice == "3":
        remove_course(courses)

    elif choice == "4":
        edit_course(courses)

    elif choice == "5":
        add_assignment(assignments, courses)

    elif choice == "6":
        list_assignments(assignments)

    elif choice == "7":
        mark_assignment_complete(assignments)

    elif choice == "8":
        remove_assignment(assignments)

    elif choice == "9":
        calculate_gpa(courses)

    elif choice == "10":
        print("\nGoodbye!")
        break

    elif choice == "11":
        predict_gpa(courses)

    else:
        print(
            "\nInvalid choice. "
            "Please choose a number from 1 to 11.\n"
        )
