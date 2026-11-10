import math
from decimal import Decimal

from academic_overview import get_valid_semester_courses
from gpa import GRADE_POINTS


def read_planner_number(prompt, minimum, maximum=None):
    while True:
        answer = input(prompt).strip()
        if answer.upper() == "Q":
            return None
        try:
            value = float(answer)
        except ValueError:
            print("Please enter a valid number, or Q to cancel.")
            continue
        if not math.isfinite(value):
            print("Please enter a finite number.")
        elif maximum is not None and not minimum <= value <= maximum:
            print(f"Please enter a number from {minimum:.2f} to {maximum:.2f}.")
        elif maximum is None and value <= minimum:
            print("Remaining credit units must be greater than zero.")
        else:
            return value


def plan_target_cgpa(courses):
    print("\nTARGET CGPA PLANNER")
    if not isinstance(courses, list):
        print("Course data must be a list. No plan is available.\n")
        return

    current_points = Decimal(0)
    current_units = Decimal(0)
    for semester_courses in get_valid_semester_courses(courses).values():
        for code, units, grade in semester_courses:
            if grade is not None and grade != "":
                units = Decimal(str(units))
                current_points += GRADE_POINTS[grade] * units
                current_units += units

    print(f"Completed attempted credits (saved grades, including F): {current_units:g}")
    print(f"Current quality points: {current_points:g}")
    if current_units:
        print(f"Current CGPA: {current_points / current_units:.2f}")
    else:
        print("Current CGPA: N/A (no valid saved grades; starting with zero credits)")
    print("This plan uses actual saved grades only; ungraded courses are excluded.")
    print("Enter all remaining credits yourself, including any ungraded courses.")
    print("Assumes current grades stay fixed and all remaining credits receive 0–5 points.")
    print("This is a mathematical estimate, not a university graduation or repeat-course policy.")

    target = read_planner_number("Desired final CGPA (0.00–5.00, Q to cancel): ", 0, 5)
    if target is None:
        print("CGPA planning cancelled.\n")
        return
    remaining = read_planner_number("Remaining credit units (greater than zero, Q to cancel): ", 0)
    if remaining is None:
        print("CGPA planning cancelled.\n")
        return

    # Decimal arithmetic avoids float errors at the exact 0 and 5 boundaries.
    target = Decimal(str(target))
    remaining = Decimal(str(remaining))
    graduation_units = current_units + remaining
    required_average = (target * graduation_units - current_points) / remaining
    if not graduation_units.is_finite() or not required_average.is_finite():
        print("These credit values are too large or too small to calculate safely.\n")
        return

    print(f"\nTarget CGPA: {target:.2f}")
    print(f"Total credits at graduation (assumed): {graduation_units:g}")
    print(f"Required average grade point: {required_average:.2f}")
    if required_average > max(GRADE_POINTS.values()):
        print("The target cannot be achieved under these assumptions: the required average exceeds 5.00.")
    elif required_average <= 0:
        print("At least the target is already guaranteed if all remaining credits are completed")
        print("and receive grade points of at least zero. No negative grade points are needed.")
    else:
        print("The target is mathematically achievable within the 0–5 scale.")
        print("Reach at least this average across remaining credits to meet or exceed the target.")
        print("Individual course weights and available letter grades may limit exact results.")
    print()
