from academic_logic import academic_summary, validate_courses


def get_valid_semester_courses(courses):
    semesters, warnings = validate_courses(courses)
    for message in warnings:
        print(message)
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

    summary = academic_summary(courses)
    comparison = []
    for (semester, semester_courses), row in zip(semesters.items(), summary["semesters"]):
        print(f"\n{semester}:")
        for code, units, grade in semester_courses:
            if grade is None or grade == "":
                print(f"  {code}: no saved grade (excluded from GPA)")
                continue
            print(f"  {code}: saved grade {grade}, {units:g} credit units")

        if row["gpa"] is not None:
            gpa = row["gpa"]
            print(f"  Semester GPA: {gpa:.2f}")
            bar = "#" * round(gpa * 4)
            comparison.append(f"{semester}: [{bar:<20}] {gpa:.2f}")
        else:
            print("  Semester GPA: N/A (no graded courses)")
            comparison.append(f"{semester}: N/A (no graded courses)")

    print(f"\nTotal completed courses (saved grades, including F): {summary['graded']}")
    print(f"Courses without saved grades: {summary['ungraded']}")
    print(f"Attempted credit units (graded courses only): {summary['units']:g}")
    if summary["gpa"] is not None:
        print(f"Cumulative GPA: {summary['gpa']:.2f}")
    else:
        print("Cumulative GPA: N/A (no graded courses)")
    print("\nSemester GPA comparison (# = approximately 0.25 GPA points):")
    print("Semesters stay in record order; this may not be chronological.")
    for line in comparison:
        print(line)
    print()
