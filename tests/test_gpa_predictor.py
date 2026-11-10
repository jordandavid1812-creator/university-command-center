import copy
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from gpa_predictor import predict_gpa


class TestGPAPredictor(unittest.TestCase):
    def setUp(self):
        self.courses = [
            {"code": "COS101", "credit_units": 3, "grade": "F"},
            {"code": "MAT101", "credit_units": 2},
        ]

    def run_predictor(self, courses, answers):
        output = StringIO()
        with patch("builtins.input", side_effect=answers) as prompts:
            with redirect_stdout(output):
                predict_gpa(courses)
        return output.getvalue(), prompts

    def test_weighted_prediction_does_not_change_actual_grades(self):
        original = copy.deepcopy(self.courses)
        # No file operations should be needed at all during prediction.
        with patch("builtins.open", side_effect=AssertionError("Unexpected file access")):
            output, _ = self.run_predictor(self.courses, ["A", "C", "Q"])

        self.assertIn("Total credit units: 5\n", output)
        self.assertIn("Predicted grade points: 21\n", output)
        self.assertIn("Predicted GPA: 4.20\n", output)
        self.assertEqual(self.courses, original)

    def test_change_prediction_and_keep_another_grade(self):
        output, prompts = self.run_predictor(
            self.courses, ["A", "C", "r", "b", "", "q"]
        )

        self.assertIn("Predicted GPA: 4.20\n", output)
        self.assertIn("Predicted GPA: 3.60\n", output)
        self.assertIn("Predicted grade points: 18\n", output)
        self.assertIn("Enter to keep predicted C", prompts.call_args_list[4].args[0])

    def test_all_f_grades(self):
        output, _ = self.run_predictor(self.courses, ["F", "F", "Q"])

        self.assertIn("Predicted grade points: 0\n", output)
        self.assertIn("Predicted GPA: 0.00\n", output)

    def test_invalid_input_is_retried_and_lowercase_works(self):
        output, _ = self.run_predictor(self.courses, ["X", "", "a", "c", "bad", "q"])

        self.assertEqual(output.count("Invalid grade."), 2)
        self.assertIn("Please enter R or Q.", output)
        self.assertIn("Predicted GPA: 4.20\n", output)

    def test_cancel_during_grade_entry_preserves_courses(self):
        original = copy.deepcopy(self.courses)
        output, _ = self.run_predictor(self.courses, ["B", "q"])

        self.assertIn("GPA prediction cancelled.", output)
        self.assertNotIn("Predicted GPA:", output)
        self.assertEqual(self.courses, original)

    def test_no_courses(self):
        output, prompts = self.run_predictor([], [])

        self.assertIn("You have no courses", output)
        prompts.assert_not_called()

    def test_invalid_credit_units_are_skipped(self):
        for units in [None, "3", True, 0, -2, float("nan"), float("inf")]:
            with self.subTest(units=units):
                courses = [{"code": "BAD", "credit_units": units}, self.courses[0]]
                output, prompts = self.run_predictor(courses, ["B", "Q"])

                self.assertIn("Skipping BAD:", output)
                self.assertIn("Total credit units: 3\n", output)
                self.assertIn("Predicted GPA: 4.00\n", output)
                self.assertEqual(prompts.call_count, 2)

    def test_missing_units_codes_and_invalid_records(self):
        courses = [{"code": "MISSING"}, {"name": "No Code", "credit_units": 3}, None]
        output, prompts = self.run_predictor(courses, [])

        self.assertIn("Skipping MISSING:", output)
        self.assertIn("Skipping No Code:", output)
        self.assertIn("Skipping Course 3:", output)
        self.assertIn("No courses with valid credit units", output)
        prompts.assert_not_called()

    def test_menu_prediction_preserves_json_and_other_options(self):
        main = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as folder:
            courses_file = Path(folder) / "courses.json"
            assignments_file = Path(folder) / "assignments.json"
            original = json.dumps(self.courses).encode()
            courses_file.write_bytes(original)
            assignments_file.write_bytes(b"[]")

            result = subprocess.run(
                [sys.executable, "-B", str(main)], cwd=folder,
                input="11\nA\nC\nR\nB\n\nQ\n6\n10\n",
                text=True, capture_output=True, check=True, timeout=10,
            )

            self.assertIn("11. GPA Predictor", result.stdout)
            self.assertIn("9. Calculate GPA", result.stdout)
            self.assertIn("Predicted GPA: 3.60", result.stdout)
            self.assertIn("You have no assignments.", result.stdout)
            self.assertIn("Goodbye!", result.stdout)
            self.assertEqual(courses_file.read_bytes(), original)
            self.assertEqual(assignments_file.read_bytes(), b"[]")


if __name__ == "__main__":
    unittest.main()
