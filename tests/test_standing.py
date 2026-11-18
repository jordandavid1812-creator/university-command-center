"""Know where you stand (part A): the CGPA breakdown and the graduation projection.

Both reuse validate_courses, GRADE_POINTS and the shared input checks, and must agree exactly
with academic_summary.
"""
import unittest
from decimal import Decimal, localcontext

from academic_logic import academic_summary, course_breakdown, projected_cgpa

COURSES = [
    {"code": "MTH101", "credit_units": 3, "grade": "A", "semester": "First"},
    {"code": "GST121", "credit_units": 2, "grade": "C", "semester": "First"},
    {"code": "PHY101", "credit_units": 4, "grade": "F", "semester": "First"},
    {"code": "CSC102", "credit_units": 3, "grade": None, "semester": "Second"},
    {"code": "CHM102", "credit_units": Decimal("2.5"), "grade": "B", "semester": "Second"},
    {"code": "mth101", "credit_units": 3, "grade": "E", "semester": "Second"},  # duplicate code: skipped
]


class BreakdownTests(unittest.TestCase):
    def test_every_course_shows_its_working_and_totals_match_the_summary(self):
        breakdown = course_breakdown(COURSES)
        summary = academic_summary(COURSES)
        first, second = breakdown["semesters"]
        self.assertEqual([(c["code"], c["grade_points"], c["quality_points"]) for c in first["courses"]],
                         [("MTH101", 5, Decimal(15)), ("GST121", 3, Decimal(6)), ("PHY101", 0, Decimal(0))])
        self.assertEqual((first["points"], first["units"], first["gpa"]), (Decimal(21), Decimal(9), Decimal(21) / 9))
        # Ungraded courses are listed but count towards nothing; F counts its credits.
        self.assertEqual([(c["code"], c["quality_points"]) for c in second["courses"]],
                         [("CSC102", None), ("CHM102", Decimal("10.0"))])
        self.assertEqual((second["units"], second["gpa"]), (Decimal("2.5"), Decimal(4)))
        self.assertEqual((breakdown["points"], breakdown["units"], breakdown["gpa"]),
                         (summary["points"], summary["units"], summary["gpa"]))
        self.assertEqual([row["gpa"] for row in breakdown["semesters"]], [row["gpa"] for row in summary["semesters"]])
        self.assertIn("Skipping duplicate course MTH101: already included.", breakdown["warnings"])

    def test_no_graded_courses_means_no_gpa(self):
        breakdown = course_breakdown([{"code": "X1", "credit_units": 3, "grade": None, "semester": "S"}])
        self.assertIsNone(breakdown["gpa"])
        self.assertIsNone(breakdown["semesters"][0]["gpa"])


class ProjectionTests(unittest.TestCase):
    def test_projection_weights_the_expected_average_by_remaining_credits(self):
        result = projected_cgpa(COURSES, "4.5", "60")
        # Current: 31 points over 11.5 credits. 31 + 4.5 x 60 = 301 over 71.5.
        with localcontext() as context:
            context.prec = 50  # the helper works at 50 digits, like target_plan
            self.assertEqual(result["projected"], Decimal(301) / Decimal("71.5"))
        self.assertEqual(result["total"], Decimal("71.5"))
        self.assertEqual(result["current"]["points"], Decimal(31))

    def test_with_no_grades_yet_the_projection_is_the_expected_average(self):
        self.assertEqual(projected_cgpa([], "3.75", "120")["projected"], Decimal("3.75"))

    def test_inputs_use_the_shared_checks(self):
        for expected, remaining in (("5.1", "10"), ("-1", "10"), ("4.12345", "10"), ("4", "0"), ("4", "abc"),
                                    ("4", "1.00001"), (True, "10")):
            with self.subTest(expected=expected, remaining=remaining), self.assertRaises(ValueError):
                projected_cgpa(COURSES, expected, remaining)


if __name__ == "__main__":
    unittest.main()
