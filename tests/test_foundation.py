"""Regression checks for production foundation; all records are synthetic."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal, localcontext
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from academic_logic import (academic_summary, checked_credits, checked_target, checked_grade,
                            predicted_summary, target_plan, validate_assignments)
from gpa import calculate_gpa
from gpa_predictor import predict_gpa
from target_cgpa import plan_target_cgpa
from assignments import list_assignments, mark_assignment_complete, add_assignment
from tools.check_repository_safety import private_path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


class TestFoundation(unittest.TestCase):
    def setUp(self):
        self.courses = [{"code": "ONE", "name": "Synthetic course", "credit_units": 3, "grade": "A"}]
        self.assignment = {"title": "Synthetic task", "course_code": "ONE",
                           "due_date": "2030-01-01", "completed": False}

    def test_documented_tiny_remaining_regression_is_rejected(self):
        for remaining in ("1e-30", "1e-300", "0.00001"):
            with self.subTest(remaining=remaining), self.assertRaises(ValueError):
                target_plan(self.courses, 5, remaining)

    def test_minimum_remaining_still_requires_five_for_all_a(self):
        result = target_plan(self.courses, 5, "0.0001")
        self.assertEqual(result["required"], 5)
        self.assertEqual(result["status"], "achievable")

    def test_planning_does_not_depend_on_callers_decimal_precision(self):
        with localcontext() as context:
            context.prec = 2
            result = target_plan(self.courses, 5, "0.0001")
        self.assertEqual(result["required"], 5)
        self.assertEqual(result["total"], Decimal("3.0001"))

    def test_outcome_uses_unrounded_required_average(self):
        courses = [{"code": "ONE", "credit_units": 3, "grade": "B"}]
        self.assertEqual(target_plan(courses, "4.5", 3)["status"], "achievable")
        result = target_plan(courses, "4.5001", 3)
        self.assertEqual(result["required"], Decimal("5.0002"))
        self.assertEqual(result["status"], "impossible")

    def test_guarantee_boundary_is_exact(self):
        self.assertEqual(target_plan(self.courses, 3, 2)["required"], 0)
        self.assertEqual(target_plan(self.courses, 3, 2)["status"], "guaranteed")
        self.assertGreater(target_plan(self.courses, "3.0001", 2)["required"], 0)

    def test_credit_and_target_input_limits(self):
        self.assertEqual(checked_credits("1000000.0000"), Decimal(1000000))
        self.assertEqual(checked_credits("0.1"), Decimal("0.1"))
        self.assertEqual(checked_target("5.0000"), 5)
        for value in (True, None, [], "nan", "inf", "-1", "0", "1000001", "1.00001", "9" * 129):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checked_credits(value)
        for value in (True, None, {}, "nan", "-0.01", "5.0001", "4.00001"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checked_target(value)

    def test_grades_keep_ungraded_separate_from_f(self):
        self.assertEqual(checked_grade(" f "), "F")
        self.assertIsNone(checked_grade(None))
        self.assertIsNone(checked_grade(" "))
        for grade in (False, 0, [], {}, "X"):
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                checked_grade(grade)

    def test_out_of_range_saved_records_are_skipped_without_rewriting(self):
        courses = self.courses + [{"code": "TINY", "credit_units": 1e-30, "grade": "F"}]
        original = copy.deepcopy(courses)
        summary = academic_summary(courses)
        self.assertEqual(summary["units"], 3)
        self.assertEqual(summary["gpa"], 5)
        self.assertEqual(len(summary["warnings"]), 1)
        self.assertEqual(courses, original)

    def test_hypothetical_grades_do_not_need_valid_actual_grades(self):
        courses = [{"code": "ONE", "credit_units": 3, "grade": "DAMAGED"}]
        original = copy.deepcopy(courses)
        self.assertIsNone(academic_summary(courses)["gpa"])
        self.assertEqual(predicted_summary(courses, {"ONE": "B"})["gpa"], 4)
        self.assertEqual(courses, original)

    def test_cli_predictor_handles_huge_credits_and_duplicates(self):
        courses = self.courses + [self.courses[0], {"code": "HUGE", "credit_units": 10 ** 400}]
        output = StringIO()
        with patch("builtins.input", side_effect=["C", "Q"]) as prompts, redirect_stdout(output):
            predict_gpa(courses)
        self.assertEqual(prompts.call_count, 2)
        self.assertIn("Predicted GPA: 3.00", output.getvalue())
        self.assertIn("Skipping duplicate", output.getvalue())

    def test_cli_calculator_skips_malformed_and_negative_records(self):
        courses = [None, {"code": "BAD", "credit_units": -2}] + self.courses
        output = StringIO()
        with patch("gpa.save_data"), patch("builtins.input", side_effect=["A"]) as prompts, redirect_stdout(output):
            calculate_gpa(courses)
        self.assertEqual(prompts.call_count, 1)
        self.assertIn("Cumulative GPA: 5.00", output.getvalue())

    def test_cli_planner_retries_tiny_remaining_values(self):
        output = StringIO()
        with patch("builtins.input", side_effect=["5", "1e-30", "0.0001"]), redirect_stdout(output):
            plan_target_cgpa(self.courses)
        self.assertIn("greater than zero", output.getvalue())
        self.assertIn("Required average grade point: 5.00", output.getvalue())
        self.assertNotIn("already guaranteed", output.getvalue())

    def test_assignment_validation_excludes_incomplete_and_malformed_records(self):
        malformed = [None, [], {}, {"title": "Incomplete"}]
        for key, value in (("title", " "), ("course_code", "MISSING"), ("due_date", "2030"),
                           ("due_date", "2030-02-30"), ("due_date", "20300101"),
                           ("completed", "False"), ("completed", 0), ("due_date", None)):
            malformed.append(dict(self.assignment, **{key: value}))
        original = copy.deepcopy(malformed)
        valid, warnings = validate_assignments(malformed + [self.assignment], self.courses)
        self.assertEqual(valid, [(len(malformed), self.assignment)])
        self.assertEqual(len(warnings), len(malformed))
        self.assertEqual(original, malformed)

    def test_completed_assignments_and_valid_older_dates_are_recognized(self):
        records = [dict(self.assignment, completed=True), dict(self.assignment, due_date="2020-02-29")]
        valid, warnings = validate_assignments(records, self.courses)
        self.assertFalse(warnings)
        self.assertEqual(sum(not item["completed"] for index, item in valid), 1)

    def test_assignment_validation_accepts_normalized_course_links(self):
        valid, warnings = validate_assignments([dict(self.assignment, course_code=" one ")], self.courses)
        self.assertEqual(len(valid), 1)
        self.assertEqual(warnings, [])

    def test_cli_assignment_list_excludes_incomplete_records(self):
        output = StringIO()
        with redirect_stdout(output):
            list_assignments([{}, None, self.assignment])
        self.assertEqual(output.getvalue().count("Pending"), 1)
        self.assertIn("3. Synthetic task", output.getvalue())
        self.assertIn("Total assignments: 1", output.getvalue())

    def test_cli_cannot_mark_invalid_assignment_complete(self):
        assignments = [{}, self.assignment]
        original = copy.deepcopy(assignments)
        with patch("assignments.save_data") as save, patch("builtins.input", return_value="1"), redirect_stdout(StringIO()):
            mark_assignment_complete(assignments)
        save.assert_not_called()
        self.assertEqual(assignments, original)

    def test_cli_rejects_invalid_assignment_date_without_saving(self):
        assignments = []
        with patch("assignments.save_data") as save, patch("builtins.input", side_effect=["Task", "ONE", "2030"]), redirect_stdout(StringIO()):
            add_assignment(assignments, self.courses)
        save.assert_not_called()
        self.assertEqual(assignments, [])

    def test_all_cli_academic_features_remain_available(self):
        main = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as folder:
            course_file = Path(folder) / "courses.json"
            course_file.write_text(json.dumps(self.courses))
            Path(folder, "assignments.json").write_text(json.dumps([self.assignment]))
            result = subprocess.run([sys.executable, "-B", str(main)], cwd=folder,
                                    input="2\n6\n9\n\n11\nB\nQ\n12\n13\n5\n3\n10\n",
                                    text=True, capture_output=True, check=True, timeout=10)
            for expected in ("Your courses:", "Your assignments:", "Cumulative GPA: 5.00",
                             "Predicted GPA: 4.00", "ACADEMIC PERFORMANCE OVERVIEW",
                             "Required average grade point: 5.00", "Goodbye!"):
                self.assertIn(expected, result.stdout)
            self.assertEqual(json.loads(course_file.read_text()), self.courses)

    def test_repository_safety_rejects_private_and_temporary_paths(self):
        for path in ("courses.json", "assignments.json", "private/courses.json", "courses.json.bak.2",
                     "venv/bin/python", ".venv-test/bin/python", ".env", ".env.production",
                     ".streamlit/secrets.toml", "records.bak", ".ucc-save"):
            with self.subTest(path=path):
                self.assertTrue(private_path(path))
        for path in ("requirements-lock.txt", ".env.example", "tests/test_storage.py", ".streamlit/config.toml"):
            self.assertFalse(private_path(path))

    def test_gitignore_covers_private_files_without_creating_them(self):
        root = Path(__file__).resolve().parents[1]
        paths = ["courses.json", "assignments.json.bak.3", "records.bak", "venv/example", ".venv-test/example",
                 ".env", ".env.production", ".streamlit/secrets.toml", ".ucc-save"]
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=root,
            input=b"\0".join(path.encode("utf-8") for path in paths) + b"\0",
            capture_output=True,
            check=True,
        )
        ignored = result.stdout.decode("utf-8").split("\0")
        self.assertEqual(set(ignored[:-1]), set(paths))


@unittest.skipIf(AppTest is None, "Install web requirements to run Streamlit regression tests")
class TestFoundationWeb(unittest.TestCase):
    def test_dashboard_excludes_invalid_assignments_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"UCC_DATA_DIR": folder}):
            courses = Path(folder, "courses.json")
            assignments = Path(folder, "assignments.json")
            courses.write_text('[{"code":"ONE","credit_units":3}]')
            assignments.write_text(json.dumps([
                {}, None, {"title": "Incomplete", "completed": False},
                {"title": "Valid", "course_code": "ONE", "due_date": "2030-01-01", "completed": False},
                {"title": "Done", "course_code": "ONE", "due_date": "2030-01-01", "completed": True},
            ]))
            before = assignments.read_bytes()
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "web_app.py"), default_timeout=20).run()
            self.assertFalse(app.exception)
            pending = next(metric for metric in app.metric if metric.label == "Pending assignments")
            self.assertEqual(pending.value, "1")
            self.assertEqual(len(app.warning), 3)
            app.sidebar.radio[0].set_value("Assignments").run()
            self.assertFalse(app.exception)
            self.assertEqual(sum(button.label == "Mark complete" for button in app.button), 1)
            self.assertEqual(assignments.read_bytes(), before)
