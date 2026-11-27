import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from storage import load_data, save_data


class TestStorage(unittest.TestCase):
    def test_damaged_file_is_backed_up_before_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "courses.json"
            damaged_data = b'{"unfinished":'
            filename.write_bytes(damaged_data)
            courses = [{"code": "COS101", "credit_units": 3}]

            with redirect_stdout(StringIO()):
                self.assertEqual(load_data(filename), [])
                save_data(str(filename), courses)

            backup = Path(f"{filename}.bak")
            self.assertEqual(backup.read_bytes(), damaged_data)
            self.assertEqual(load_data(filename), courses)
            save_data(filename, [])
            self.assertEqual(backup.read_bytes(), damaged_data)
            self.assertFalse(Path(f"{filename}.bak.1").exists())

    def test_backup_failure_leaves_damaged_file_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "courses.json"
            damaged_data = b'{"unfinished":'
            filename.write_bytes(damaged_data)
            output = StringIO()

            with redirect_stdout(output):
                load_data(filename)
                with patch("storage.shutil.copyfile", side_effect=PermissionError):
                    save_data(filename, [])

            self.assertEqual(filename.read_bytes(), damaged_data)
            self.assertIn("Could not save", output.getvalue())

    def test_existing_backup_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "courses.json"
            backup = Path(f"{filename}.bak")
            backup.write_bytes(b"older damaged data")
            filename.write_bytes(b"new damaged data")

            with redirect_stdout(StringIO()):
                load_data(filename)
                save_data(filename, [])

            self.assertEqual(backup.read_bytes(), b"older damaged data")
            self.assertEqual(Path(f"{filename}.bak.1").read_bytes(), b"new damaged data")

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
