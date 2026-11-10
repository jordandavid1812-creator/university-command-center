import copy
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO

from academic_logic import academic_summary, predicted_summary, target_plan, validate_courses
from web_actions import course_change, remove_course_record, add_assignment_record, assignment_status


class TestAcademicLogic(unittest.TestCase):
    def setUp(self):
        self.courses = [
            {"name": "Computing", "code": "ONE", "credit_units": 3, "grade": "A", "semester": "First", "extra": "keep"},
            {"name": "Math", "code": "TWO", "credit_units": 2, "grade": "C", "semester": "First"},
            {"code": "THREE", "credit_units": 6, "grade": "E", "semester": "Second"},
            {"code": "FOUR", "credit_units": 3},
        ]

    def test_summary_is_weighted_and_ungraded_are_excluded(self):
        result = academic_summary(self.courses)
        self.assertEqual(result["points"], 27)
        self.assertEqual(result["units"], 11)
        self.assertEqual(result["graded"], 3)
        self.assertEqual(result["ungraded"], 1)
        self.assertEqual(result["gpa"], Decimal(27) / 11)
        self.assertEqual(result["semesters"][0]["gpa"], Decimal("4.2"))
        self.assertIsNone(result["semesters"][2]["gpa"])

    def test_validation_returns_warnings_without_printing(self):
        output = StringIO()
        with redirect_stdout(output):
            semesters, warnings = validate_courses([None, {}, self.courses[0], self.courses[0]])
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(warnings), 3)
        self.assertEqual(len(semesters["First"]), 1)

    def test_prediction_and_plan_never_mutate_records(self):
        before = copy.deepcopy(self.courses)
        result = predicted_summary(self.courses, {code: "F" for code in ("ONE", "TWO", "THREE", "FOUR")})
        self.assertEqual(result["gpa"], 0)
        self.assertEqual(result["units"], 14)
        target_plan(self.courses, 4, 10)
        self.assertEqual(before, self.courses)

    def test_prediction_requires_all_grades(self):
        for grades in [{}, {"ONE": []}]:
            with self.assertRaises(ValueError):
                predicted_summary(self.courses, grades)

    def test_planner_boundaries(self):
        for target, status in [(5, "achievable"), (0, "guaranteed")]:
            result = target_plan([{"code": "ONE", "credit_units": 0.1, "grade": "A"}], target, 0.3)
            self.assertEqual(result["status"], status)
        self.assertEqual(target_plan(self.courses, 5, 1)["status"], "impossible")

    def test_invalid_plan_inputs(self):
        for target, remaining in [(6, 5), (-1, 5), ("nan", 5), (4, 0), (4, -1), (4, "inf"), ("bad", 1), (4, "1e999999")]:
            with self.subTest(target=target, remaining=remaining), self.assertRaises(ValueError):
                target_plan(self.courses, target, remaining)

    def test_course_edit_preserves_extra_fields_and_does_not_mutate(self):
        before = copy.deepcopy(self.courses)
        result = course_change(self.courses, 0, "New name", "ONE", 4, "Second", "B")
        self.assertEqual(result[0]["extra"], "keep")
        self.assertEqual(result[0]["grade"], "B")
        self.assertEqual(self.courses, before)

    def test_invalid_course_inputs_and_duplicate_codes(self):
        for name, code, units, grade in [("", "NEW", 3, "A"), ("New", " one ", 3, "A"), ("New", "NEW", 0, "A"),
                                          ("New", "NEW", True, "A"), ("New", "NEW", 2.5, "A"), ("New", "NEW", 3, "X")]:
            with self.subTest(code=code, units=units), self.assertRaises(ValueError):
                course_change(self.courses, None, name, code, units, "", grade)

    def test_course_removal_protects_assignment_links(self):
        with self.assertRaises(ValueError):
            remove_course_record(self.courses, 0, [{"course_code": "ONE"}])
        self.assertEqual(len(remove_course_record(self.courses, 0, [])), 3)
        self.assertEqual(len(self.courses), 4)

    def test_assignment_validation_and_completion_preserve_records(self):
        for title, code, due in [("", "ONE", "2030-01-01"), ("Work", "MISSING", "2030-01-01"), ("Work", "ONE", "2030")]:
            with self.assertRaises(ValueError):
                add_assignment_record([], self.courses, title, code, due)
        added = add_assignment_record([], self.courses, "Work", "ONE", "2030-01-01")
        done = assignment_status(added, 0, True)
        self.assertTrue(done[0]["completed"])
        self.assertFalse(added[0]["completed"])
