"""The upload form trusts only checked bytes, never the browser's claims."""
import uuid
from types import SimpleNamespace
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from student_web.forms import MaterialUploadForm

COURSE = SimpleNamespace(pk=uuid.uuid4(), normalized_code="CSC101", name="Synthetic course")


def upload_form(filename, content, **changes):
    data = {"title": "Week 1 notes", "course_id": str(COURSE.pk), **changes}
    upload = SimpleUploadedFile(filename, content, content_type="application/pdf")
    return MaterialUploadForm(data, {"file": upload}, courses=[COURSE])


class MaterialUploadFormTests(SimpleTestCase):
    databases = {"default", "runtime", "auth"}

    def test_valid_text_and_pdf_produce_checked_file_facts(self):
        form = upload_form("notes.txt", "Synthetic notes".encode())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.file_facts, {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 15})
        form = upload_form("slides.PDF", b"%PDF-1.7 synthetic")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.file_facts["file_type"], "pdf")

    def test_wrong_or_disguised_files_are_rejected(self):
        for filename, content in (("virus.pdf", b"MZ\x90\x00"), ("program.exe", b"%PDF-1.7"),
                                  ("notes.txt", b"\xff\xfe broken"), ("notes.txt", b"bad \x00 byte"),
                                  ("noextension", b"Synthetic")):
            form = upload_form(filename, content)
            self.assertFalse(form.is_valid(), filename)
            self.assertIn("file", form.errors)
            self.assertIsNone(form.file_facts)

    def test_course_must_come_from_the_students_own_list(self):
        form = upload_form("notes.txt", b"Synthetic", course_id=str(uuid.uuid4()))
        self.assertFalse(form.is_valid())
        self.assertIn("course_id", form.errors)

    def test_extra_fields_like_owner_are_refused(self):
        form = upload_form("notes.txt", b"Synthetic", owner_id=str(uuid.uuid4()))
        self.assertFalse(form.is_valid())

    def test_missing_title_or_file_is_refused(self):
        form = upload_form("notes.txt", b"Synthetic", title="   ")
        self.assertFalse(form.is_valid())
        form = MaterialUploadForm({"title": "Week 1", "course_id": str(COURSE.pk)}, {}, courses=[COURSE])
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)