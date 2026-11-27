import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements.txt to run Streamlit interaction tests")
class TestWebApp(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        environment = patch.dict(os.environ, {"UCC_DATA_DIR": folder.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.courses = self.root / "courses.json"
        self.assignments = self.root / "assignments.json"
        self.courses.write_text(json.dumps([
            {"name": "Computing", "code": "COS101", "credit_units": 3, "grade": "A", "semester": "First", "extra": "keep"}
        ]))
        self.assignments.write_text('[]')
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "web_app.py"), default_timeout=20).run()

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def page(self, name):
        self.app.sidebar.radio[0].set_value(name).run()
        self.assertEqual(len(self.app.exception), 0)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assertEqual(len(self.app.exception), 0)

    def test_all_pages_render_without_writing(self):
        before = self.courses.read_bytes()
        for page in self.app.sidebar.radio[0].options:
            self.page(page)
        self.assertEqual(self.courses.read_bytes(), before)
        self.assertEqual(self.assignments.read_bytes(), b'[]')

    def test_course_add_edit_and_remove(self):
        self.page("Courses")
        self.widget("text_input", "Course name").set_value("Math")
        self.widget("text_input", "Course code").set_value("MAT101")
        self.widget("text_input", "Semester").set_value("Second")
        self.click("Save course")
        self.assertEqual(len(json.loads(self.courses.read_text())), 2)
        self.app.selectbox[0].set_value(0).run()
        self.widget("text_input", "Course name").set_value("New Computing")
        self.widget("selectbox", "Actual saved grade").set_value("B")
        self.click("Save course")
        saved = json.loads(self.courses.read_text())
        self.assertEqual(saved[0]["name"], "New Computing")
        self.assertEqual(saved[0]["grade"], "B")
        self.assertEqual(saved[0]["extra"], "keep")
        self.assertTrue(Path(f"{self.courses}.bak").exists())
        self.widget("checkbox", "I confirm I want to remove this course").check().run()
        self.click("Remove course")
        self.assertEqual([c["code"] for c in json.loads(self.courses.read_text())], ["MAT101"])

    def test_assignment_add_complete_and_remove(self):
        self.page("Assignments")
        self.widget("text_input", "Assignment title").set_value("Read chapter one")
        self.click("Add assignment")
        self.assertEqual(len(json.loads(self.assignments.read_text())), 1)
        self.click("Mark complete")
        self.assertTrue(json.loads(self.assignments.read_text())[0]["completed"])
        self.click("Mark pending")
        self.assertFalse(json.loads(self.assignments.read_text())[0]["completed"])
        self.widget("checkbox", "Confirm removal").check().run()
        self.click("Remove assignment")
        self.assertEqual(json.loads(self.assignments.read_text()), [])

    def test_predictor_and_target_plan_do_not_save(self):
        before = self.courses.read_bytes()
        self.page("GPA Predictor")
        self.app.selectbox[0].set_value("F")
        self.click("Calculate prediction")
        self.assertEqual(self.app.metric[0].value, "0.00")
        self.app.selectbox[0].set_value("B")
        self.click("Calculate prediction")
        self.assertEqual(self.app.metric[0].value, "4.00")
        self.page("Target CGPA Planner")
        self.widget("number_input", "Desired final CGPA").set_value(5.0)
        self.widget("number_input", "Remaining credit units").set_value(3.0)
        self.click("Calculate required average")
        self.assertEqual(self.app.metric[-1].value, "5.00")
        self.assertEqual(self.courses.read_bytes(), before)
        self.assertEqual(self.assignments.read_bytes(), b'[]')

    def test_bad_input_shows_validation(self):
        self.page("Courses")
        self.click("Save course")
        self.assertIn("required", self.app.error[0].value)
        self.page("Target CGPA Planner")
        self.widget("number_input", "Remaining credit units").set_value(0.0)
        self.click("Calculate required average")
        self.assertIn("greater than zero", self.app.error[0].value)

    def test_stale_form_cannot_overwrite_changes(self):
        self.page("Courses")
        external = self.courses.read_bytes() + b'\n'
        self.courses.write_bytes(external)
        self.widget("text_input", "Course name").set_value("New")
        self.widget("text_input", "Course code").set_value("NEW101")
        self.click("Save course")
        self.assertIn("changed since", self.app.error[0].value)
        self.assertEqual(self.courses.read_bytes(), external)

    def test_corrupt_file_disables_editing(self):
        self.courses.write_bytes(b'{"bad":')
        self.click("Reload data")
        self.assertIn("damaged", self.app.error[0].value)
        self.assertEqual(len(self.app.text_input), 0)
        self.assertFalse(any(item.label == "Save course" for item in self.app.button))
        self.assertEqual(self.courses.read_bytes(), b'{"bad":')

    def test_empty_workspace_creates_nothing_on_read(self):
        self.courses.unlink()
        self.assignments.unlink()
        self.click("Reload data")
        self.page("Dashboard")
        self.assertEqual(self.app.metric[0].value, "Not graded")
        self.page("GPA Predictor")
        self.assertTrue(any("Add at least one" in item.value for item in self.app.info))
        self.assertFalse(self.courses.exists())
        self.assertFalse(self.assignments.exists())
