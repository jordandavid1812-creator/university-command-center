"""Validate form edits and return new records; these functions never write files."""
from copy import deepcopy
from datetime import date

from academic_logic import checked_grade


def course_change(courses, index, name, code, units, semester, grade):
    if not name.strip() or not code.strip():
        raise ValueError("Course name and code are required.")
    code = code.strip().upper()
    if isinstance(units, bool) or not isinstance(units, (int, float)) or units not in range(1, 7):
        raise ValueError("Credit units must be a whole number from 1 to 6.")
    grade = checked_grade(grade)
    for number, course in enumerate(courses):
        if isinstance(course, dict) and number != index and str(course.get("code", "")).strip().upper() == code:
            raise ValueError("This course code already exists.")
    result = deepcopy(courses)
    course = {} if index is None else result[index]
    if not isinstance(course, dict):
        raise ValueError("This record cannot be edited as a course.")
    course.update(name=name.strip(), code=code, credit_units=int(units), semester=semester.strip() or "Unassigned")
    if grade:
        course["grade"] = grade
    else:
        course.pop("grade", None)
    if index is None:
        result.append(course)
    return result


def remove_course_record(courses, index, assignments):
    code = str(courses[index].get("code", "")).strip().upper()
    if any(isinstance(item, dict) and str(item.get("course_code", "")).strip().upper() == code for item in assignments):
        raise ValueError("Remove assignments linked to this course before removing the course.")
    result = deepcopy(courses)
    result.pop(index)
    return result


def add_assignment_record(assignments, courses, title, code, due):
    if not title.strip():
        raise ValueError("Assignment title is required.")
    if not any(isinstance(course, dict) and course.get("code") == code for course in courses):
        raise ValueError("Select an existing course.")
    try:
        if not isinstance(due, str) or date.fromisoformat(due).isoformat() != due:
            raise ValueError("Invalid date format")
    except (ValueError, TypeError):
        raise ValueError("Enter a valid due date in YYYY-MM-DD format.")
    return deepcopy(assignments) + [{"title": title.strip(), "course_code": code,
                                    "due_date": due, "completed": False}]


def assignment_status(assignments, index, completed):
    result = deepcopy(assignments)
    result[index]["completed"] = bool(completed)
    return result
