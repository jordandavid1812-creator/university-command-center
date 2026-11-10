"""Local, single-user Streamlit interface. Run with streamlit run web_app.py."""
import os
from copy import deepcopy
from pathlib import Path

import streamlit as st

from academic_logic import GRADE_POINTS, academic_summary, predicted_summary, target_plan, validate_courses
from web_actions import course_change, remove_course_record, add_assignment_record, assignment_status
from web_data import DataError, read_records, write_records


st.set_page_config(page_title="University Command Center", page_icon="🎓", layout="wide")
DATA_DIR = Path(os.environ.get("UCC_DATA_DIR", Path(__file__).parent))
PAGES = ["Dashboard", "Courses", "Assignments", "Academic performance", "GPA Predictor", "Target CGPA Planner"]


def save_records(name, records):
    had_file = st.session_state.snapshots[name].original is not None
    try:
        write_records(DATA_DIR / name, records, st.session_state.snapshots[name])
    except DataError as error:
        st.error(str(error))
        return
    st.session_state.pop("snapshots", None)
    st.session_state.flash = "Your changes were saved." + (" A backup of the previous file was kept." if had_file else "")
    st.rerun()


def metrics(summary):
    columns = st.columns(3)
    columns[0].metric("Actual CGPA", f"{summary['gpa']:.2f}" if summary["gpa"] is not None else "Not graded")
    columns[1].metric("Graded courses", summary["graded"])
    columns[2].metric("Attempted credits", f"{summary['units']:g}")


def performance(summary):
    rows = [{"Semester": row["semester"], "GPA": float(row["gpa"]) if row["gpa"] is not None else None,
             "Graded courses": row["graded"], "Ungraded courses": row["ungraded"],
             "Attempted credits": float(row["units"])} for row in summary["semesters"]]
    if not rows:
        st.info("Add courses and save actual grades to see your academic performance.")
        return
    st.dataframe(rows, hide_index=True, width="stretch")
    chart = [row for row in rows if row["GPA"] is not None]
    if chart:
        st.bar_chart(chart, x="Semester", y="GPA", sort=False, color="#2563eb")
    st.caption("5-point scale · Semesters follow record order, which may not be chronological. Ungraded semesters have no GPA.")


def course_page(courses, assignments):
    st.caption("Manage your courses and actual grades. Predictions never appear here.")
    if not courses:
        st.info("No courses yet. Add your first course below; older records do not need to be migrated.")
    names = {str(record.get("code", "")).strip().upper(): str(record.get("name", ""))
             for record in reversed(courses) if isinstance(record, dict)}
    for semester, records in validate_courses(courses)[0].items():
        st.subheader(semester)
        st.dataframe([{"Code": code, "Name": names.get(code, ""), "Credits": units, "Actual grade": grade or "Ungraded"}
                      for code, units, grade in records], hide_index=True, width="stretch")
    options = [None] + [i for i, record in enumerate(courses) if isinstance(record, dict)]
    index = st.selectbox("Choose a course to edit, or add a new course", options,
                         format_func=lambda i: "Add new course" if i is None else f"{i + 1}. {courses[i].get('code', 'Missing code')}")
    current = {} if index is None else courses[index]
    with st.form(f"course_form_{index}"):
        name = st.text_input("Course name", value=str(current.get("name", "")))
        code = st.text_input("Course code", value=str(current.get("code", "")), disabled=index is not None)
        old_units = current.get("credit_units", 3)
        safe_units = old_units if type(old_units) is int and 1 <= old_units <= 6 else 3
        if current and old_units != safe_units:
            st.warning("This course has invalid credit units. Choose the correct units before saving.")
        units = st.number_input("Credit units", min_value=1, max_value=6, value=safe_units)
        semester = st.text_input("Semester", value=str(current.get("semester") or "Unassigned"), placeholder="100L First")
        choices = [""] + list(GRADE_POINTS)
        actual = str(current.get("grade") or "").strip().upper()
        grade = st.selectbox("Actual saved grade", choices, index=choices.index(actual) if actual in choices else 0,
                             format_func=lambda value: value or "Ungraded")
        if st.form_submit_button("Save course", type="primary"):
            try:
                result = course_change(courses, index, name, code, units, semester, grade)
                save_records("courses.json", result)
            except ValueError as error:
                st.error(str(error))
    if index is not None:
        st.caption("Course codes stay fixed to protect assignment links. Name, semester, credits, and actual grade can be edited.")
        confirm = st.checkbox("I confirm I want to remove this course", key=f"remove_course_{index}_{current.get('code')}")
        if st.button("Remove course", disabled=not confirm):
            try:
                save_records("courses.json", remove_course_record(courses, index, assignments))
            except ValueError as error:
                st.error(str(error))


def assignment_page(courses, assignments):
    codes = list(dict.fromkeys(record["code"] for record in courses
                              if isinstance(record, dict) and isinstance(record.get("code"), str) and record["code"].strip()))
    if codes:
        with st.form("add_assignment", clear_on_submit=True):
            st.subheader("Add an assignment")
            title = st.text_input("Assignment title")
            code = st.selectbox("Course", codes)
            due = st.date_input("Due date")
            if st.form_submit_button("Add assignment", type="primary"):
                try:
                    save_records("assignments.json", add_assignment_record(assignments, courses, title, code, due.isoformat()))
                except ValueError as error:
                    st.error(str(error))
    else:
        st.info("Add a course before adding an assignment.")
    if not assignments:
        st.info("No assignments yet. Your upcoming work will appear here.")
    for index, record in enumerate(assignments):
        if not isinstance(record, dict):
            st.warning(f"Assignment {index + 1} is invalid and has been left unchanged.")
            continue
        done = record.get("completed") is True
        with st.expander(f"{'Completed' if done else 'Pending'} · {record.get('title', 'Untitled assignment')}"):
            st.write(f"Course: {record.get('course_code', 'Unassigned')}")
            st.write(f"Due: {record.get('due_date', 'Not set')}")
            if st.button("Mark pending" if done else "Mark complete", key=f"status_{index}"):
                save_records("assignments.json", assignment_status(assignments, index, not done))
            confirm = st.checkbox("Confirm removal", key=f"remove_assignment_{index}_{hash(str(record))}")
            if st.button("Remove assignment", key=f"delete_{index}", disabled=not confirm):
                result = deepcopy(assignments)
                result.pop(index)
                save_records("assignments.json", result)


def prediction_page(courses):
    st.info("What-if results only. These grades are never saved and do not change your actual CGPA.")
    valid, _ = validate_courses(courses)
    if not valid:
        st.info("Add at least one course with valid credit units to try a prediction.")
        return
    with st.form("prediction"):
        grades = {}
        for semester, records in valid.items():
            st.subheader(semester)
            for code, units, actual in records:
                grades[code] = st.selectbox(f"Predicted grade for {code} ({units:g} credits)",
                                           [""] + list(GRADE_POINTS), key=f"predict_{code}",
                                           format_func=lambda value: value or "Choose a grade")
        if st.form_submit_button("Calculate prediction", type="primary"):
            try:
                result = predicted_summary(courses, grades)
                st.metric("Predicted GPA", f"{result['gpa']:.2f}")
                st.write(f"Total credit units: {result['units']:g} · Predicted grade points: {result['points']:g}")
                st.caption("Change any hypothetical grade and calculate again to compare scenarios.")
            except ValueError as error:
                st.error(str(error))


def planner_page(courses, summary):
    metrics(summary)
    st.caption("Current grades stay fixed. Enter all remaining credits, including ungraded courses. No graduation or repeat-course policy is assumed.")
    with st.form("target_plan"):
        target = st.number_input("Desired final CGPA", min_value=0.0, max_value=5.0, value=4.0, step=0.1)
        remaining = st.number_input("Remaining credit units", min_value=0.0, value=30.0, step=1.0)
        if st.form_submit_button("Calculate required average", type="primary"):
            try:
                result = target_plan(courses, target, remaining)
                st.metric("Required average grade point", f"{result['required']:.2f}")
                st.write(f"Assumed total credits at graduation: {result['total']:g}")
                if result["status"] == "impossible":
                    st.warning("This target cannot be achieved under these assumptions: the required average exceeds 5.00.")
                elif result["status"] == "guaranteed":
                    st.success("At least this target is guaranteed if all remaining credits are completed with grade points of at least zero.")
                else:
                    st.success("Mathematically achievable. Reach at least this credit-weighted average across remaining credits.")
                st.caption("Individual course weights and letter-grade choices may limit exact results. Displayed values are rounded; decisions use unrounded values. Nothing is saved.")
            except ValueError as error:
                st.error(str(error))


st.sidebar.title("University\nCommand Center")
st.sidebar.caption("Your studies, in one place")
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.divider()
st.sidebar.caption("Local, single-user workspace. Close the CLI before editing here.")
if st.sidebar.button("Reload data"):
    st.session_state.pop("snapshots", None)
    st.rerun()

st.title(page)
st.caption("Plan with confidence. Keep your actual results separate from what-if scenarios.")
try:
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = {name: read_records(DATA_DIR / name)
                                      for name in ("courses.json", "assignments.json")}
except DataError as error:
    st.error(str(error))
    st.info("Fix or restore the local file, then choose Reload data. Editing is disabled to protect your records.")
    st.stop()

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
courses = st.session_state.snapshots["courses.json"].records
assignments = st.session_state.snapshots["assignments.json"].records
summary = academic_summary(courses)
if summary["warnings"]:
    with st.expander("Some course records need attention"):
        for warning in summary["warnings"]:
            st.warning(warning)

if page == "Dashboard":
    st.subheader("Your academic snapshot")
    metrics(summary)
    left, right = st.columns(2)
    left.metric("Ungraded courses", summary["ungraded"])
    pending = sum(isinstance(item, dict) and item.get("completed") is not True for item in assignments)
    right.metric("Pending assignments", pending)
    st.caption("Completed means graded, including F. Attempted credits exclude ungraded courses.")
    st.subheader("Semester performance")
    performance(summary)
    st.subheader("Upcoming work")
    upcoming = [{"Assignment": str(item.get("title", "Untitled")), "Course": str(item.get("course_code", "")),
                 "Due": str(item.get("due_date", "Not set"))} for item in assignments
                if isinstance(item, dict) and item.get("completed") is not True]
    if upcoming:
        st.dataframe(upcoming, hide_index=True, width="stretch")
    else:
        st.info("No pending assignments. Add your next task on the Assignments page.")
elif page == "Courses":
    course_page(courses, assignments)
elif page == "Assignments":
    assignment_page(courses, assignments)
elif page == "Academic performance":
    metrics(summary)
    st.caption("Actual saved grades only. F counts as an attempt; ungraded courses do not count toward GPA.")
    performance(summary)
elif page == "GPA Predictor":
    prediction_page(courses)
elif page == "Target CGPA Planner":
    planner_page(courses, summary)
