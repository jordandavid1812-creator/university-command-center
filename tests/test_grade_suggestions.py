"""Grade suggestions (owner's choice): one letter per ungraded course reaching a target CGPA,
spread as evenly as possible. Read-only planning with exact Decimals. Synthetic courses only."""
from copy import deepcopy
from decimal import Decimal
import unittest

from academic_logic import academic_summary, grade_suggestions
from grading_policy import FOUR_POINT_POLICY, LEGACY_POLICY

COURSES = [
    {"code": "SYN101", "credit_units": 3, "grade": "B", "semester": "First"},
    {"code": "SYN102", "credit_units": 2, "grade": "A", "semester": "First"},
    {"code": "SYN201", "credit_units": 3, "grade": None, "semester": "Second"},
    {"code": "SYN202", "credit_units": 2, "grade": "", "semester": "Second"},
    {"code": "SYN203", "credit_units": 4, "grade": None, "semester": "Second"},
]


def grades(result):
    return {course["code"]: course["grade"] for course in result["courses"]}


class GradeSuggestionTests(unittest.TestCase):
    def test_reaches_the_target_with_two_neighbouring_grades_biggest_courses_first(self):
        result = grade_suggestions(COURSES, "4.5")
        self.assertEqual(result["status"], "achievable")
        self.assertEqual(grades(result), {"SYN201": "A", "SYN202": "B", "SYN203": "A"})
        self.assertGreaterEqual(result["projected"], Decimal("4.5"))
        self.assertEqual(result["projected"], academic_summary([dict(c, grade=grades(result).get(c["code"], c["grade"])) for c in COURSES])["gpa"])
        self.assertEqual(round(result["projected"], 4), Decimal("4.6429"))

    def test_suggested_grades_really_give_the_projected_cgpa(self):
        for target in ("1.5", "2.4", "3", "3.5", "4", "4.5", "4.7"):
            with self.subTest(target=target):
                result = grade_suggestions(COURSES, target)
                filled = [dict(course, grade=grades(result).get(course["code"], course["grade"])) for course in COURSES]
                summary = academic_summary(filled)
                self.assertEqual(summary["gpa"], result["projected"])
                if result["status"] == "achievable":
                    self.assertGreaterEqual(result["projected"], Decimal(target))
                    used = sorted({LEGACY_POLICY.grade_points[g] for g in grades(result).values()})
                    self.assertLessEqual(used[-1] - used[0], 1)  # at most two neighbouring grades

    def test_already_safe_and_out_of_reach(self):
        safe = grade_suggestions(COURSES, "1")
        self.assertEqual(safe["status"], "guaranteed")
        impossible = grade_suggestions(COURSES, "4.9")
        self.assertEqual(impossible["status"], "impossible")
        self.assertEqual(set(grades(impossible).values()), {"A"})
        self.assertLess(impossible["projected"], Decimal("4.9"))

    def test_no_ungraded_courses(self):
        graded = [course for course in COURSES if course["grade"]]
        result = grade_suggestions(graded, "4")
        self.assertEqual((result["status"], result["courses"], result["projected"]), ("no_courses", [], None))

    def test_four_point_scale_has_no_e(self):
        result = grade_suggestions(COURSES, "3.5", policy=FOUR_POINT_POLICY)
        self.assertEqual(result["status"], "achievable")
        self.assertNotIn("E", grades(result).values())
        self.assertGreaterEqual(result["projected"], Decimal("3.5"))
        with self.assertRaises(ValueError):
            grade_suggestions(COURSES, "4.5", policy=FOUR_POINT_POLICY)  # above the 4-point maximum

    def test_exact_decimal_credits_and_inputs_are_not_changed(self):
        courses = deepcopy(COURSES) + [{"code": "SYN204", "credit_units": Decimal("1.5"), "grade": None, "semester": "Second"}]
        before = deepcopy(courses)
        result = grade_suggestions(courses, "4.25")
        self.assertEqual(courses, before)
        self.assertEqual(result["remaining"], Decimal("10.5"))
        self.assertTrue(all(isinstance(course["units"], Decimal) for course in result["courses"]))

    def test_invalid_records_and_targets_follow_the_shared_rules(self):
        messy = COURSES + [{"code": "SYN201", "credit_units": 9, "grade": None}, {"code": "", "credit_units": 3}]
        result = grade_suggestions(messy, "4")
        self.assertEqual(len(result["courses"]), 3)  # duplicate code and missing code skipped
        self.assertTrue(result["warnings"])
        for bad in ("5.1", "-1", "abc", "4.12345"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                grade_suggestions(COURSES, bad)
        with self.assertRaises(ValueError):
            grade_suggestions(COURSES, "4", policy=None)


if __name__ == "__main__":
    unittest.main()
