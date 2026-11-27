from storage import save_data


COURSES_FILE = "courses.json"


def add_course(courses):
    course_name = input("Enter course name: ").strip()
    course_code = input("Enter course code: ").strip().upper()
    credit_units = input("Enter credit units: ").strip()
    semester = input("Enter semester name (for example, 100L First): ").strip()

    if course_name == "":
        print("Course name cannot be empty.\n")
        return

    if course_code == "":
        print("Course code cannot be empty.\n")
        return

    if not credit_units.isdigit():
        print("Credit units must be a number.\n")
        return

    credit_units = int(credit_units)

    if credit_units < 1 or credit_units > 6:
        print("Credit units must be between 1 and 6.\n")
        return

    for course in courses:
        if course["code"] == course_code:
            print(f"Course code {course_code} already exists.\n")
            return

    course = {
        "name": course_name,
        "code": course_code,
        "credit_units": credit_units,
        "semester": semester or "Unassigned"
    }

    courses.append(course)

    save_data(COURSES_FILE, courses)

    print(f"\nYou added {course_name} ({course_code}).\n")


def list_courses(courses):
    if len(courses) == 0:
        print("\nYou have no courses yet.\n")
        return

    print("\nYour courses:")

    semesters = {}
    for number, course in enumerate(courses, start=1):
        semester = course.get("semester") or "Unassigned"
        semesters.setdefault(semester, []).append((number, course))

    for semester, semester_courses in semesters.items():
        print(f"\n{semester}:")
        for number, course in semester_courses:
            print(
                f"{number}. "
                f"{course['name']} "
                f"({course['code']}) - "
                f"{course['credit_units']} credit units"
            )

    print(f"\nTotal courses: {len(courses)}\n")


def remove_course(courses):
    if len(courses) == 0:
        print("\nYou have no courses to remove.\n")
        return

    list_courses(courses)

    choice = input(
        "Enter the number of the course to remove: "
    ).strip()

    if not choice.isdigit():
        print("Please enter a valid number.\n")
        return

    course_number = int(choice)

    if course_number < 1 or course_number > len(courses):
        print("That course number does not exist.\n")
        return

    removed_course = courses.pop(course_number - 1)

    save_data(COURSES_FILE, courses)

    print(f"\n{removed_course['name']} has been removed.\n")


def edit_course(courses):
    if len(courses) == 0:
        print("\nYou have no courses to edit.\n")
        return

    list_courses(courses)

    choice = input(
        "Enter the number of the course to edit: "
    ).strip()

    if not choice.isdigit():
        print("Please enter a valid number.\n")
        return

    course_number = int(choice)

    if course_number < 1 or course_number > len(courses):
        print("That course number does not exist.\n")
        return

    course = courses[course_number - 1]

    print("\nEnter the new information.")

    new_name = input("Enter new course name: ").strip()
    new_code = input("Enter new course code: ").strip().upper()
    new_credit_units = input("Enter new credit units: ").strip()
    current_semester = course.get("semester") or "Unassigned"
    new_semester = input(
        f"Enter new semester (Enter to keep {current_semester}): "
    ).strip()

    if new_name == "":
        print("Course name cannot be empty.\n")
        return

    if new_code == "":
        print("Course code cannot be empty.\n")
        return

    if not new_credit_units.isdigit():
        print("Credit units must be a number.\n")
        return

    new_credit_units = int(new_credit_units)

    if new_credit_units < 1 or new_credit_units > 6:
        print("Credit units must be between 1 and 6.\n")
        return

    for other_course in courses:
        if other_course != course and other_course["code"] == new_code:
            print(f"Course code {new_code} already exists.\n")
            return

    course["name"] = new_name
    course["code"] = new_code
    course["credit_units"] = new_credit_units
    course["semester"] = new_semester or current_semester

    save_data(COURSES_FILE, courses)

    print("\nCourse updated successfully.\n")
