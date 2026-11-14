import unittest

from server.student_web.upload_validation import (
    MAX_UPLOAD_BYTES,
    validate_upload_metadata,
)


class TestUploadValidation(unittest.TestCase):
    def test_allowed_extensions(self):
        self.assertEqual(validate_upload_metadata("NOTES.PDF", 100), ".pdf")
        self.assertEqual(validate_upload_metadata("notes.txt", 100), ".txt")

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
            None,
            "",
            " ",
            "../notes.pdf",
            r"folder\notes.pdf",
            "notes\n.pdf",
            "notes\x00.pdf",
            "a" * 256 + ".pdf",
        ):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    validate_upload_metadata(filename, 100)

    def test_unsupported_extensions(self):
        for filename in ("notes.exe", "notes.pdf.exe", "notes", "notes.docx"):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    validate_upload_metadata(filename, 100)


class TestPdfContent(unittest.TestCase):
    def validate(self, content):
        from server.student_web.upload_validation import validate_pdf_content

        return validate_pdf_content(content)

    def test_real_pdf_header(self):
        content = b"%PDF-1.7\n%synthetic test file\n"
        self.assertEqual(self.validate(content), content)

    def test_rejects_files_that_are_not_pdfs(self):
        for content in (b"Hello", b"MZ\x90\x00", b" %PDF-1.7", b"%PDF"):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    self.validate(content)

    def test_rejects_wrong_type_empty_and_oversized(self):
        for content in ("%PDF-1.7", None, b"", b"%PDF-" + b"a" * MAX_UPLOAD_BYTES):
            with self.subTest(
                kind=type(content).__name__,
                length=len(content) if content is not None else None,
            ):
                with self.assertRaises(ValueError):
                    self.validate(content)


if __name__ == "__main__":
    unittest.main()


class TestTextContent(unittest.TestCase):
    def validate(self, content):
        from server.student_web.upload_validation import validate_text_content

        return validate_text_content(content)

    def test_readable_utf8(self):
        text = "Lecture notes: café\nSecond line\tExample"
        self.assertEqual(self.validate(text.encode("utf-8")), text)

    def test_utf8_bom(self):
        self.assertEqual(self.validate(b"\xef\xbb\xbfNotes"), "Notes")

    def test_empty_or_whitespace(self):
        for content in (b"", b" \r\n\t", b"\xef\xbb\xbf"):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    self.validate(content)

    def test_invalid_encoding_and_controls(self):
        for content in (b"\xff", b"Notes\x00", b"Notes\x1b", b"Notes\x7f"):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    self.validate(content)

    def test_invalid_type_and_oversized_content(self):
        for content in ("Notes", None, b"a" * (MAX_UPLOAD_BYTES + 1)):
            with self.subTest(
                kind=type(content).__name__,
                length=len(content) if content is not None else None,
            ):
                with self.assertRaises(ValueError):
                    self.validate(content)
