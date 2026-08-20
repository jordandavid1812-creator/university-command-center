from storage import save_data


ASSIGNMENTS_FILE = "assignments.json"


def add_assignment(assignments, courses):
    if len(courses) == 0:
        print("\nAdd a course before adding an assignment.\n")
        return

    title = input("Enter assignment title: ").strip()
    course_code = input("Enter course code: ").strip().upper()
    due_date = input("Enter due date (YYYY-MM-DD): ").strip()

    if title == "":
        print("Assignment title cannot be empty.\n")
        return

    if course_code == "":
        print("Course code cannot be empty.\n")
        return

    course_exists = False

    for course in courses:
        if course["code"] == course_code:
            course_exists = True
            break

    if not course_exists:
        print(f"Course {course_code} does not exist.\n")
        return

    if due_date == "":
        print("Due date cannot be empty.\n")
        return

    assignment = {
        "title": title,
        "course_code": course_code,
        "due_date": due_date,
        "completed": False
    }

    assignments.append(assignment)

    save_data(ASSIGNMENTS_FILE, assignments)

    print(f"\nAssignment '{title}' added successfully.\n")


def list_assignments(assignments):
    if len(assignments) == 0:
        print("\nYou have no assignments.\n")
        return

    print("\nYour assignments:")

    for number, assignment in enumerate(assignments, start=1):

        if assignment["completed"]:
            status = "Completed"
        else:
            status = "Pending"

        print(
            f"{number}. "
            f"{assignment['title']} | "
            f"{assignment['course_code']} | "
            f"Due: {assignment['due_date']} | "
            f"{status}"
        )

    print(f"\nTotal assignments: {len(assignments)}\n")


def mark_assignment_complete(assignments):
    if len(assignments) == 0:
        print("\nYou have no assignments.\n")
        return

    list_assignments(assignments)

    choice = input(
        "Enter the number of the assignment to mark complete: "
    ).strip()

    if not choice.isdigit():
        print("Please enter a valid number.\n")
        return

    assignment_number = int(choice)

    if assignment_number < 1 or assignment_number > len(assignments):
        print("That assignment number does not exist.\n")
        return

    assignment = assignments[assignment_number - 1]

    assignment["completed"] = True

    save_data(ASSIGNMENTS_FILE, assignments)

    print(f"\n'{assignment['title']}' marked as completed.\n")


def remove_assignment(assignments):
    if len(assignments) == 0:
        print("\nYou have no assignments to remove.\n")
        return

    list_assignments(assignments)

    choice = input(
        "Enter the number of the assignment to remove: "
    ).strip()

    if not choice.isdigit():
        print("Please enter a valid number.\n")
        return

    assignment_number = int(choice)

    if assignment_number < 1 or assignment_number > len(assignments):
        print("That assignment number does not exist.\n")
        return

    removed_assignment = assignments.pop(assignment_number - 1)

    save_data(ASSIGNMENTS_FILE, assignments)

    print(
        f"\n'{removed_assignment['title']}' "
        "has been removed.\n"
    )