import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from storage import load_data, save_data


class TestStorage(unittest.TestCase):
    def test_damaged_json_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "damaged.json"
            damaged_data = b'{"unfinished":'
            filename.write_bytes(damaged_data)
            output = StringIO()

            with redirect_stdout(output):
                result = load_data(filename)

            self.assertEqual(result, [])
            self.assertIn("Could not read", output.getvalue())
            self.assertIn(str(filename), output.getvalue())
            self.assertEqual(filename.read_bytes(), damaged_data)

    def test_unreadable_text_is_left_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "unreadable.json"
            filename.write_bytes(b'\xff\xfe')
            output = StringIO()

            with redirect_stdout(output):
                result = load_data(filename)

            self.assertEqual(result, [])
            self.assertIn("Could not read", output.getvalue())
            self.assertEqual(filename.read_bytes(), b'\xff\xfe')

    def test_loading_permission_error(self):
        output = StringIO()
        with patch("builtins.open", side_effect=PermissionError):
            with redirect_stdout(output):
                result = load_data("courses.json")

        self.assertEqual(result, [])
        self.assertIn("Could not read courses.json", output.getvalue())

    def test_saving_permission_error(self):
        output = StringIO()
        with patch("builtins.open", side_effect=PermissionError):
            with redirect_stdout(output):
                save_data("courses.json", [])

        self.assertIn("Could not save courses.json", output.getvalue())

    def test_successful_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "courses.json"
            courses = [{"code": "COS101", "credit_units": 3}]

            save_data(filename, courses)

            self.assertEqual(load_data(filename), courses)


if __name__ == "__main__":
    unittest.main()
