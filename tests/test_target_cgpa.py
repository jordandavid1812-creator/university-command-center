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

from target_cgpa import plan_target_cgpa


class TestTargetCGPA(unittest.TestCase):
    def setUp(self):
        self.courses = [
            {"code": "COS101", "credit_units": 3, "grade": "A"},
            {"code": "MAT101", "credit_units": 2, "grade": "C"},
        ]

    def plan(self, courses, answers):
        output = StringIO()
        with patch("builtins.input", side_effect=answers) as prompts:
            with redirect_stdout(output):
                plan_target_cgpa(courses)
        return output.getvalue(), prompts

    def test_normal_weighted_plan(self):
        output, _ = self.plan(self.courses, ["4", "5"])

        self.assertIn("Current CGPA: 4.20", output)
        self.assertIn("Current quality points: 21", output)
        self.assertIn("Completed attempted credits (saved grades, including F): 5", output)
        self.assertIn("Total credits at graduation (assumed): 10", output)
        self.assertIn("Required average grade point: 3.80", output)
        self.assertIn("mathematically achievable", output)

    def test_impossible_target(self):
        output, _ = self.plan([{"code": "ONE", "credit_units": 3, "grade": "F"}], ["4", "2"])

        self.assertIn("Current CGPA: 0.00", output)
        self.assertIn("Required average grade point: 10.00", output)
        self.assertIn("cannot be achieved", output)

    def test_exact_five_is_achievable(self):
        for current, remaining in [(3, "2"), (0.1, "0.3")]:
            with self.subTest(current=current):
                output, _ = self.plan(
                    [{"code": "ONE", "credit_units": current, "grade": "A"}],
                    ["5", remaining],
                )
                self.assertIn("Required average grade point: 5.00", output)
                self.assertIn("mathematically achievable", output)
                self.assertNotIn("cannot be achieved", output)

    def test_zero_target_and_zero_required_average(self):
        output, _ = self.plan([{"code": "ONE", "credit_units": 3, "grade": "F"}], ["0", "2"])

        self.assertIn("Required average grade point: 0.00", output)
        self.assertIn("already guaranteed", output)
        self.assertIn("all remaining credits are completed", output)

    def test_negative_required_average_is_guaranteed(self):
        output, _ = self.plan([{"code": "ONE", "credit_units": 3, "grade": "A"}], ["1", "2"])

        self.assertIn("Required average grade point: -5.00", output)
        self.assertIn("already guaranteed", output)
        self.assertIn("at least zero", output)

    def test_invalid_target_inputs_are_retried(self):
        invalid = ["", "text", "-1", "5.01", "nan", "inf", "-inf", "1e999"]
        output, prompts = self.plan(self.courses, invalid + ["4", "5"])

        self.assertEqual(prompts.call_count, len(invalid) + 2)
        self.assertIn("Please enter a number from 0.00 to 5.00", output)
        self.assertIn("finite number", output)
        self.assertIn("Required average grade point: 3.80", output)

    def test_invalid_remaining_inputs_are_retried(self):
        invalid = ["", "text", "-2", "0", "nan", "inf", "-inf", "1e999"]
        output, prompts = self.plan(self.courses, ["4"] + invalid + ["5"])

        self.assertEqual(prompts.call_count, len(invalid) + 2)
        self.assertIn("must be greater than zero", output)
        self.assertIn("Required average grade point: 3.80", output)

    def test_no_graded_courses_starts_at_zero(self):
        for courses in [[], [{"code": "ONE", "credit_units": 3, "predicted_grade": "A"}]]:
            with self.subTest(courses=courses):
                output, _ = self.plan(courses, ["3.5", "10"])
                self.assertIn("Current CGPA: N/A", output)
                self.assertIn("Required average grade point: 3.50", output)
                self.assertIn("Current quality points: 0", output)

    def test_overview_deduplication_rules_and_invalid_records(self):
        courses = [
            None,
            {"code": "BAD", "credit_units": "3", "grade": "A"},
            {"code": "BADGRADE", "credit_units": 3, "grade": "X"},
            {"code": "ONE", "credit_units": 3, "grade": " b ", "semester": "First"},
            {"code": " one ", "credit_units": 6, "grade": "F", "semester": "Second"},
            {"code": "UNFINISHED", "credit_units": 6},
            {"code": "UNFINISHED", "credit_units": 6, "grade": "A"},
        ]
        output, _ = self.plan(courses, ["4", "3"])

        self.assertIn("Skipping duplicate course ONE", output)
        self.assertIn("Skipping duplicate course UNFINISHED", output)
        self.assertIn("Skipping BAD:", output)
        self.assertIn("Current quality points: 12", output)
        self.assertIn("Current CGPA: 4.00", output)
        self.assertIn("Total credits at graduation (assumed): 6", output)
        self.assertIn("Required average grade point: 4.00", output)

    def test_invalid_top_level_data_does_not_prompt(self):
        for courses in [None, {}, "bad"]:
            with self.subTest(courses=courses):
                output, prompts = self.plan(courses, [])
                self.assertIn("Course data must be a list", output)
                prompts.assert_not_called()

    def test_cancel_either_prompt(self):
        for answers in [["q"], ["4", " Q "]]:
            with self.subTest(answers=answers):
                output, _ = self.plan(self.courses, answers)
                self.assertIn("CGPA planning cancelled", output)
                self.assertNotIn("Required average grade point:", output)

    def test_planning_is_read_only_and_ignores_predictions(self):
        courses = [{"code": "ONE", "credit_units": 3, "grade": "F", "predicted_grade": "A"}]
        original = copy.deepcopy(courses)
        with patch("builtins.open", side_effect=AssertionError("Unexpected file access")):
            output, _ = self.plan(courses, ["4", "2"])

        self.assertEqual(courses, original)
        self.assertIn("Current CGPA: 0.00", output)
        self.assertIn("Required average grade point: 10.00", output)

    def test_menu_after_prediction_keeps_student_json_unchanged(self):
        main = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as folder:
            courses = Path(folder) / "courses.json"
            assignments = Path(folder) / "assignments.json"
            original = json.dumps([{"code": "ONE", "credit_units": 3, "grade": "F"}]).encode()
            courses.write_bytes(original)
            assignments.write_bytes(b"[]")

            result = subprocess.run(
                [sys.executable, "-B", str(main)], cwd=folder,
                input="11\nA\nQ\n13\n4\n2\n12\n10\n",
                text=True, capture_output=True, check=True, timeout=10,
            )

            self.assertIn("13. Target CGPA Planner", result.stdout)
            self.assertIn("Predicted GPA: 5.00", result.stdout)
            self.assertIn("Required average grade point: 10.00", result.stdout)
            self.assertIn("Cumulative GPA: 0.00", result.stdout)
            self.assertIn("Goodbye!", result.stdout)
            self.assertEqual(courses.read_bytes(), original)
            self.assertEqual(assignments.read_bytes(), b"[]")


if __name__ == "__main__":
    unittest.main()
