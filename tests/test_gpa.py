import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from gpa import calculate_gpa


class TestGPA(unittest.TestCase):
    def setUp(self):
        self.courses = [
            {"code": "COS101", "credit_units": 3},
            {"code": "MAT101", "credit_units": 2},
        ]

    def run_calculator(self, courses, grades):
        output = StringIO()
        with patch("builtins.input", side_effect=grades) as grade_input:
            with redirect_stdout(output):
                calculate_gpa(courses)
        return output.getvalue(), grade_input.call_count

    def test_different_credit_weights(self):
        output, _ = self.run_calculator(self.courses, ["A", "C"])

        # (5 * 3 + 3 * 2) / (3 + 2) = 4.20
        self.assertIn("Total credit units: 5\n", output)
        self.assertIn("Total grade points: 21\n", output)
        self.assertIn("GPA: 4.20\n", output)

    def test_all_f_grades(self):
        output, _ = self.run_calculator(self.courses, ["F", "F"])

        self.assertIn("Total credit units: 5\n", output)
        self.assertIn("Total grade points: 0\n", output)
        self.assertIn("GPA: 0.00\n", output)

    def test_lowercase_grades(self):
        output, _ = self.run_calculator(self.courses, ["a", "c"])

        self.assertNotIn("Invalid grade.", output)
        self.assertIn("GPA: 4.20\n", output)

    def test_invalid_grades(self):
        output, prompt_count = self.run_calculator(
            self.courses, ["X", "", "A", "C"]
        )

        self.assertEqual(output.count("Invalid grade."), 2)
        self.assertEqual(prompt_count, 4)
        self.assertIn("GPA: 4.20\n", output)

    def test_no_courses(self):
        output, prompt_count = self.run_calculator([], [])

        self.assertIn("You have no courses.", output)
        self.assertEqual(prompt_count, 0)
        self.assertNotIn("GPA RESULT", output)


if __name__ == "__main__":
    unittest.main()
