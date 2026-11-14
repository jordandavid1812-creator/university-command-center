import unittest

from server.student_web.upload_validation import (
    MAX_UPLOAD_BYTES,
    validate_upload_metadata,
)


class TestUploadValidation(unittest.TestCase):
    def test_allowed_extensions(self):
        self.assertEqual(
            validate_upload_metadata("NOTES.PDF", 100), ".pdf"
        )
        self.assertEqual(
            validate_upload_metadata("notes.txt", 100), ".txt"
        )

    def test_size_limit(self):
        self.assertEqual(
            validate_upload_metadata("notes.pdf", MAX_UPLOAD_BYTES), ".pdf"
        )
        with self.assertRaises(ValueError):
            validate_upload_metadata("notes.pdf", MAX_UPLOAD_BYTES + 1)

    def test_invalid_sizes(self):
        for size in (0, -1, True, None, "100", 1.5):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    validate_upload_metadata("notes.txt", size)

    def test_invalid_names(self):
        for filename in (
            None, "", " ", "../notes.pdf", r"folder\notes.pdf",
            "notes\n.pdf", "notes\x00.pdf", "a" * 256 + ".pdf",
        ):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    validate_upload_metadata(filename, 100)

    def test_unsupported_extensions(self):
        for filename in ("notes.exe", "notes.pdf.exe", "notes", "notes.docx"):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    validate_upload_metadata(filename, 100)


if __name__ == "__main__":
    unittest.main()
