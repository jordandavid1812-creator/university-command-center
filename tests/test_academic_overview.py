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

from academic_overview import show_academic_overview


class TestAcademicOverview(unittest.TestCase):
    def overview(self, courses):
        output = StringIO()
        with redirect_stdout(output):
            show_academic_overview(courses)
        return output.getvalue()

    def test_two_semesters_and_weighted_cumulative_gpa(self):
        courses = [
            {"code": "COS101", "credit_units": 3, "grade": "A", "semester": "100L First"},
            {"code": "MAT101", "credit_units": 2, "grade": "C", "semester": "100L First"},
            {"code": "COS102", "credit_units": 6, "grade": "E", "semester": "100L Second"},
        ]
        output = self.overview(courses)

        self.assertIn("Semester GPA: 4.20", output)
        self.assertIn("Semester GPA: 1.00", output)
        self.assertIn("Cumulative GPA: 2.45", output)  # 27 points / 11 units
        self.assertIn("Total completed courses (saved grades, including F): 3", output)
        self.assertIn("Attempted credit units (graded courses only): 11", output)
        self.assertIn("100L Second: [####                ] 1.00", output)

    def test_ungraded_courses_are_not_f_grades(self):
        courses = [
            {"code": "ONE", "credit_units": 3, "grade": "A"},
            {"code": "TWO", "credit_units": 6},
            {"code": "THREE", "credit_units": 2, "grade": ""},
            {"code": "FOUR", "credit_units": 2, "grade": None},
        ]
        output = self.overview(courses)

        self.assertIn("Unassigned:", output)
        self.assertIn("ONE: saved grade A", output)
        self.assertIn("TWO: no saved grade", output)
        self.assertIn("Courses without saved grades: 3", output)
        self.assertIn("Attempted credit units (graded courses only): 3", output)
        self.assertIn("Cumulative GPA: 5.00", output)

    def test_all_f_grades_are_completed_and_zero_gpa(self):
        output = self.overview([{"code": "ONE", "credit_units": 3, "grade": "F"}])

        self.assertIn("Cumulative GPA: 0.00", output)
        self.assertIn("Total completed courses (saved grades, including F): 1", output)
        self.assertIn("Attempted credit units (graded courses only): 3", output)
        self.assertIn("Unassigned: [                    ] 0.00", output)

    def test_ungraded_semester_has_no_gpa(self):
        output = self.overview([{"code": "ONE", "credit_units": 3}])

        self.assertIn("Semester GPA: N/A (no graded courses)", output)
        self.assertIn("Cumulative GPA: N/A (no graded courses)", output)
        self.assertIn("Attempted credit units (graded courses only): 0", output)

    def test_empty_and_invalid_top_level_data(self):
        self.assertIn("You have no courses", self.overview([]))
        for courses in [None, {}, "bad data", 1]:
            with self.subTest(courses=courses):
                self.assertIn("Course data must be a list", self.overview(courses))

    def test_invalid_units_are_excluded(self):
        for units in [None, "3", True, 0, -1, float("nan"), float("inf"), 10 ** 400]:
            with self.subTest(units=units):
                output = self.overview([
                    {"code": "BAD", "credit_units": units, "grade": "A"},
                    {"code": "GOOD", "credit_units": 2, "grade": "B"},
                ])
                self.assertIn("Skipping BAD:", output)
                self.assertIn("Cumulative GPA: 4.00", output)
                self.assertIn("Attempted credit units (graded courses only): 2", output)

    def test_incomplete_records_and_invalid_grades(self):
        courses = [None, [], {}, {"code": " "}, {"code": 123},
                   {"code": "NO_UNITS", "grade": "A"}]
        for grade in ["X", 5, [], {}, False]:
            courses.append({"code": "BAD_GRADE", "credit_units": 3, "grade": grade})
        output = self.overview(courses)

        self.assertEqual(output.count("Skipping"), len(courses))
        self.assertIn("Cumulative GPA: N/A", output)

    def test_duplicates_across_semesters_count_once(self):
        output = self.overview([
            {"code": "COS101", "credit_units": 3, "grade": "A", "semester": "First"},
            {"code": " cos101 ", "credit_units": 6, "grade": "F", "semester": "Second"},
        ])

        self.assertIn("Skipping duplicate course COS101", output)
        self.assertIn("Total completed courses (saved grades, including F): 1", output)
        self.assertIn("Cumulative GPA: 5.00", output)
        self.assertNotIn("Second:", output)

    def test_free_text_semesters_keep_record_order(self):
        output = self.overview([
            {"code": "ONE", "credit_units": 3, "grade": " b ", "semester": "Later"},
            {"code": "TWO", "credit_units": 2, "grade": "A", "semester": "Earlier"},
        ])

        self.assertLess(output.index("Later:"), output.index("Earlier:"))
        self.assertIn("ONE: saved grade B", output)
        self.assertIn("this may not be chronological", output)

    def test_missing_or_invalid_semester_uses_unassigned(self):
        for semester in [None, "", " ", []]:
            with self.subTest(semester=semester):
                output = self.overview([
                    {"code": "ONE", "credit_units": 2.5, "grade": "A", "semester": semester}
                ])
                self.assertIn("Unassigned:", output)
                self.assertIn("Cumulative GPA: 5.00", output)

    def test_read_only_and_hypothetical_grades_excluded(self):
        courses = [
            {"code": "ONE", "credit_units": 3, "grade": "F", "predicted_grade": "A"},
            {"code": "TWO", "credit_units": 3, "predicted_grade": "A"},
        ]
        original = copy.deepcopy(courses)
        with patch("builtins.open", side_effect=AssertionError("Unexpected file access")):
            with patch("builtins.input", side_effect=AssertionError("Unexpected prompt")):
                output = self.overview(courses)

        self.assertEqual(courses, original)
        self.assertIn("Cumulative GPA: 0.00", output)
        self.assertIn("Courses without saved grades: 1", output)

    def test_menu_after_prediction_preserves_json(self):
        main = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as folder:
            courses = Path(folder) / "courses.json"
            assignments = Path(folder) / "assignments.json"
            original = json.dumps([{"code": "ONE", "credit_units": 3, "grade": "F"}]).encode()
            courses.write_bytes(original)
            assignments.write_bytes(b"[]")

            result = subprocess.run(
                [sys.executable, "-B", str(main)], cwd=folder,
                input="11\nA\nQ\n12\n6\n10\n",
                text=True, capture_output=True, check=True, timeout=10,
            )

            self.assertIn("12. Academic Performance Overview", result.stdout)
            self.assertIn("Predicted GPA: 5.00", result.stdout)
            self.assertIn("Cumulative GPA: 0.00", result.stdout)
            self.assertIn("You have no assignments", result.stdout)
            self.assertIn("Goodbye!", result.stdout)
            self.assertEqual(courses.read_bytes(), original)
            self.assertEqual(assignments.read_bytes(), b"[]")


if __name__ == "__main__":
    unittest.main()
