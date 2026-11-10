import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_data import DataError, read_records, write_records


class TestWebData(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "courses.json"

    def test_missing_file_does_not_get_created_by_reading(self):
        snapshot = read_records(self.path)
        self.assertEqual(snapshot.records, [])
        self.assertFalse(self.path.exists())
        write_records(self.path, [{"code": "ONE"}], snapshot)
        self.assertEqual(read_records(self.path).records, [{"code": "ONE"}])

    def test_damaged_and_wrong_shape_files_cannot_be_overwritten(self):
        for original in [b'{"bad":', b'{}', b'\xff\xfe']:
            self.path.write_bytes(original)
            with self.assertRaises(DataError):
                read_records(self.path)
            # Even a previously valid snapshot cannot replace a now-damaged file.
            from web_data import Snapshot
            with self.assertRaises(DataError):
                write_records(self.path, [], Snapshot([], None))
            self.assertEqual(self.path.read_bytes(), original)

    def test_successful_write_keeps_exact_backup_and_unknown_fields(self):
        original = b'[ {"code":"ONE", "custom":"keep"} ]\n'
        self.path.write_bytes(original)
        snapshot = read_records(self.path)
        write_records(self.path, snapshot.records + [{"code": "TWO"}], snapshot)
        self.assertEqual(Path(f"{self.path}.bak").read_bytes(), original)
        self.assertEqual(read_records(self.path).records[0]["custom"], "keep")
        write_records(self.path, [], read_records(self.path))
        self.assertEqual(Path(f"{self.path}.bak").read_bytes(), original)
        self.assertTrue(Path(f"{self.path}.bak.1").exists())

    def test_stale_snapshot_cannot_erase_external_changes(self):
        self.path.write_text('[]')
        snapshot = read_records(self.path)
        self.path.write_text('[{"code":"EXTERNAL"}]')
        with self.assertRaisesRegex(DataError, "changed"):
            write_records(self.path, [], snapshot)
        self.assertEqual(read_records(self.path).records, [{"code": "EXTERNAL"}])

    def test_backup_failure_prevents_write(self):
        self.path.write_text('[]')
        snapshot = read_records(self.path)
        original_open = Path.open
        def fail_backup(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError("Backup is not writable")
            return original_open(path, mode, *args, **kwargs)
        with patch("pathlib.Path.open", new=fail_backup):
            with self.assertRaises(DataError):
                write_records(self.path, [{"code": "ONE"}], snapshot)
        self.assertEqual(self.path.read_bytes(), b'[]')

    def test_atomic_replace_failure_keeps_original_and_cleans_temporary(self):
        self.path.write_text('[]')
        snapshot = read_records(self.path)
        with patch("web_data.os.replace", side_effect=OSError):
            with self.assertRaises(DataError):
                write_records(self.path, [{"code": "ONE"}], snapshot)
        self.assertEqual(self.path.read_bytes(), b'[]')
        self.assertEqual(list(self.path.parent.glob('.ucc-*')), [])

    def test_serialization_failure_does_not_truncate_original(self):
        self.path.write_text('[]')
        snapshot = read_records(self.path)
        with self.assertRaises(DataError):
            write_records(self.path, [{"bad": float('nan')}], snapshot)
        self.assertEqual(self.path.read_bytes(), b'[]')
