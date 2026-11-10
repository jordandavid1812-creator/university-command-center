import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from courses import add_course, edit_course, list_courses, remove_course


class TestCourseSemesters(unittest.TestCase):
    def setUp(self):
        save_patch = patch("courses.save_data")
        self.save_mock = save_patch.start()
        self.addCleanup(save_patch.stop)
        self.courses = [
            {"name": "Computing", "code": "COS101", "credit_units": 3,
             "semester": "100L First"},
            {"name": "Math", "code": "MAT102", "credit_units": 2,
             "semester": "100L Second"},
            {"name": "Physics", "code": "PHY101", "credit_units": 3,
             "semester": "100L First"},
            {"name": "Old Course", "code": "OLD101", "credit_units": 2},
        ]

    def test_add_course_saves_semester(self):
        courses = []
        with patch("builtins.input", side_effect=["Computing", "cos101", "3", " 100L First "]):
            with redirect_stdout(StringIO()):
                add_course(courses)

        self.assertEqual(courses[0]["semester"], "100L First")
        self.save_mock.assert_called_once_with("courses.json", courses)

    def test_blank_semester_is_unassigned(self):
        courses = []
        with patch("builtins.input", side_effect=["Computing", "COS101", "3", " "]):
            with redirect_stdout(StringIO()):
                add_course(courses)

        self.assertEqual(courses[0]["semester"], "Unassigned")

    def test_list_groups_courses_and_keeps_original_numbers(self):
        output = StringIO()
        with redirect_stdout(output):
            list_courses(self.courses)

        text = output.getvalue()
        first_group = text.split("100L First:")[1].split("100L Second:")[0]
        self.assertIn("1. Computing (COS101)", first_group)
        self.assertIn("3. Physics (PHY101)", first_group)
        self.assertNotIn("Math", first_group)
        self.assertIn("2. Math (MAT102)", text)
        self.assertIn("Unassigned:\n4. Old Course (OLD101)", text)
        self.assertIn("Total courses: 4", text)
        self.assertNotIn("semester", self.courses[3])
        self.save_mock.assert_not_called()

    def test_remove_uses_number_shown_in_grouped_list(self):
        with patch("builtins.input", return_value="3"):
            with redirect_stdout(StringIO()):
                remove_course(self.courses)

        self.assertEqual([course["code"] for course in self.courses],
                         ["COS101", "MAT102", "OLD101"])

    def test_edit_uses_number_shown_and_preserves_semester(self):
        with patch("builtins.input", side_effect=["3", "New Physics", "PHY101", "4", ""]):
            with redirect_stdout(StringIO()):
                edit_course(self.courses)

        self.assertEqual(self.courses[2]["name"], "New Physics")
        self.assertEqual(self.courses[2]["semester"], "100L First")
        self.assertEqual(self.courses[1]["name"], "Math")

    def test_edit_changes_and_saves_semester(self):
        self.courses[0]["grade"] = "A"
        with patch("builtins.input", side_effect=["1", "Computing", "COS101", "3", " 200L First "]):
            with redirect_stdout(StringIO()):
                edit_course(self.courses)

        self.assertEqual(self.courses[0]["semester"], "200L First")
        self.assertEqual(self.courses[0]["grade"], "A")
        self.save_mock.assert_called_once_with("courses.json", self.courses)

    def test_edit_assigns_semester_to_old_course(self):
        with patch("builtins.input", side_effect=["4", "Old Course", "OLD101", "2", "100L Second"]):
            with redirect_stdout(StringIO()):
                edit_course(self.courses)

        self.assertEqual(self.courses[3]["semester"], "100L Second")
        self.save_mock.assert_called_once_with("courses.json", self.courses)

    def test_edit_old_course_keeps_unassigned_on_enter(self):
        with patch("builtins.input", side_effect=["4", "Old Course", "OLD101", "2", " "]) as prompts:
            with redirect_stdout(StringIO()):
                edit_course(self.courses)

        self.assertEqual(self.courses[3]["semester"], "Unassigned")
        self.assertIn("Enter to keep Unassigned", prompts.call_args.args[0])

    def test_invalid_edit_does_not_change_semester(self):
        with patch("builtins.input", side_effect=["1", "Computing", "COS101", "0", "200L First"]):
            with redirect_stdout(StringIO()):
                edit_course(self.courses)

        self.assertEqual(self.courses[0]["semester"], "100L First")
        self.save_mock.assert_not_called()

    def test_empty_course_list(self):
        output = StringIO()
        with redirect_stdout(output):
            list_courses([])

        self.assertIn("You have no courses yet.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
