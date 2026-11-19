"""The 4-point scale used by the website's grade-scale choice: A=4, B=3, C=2, D=1, F=0 and no E.
Class bands follow the chosen scale's maximum; the 5-point defaults are unchanged."""
import unittest
from decimal import Decimal
from academic_logic import (DEFAULT_CLASS_BANDS, academic_summary, checked_bands, checked_grade, class_standing,
                            target_plan)
from grading_policy import FOUR_POINT_POLICY, LEGACY_POLICY, SCALES

FOUR = FOUR_POINT_POLICY


class FourPointScaleTests(unittest.TestCase):
    def test_letters_and_points(self):
        self.assertEqual(dict(FOUR.grade_points), {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0})
        self.assertEqual(FOUR.maximum, 4)
        self.assertEqual(SCALES, {"five": LEGACY_POLICY, "four": FOUR})
        with self.assertRaises(ValueError):
            checked_grade("E", policy=FOUR)

    def test_saved_e_is_skipped_with_a_warning_not_counted_as_zero(self):
        courses = [{"code": "ONE", "credit_units": 3, "grade": "B", "semester": "S1"},
                   {"code": "TWO", "credit_units": 3, "grade": "E", "semester": "S1"}]
        result = academic_summary(courses, policy=FOUR)
        self.assertEqual((result["gpa"], result["units"]), (3, 3))
        self.assertEqual(result["warnings"], ["Skipping TWO: invalid saved grade."])

    def test_bands_follow_the_scale(self):
        bands = ("3.5", "3.0", "2.4", "1.5", "1.0")
        self.assertEqual(checked_bands(bands, policy=FOUR)[0], Decimal("3.5"))
        with self.assertRaises(ValueError):
            checked_bands(("4.5",) + bands[1:], policy=FOUR)
        self.assertEqual(checked_bands(DEFAULT_CLASS_BANDS), DEFAULT_CLASS_BANDS)  # 5-point unchanged
        standing = class_standing(Decimal("3.2"), bands, policy=FOUR)
        self.assertEqual(standing["current"]["name"], "Second Class Upper")
        with self.assertRaises(ValueError):
            class_standing(Decimal("3.2"), DEFAULT_CLASS_BANDS, policy=FOUR)  # 4.50 is above 4

    def test_planner_ceiling(self):
        plan = target_plan([{"code": "ONE", "credit_units": 3, "grade": "A", "semester": "S1"}], 4, 3, policy=FOUR)
        self.assertEqual((plan["required"], plan["status"]), (4, "achievable"))
        with self.assertRaises(ValueError):
            target_plan([], "4.5", 3, policy=FOUR)


if __name__ == "__main__":
    unittest.main()
