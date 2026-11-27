import unittest
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from gpa import calculate_gpa
from storage import load_data, save_data


class TestGPA(unittest.TestCase):
    def setUp(self):
        save_patch = patch("gpa.save_data")
        save_patch.start()
        self.addCleanup(save_patch.stop)
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

    def test_two_semesters_use_credit_weights(self):
        courses = [
            {"code": "COS101", "credit_units": 3, "semester": "100L First"},
            {"code": "MAT101", "credit_units": 2, "semester": "100L First"},
            {"code": "COS102", "credit_units": 6, "semester": "100L Second"},
        ]

        output, _ = self.run_calculator(courses, ["A", "C", "E"])

        self.assertIn("100L First GPA: 4.20\n", output)
        self.assertIn("100L Second GPA: 1.00\n", output)
        # All course points / all units = (21 + 6) / (5 + 6).
        self.assertIn("Cumulative GPA: 2.45\n", output)
        self.assertLess(output.index("100L Second GPA:"),
                        output.index("Cumulative GPA:"))

    def test_courses_without_semesters_are_unassigned(self):
        output, _ = self.run_calculator(self.courses, ["A", "C"])

        self.assertIn("Unassigned GPA: 4.20\n", output)
        self.assertIn("Cumulative GPA: 4.20\n", output)

    def test_invalid_courses_do_not_affect_semester_totals(self):
        courses = [
            {"name": "Missing Code", "credit_units": 6, "semester": "Bad"},
            {"code": "BAD101", "credit_units": "3", "semester": "Bad"},
            {"code": "COS101", "credit_units": 3, "semester": "100L First"},
        ]

        output, prompt_count = self.run_calculator(courses, ["B"])

        self.assertEqual(prompt_count, 1)
        self.assertIn("Skipping Missing Code:", output)
        self.assertIn("Skipping BAD101:", output)
        self.assertNotIn("Bad GPA:", output)
        self.assertIn("100L First GPA: 4.00\n", output)
        self.assertIn("Total credit units: 3\n", output)
        self.assertIn("Cumulative GPA: 4.00\n", output)

    def test_zero_unit_semester_does_not_crash(self):
        courses = [
            {"code": "ZERO", "credit_units": 0, "semester": "Empty"},
            {"code": "COS101", "credit_units": 3, "semester": "100L First"},
        ]

        output, _ = self.run_calculator(courses, ["A", "B"])

        self.assertIn("Empty: cannot calculate GPA because credit units are zero.", output)
        self.assertIn("100L First GPA: 4.00\n", output)
        self.assertIn("Cumulative GPA: 4.00\n", output)


class TestSavedGrades(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.filename = Path(folder.name) / "courses.json"
        self.courses = [
            {"code": "COS101", "credit_units": 3},
            {"code": "MAT101", "credit_units": 2},
        ]
        # Use a temporary file so tests never change the user's courses.json.
        save_patch = patch(
            "gpa.save_data",
            side_effect=lambda filename, data: save_data(self.filename, data),
        )
        self.save_mock = save_patch.start()
        self.addCleanup(save_patch.stop)

    def run_calculator(self, courses, grades):
        output = StringIO()
        with patch("builtins.input", side_effect=grades) as grade_input:
            with redirect_stdout(output):
                calculate_gpa(courses)
        return output.getvalue(), grade_input

    def test_old_courses_gain_saved_grades(self):
        output, _ = self.run_calculator(self.courses, ["a", "C"])

        saved = load_data(self.filename)
        self.assertEqual([course["grade"] for course in saved], ["A", "C"])
        self.assertIn("GPA: 4.20\n", output)
        self.save_mock.assert_called_once_with("courses.json", self.courses)

    def test_enter_keeps_grades_after_reloading(self):
        self.run_calculator(self.courses, ["A", "C"])
        reloaded = load_data(self.filename)

        output, grade_input = self.run_calculator(reloaded, ["", ""])

        self.assertIn("saved grade: A", grade_input.call_args_list[0].args[0])
        self.assertIn("saved grade: C", grade_input.call_args_list[1].args[0])
        self.assertIn("Enter to keep", grade_input.call_args_list[0].args[0])
        self.assertIn("GPA: 4.20\n", output)
        self.assertEqual(load_data(self.filename), reloaded)

    def test_new_grade_replaces_saved_grade(self):
        self.run_calculator(self.courses, ["A", "C"])

        output, _ = self.run_calculator(self.courses, ["b", ""])

        self.assertEqual(load_data(self.filename)[0]["grade"], "B")
        self.assertIn("GPA: 3.60\n", output)

    def test_cancel_leaves_saved_grades_unchanged(self):
        self.run_calculator(self.courses, ["A", "C"])
        original_file = self.filename.read_bytes()
        self.save_mock.reset_mock()

        output, _ = self.run_calculator(self.courses, ["B", "q"])

        self.assertIn("GPA calculation cancelled.", output)
        self.assertNotIn("GPA RESULT", output)
        self.assertEqual(self.filename.read_bytes(), original_file)
        self.assertEqual(self.courses[0]["grade"], "A")
        self.save_mock.assert_not_called()

    def test_invalid_saved_grade_requires_valid_input(self):
        self.courses[0]["grade"] = "X"

        output, _ = self.run_calculator(self.courses, ["", "A", "C"])

        self.assertEqual(output.count("Invalid grade."), 1)
        self.assertEqual(load_data(self.filename)[0]["grade"], "A")


if __name__ == "__main__":
    unittest.main()
