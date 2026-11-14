"""Material file service: owner-only bytes, all-or-nothing saves and per-student quotas."""
from unittest.mock import patch
from academics import services
from academics.services import InvalidRecord, RecordNotFound, StorageQuotaExceeded, materials
from .base import StudentSecurityCase

CONTENT = b"Synthetic notes"


class MaterialFileServiceTests(StudentSecurityCase):
    def upload(self, identity, course, content=CONTENT, title="Synthetic notes"):
        return materials.create_with_file(identity, title=title, course_id=course.pk,
                                          original_filename="notes.txt", file_type="txt", content=content)

    def test_saved_file_is_read_back_by_its_owner_only(self):
        material = self.upload(self.a, self.course_a)
        self.assertEqual(material.size_bytes, len(CONTENT))
        self.assertEqual(materials.read_file(self.a, material.pk)[1], CONTENT)
        self.assertEqual(materials.stored_ids(self.a), {material.pk})
        self.assertEqual(materials.stored_ids(self.b), set())
        with self.assertRaises(RecordNotFound):
            materials.read_file(self.b, material.pk)

    def test_material_without_a_stored_file_has_nothing_to_read(self):
        material = materials.create(self.a, course_id=self.course_a.pk, title="Details only",
                                    original_filename="notes.txt", file_type="txt", size_bytes=10)
        with self.assertRaises(RecordNotFound):
            materials.read_file(self.a, material.pk)

    def test_cannot_upload_to_another_students_course(self):
        with self.assertRaises(RecordNotFound):
            self.upload(self.a, self.course_b)
        self.assertEqual(materials.list(self.a) + materials.list(self.b), [])

    def test_bad_content_saves_nothing_at_all(self):
        for content in (b"", "text, not bytes", b"a" * (10 * 1024 * 1024 + 1)):
            with self.assertRaises(InvalidRecord):
                self.upload(self.a, self.course_a, content=content)
        self.assertEqual(materials.list(self.a), [])

    def test_file_count_quota_is_per_student(self):
        with patch.object(services, "MAX_FILES_PER_STUDENT", 2):
            self.upload(self.a, self.course_a)
            self.upload(self.a, self.course_a)
            with self.assertRaises(StorageQuotaExceeded):
                self.upload(self.a, self.course_a)
            self.upload(self.b, self.course_b)
        self.assertEqual((len(materials.list(self.a)), len(materials.list(self.b))), (2, 1))

    def test_storage_size_quota_and_delete_frees_space(self):
        with patch.object(services, "MAX_STORED_BYTES_PER_STUDENT", 20):
            first = self.upload(self.a, self.course_a)
            with self.assertRaises(StorageQuotaExceeded):
                self.upload(self.a, self.course_a)
            materials.delete(self.a, first.pk, version=1)
            self.upload(self.a, self.course_a)
        self.assertEqual(len(materials.list(self.a)), 1)

    def test_file_less_records_do_not_count_toward_the_quota(self):
        materials.create(self.a, course_id=self.course_a.pk, title="Details only",
                         original_filename="notes.txt", file_type="txt", size_bytes=10)
        with patch.object(services, "MAX_FILES_PER_STUDENT", 1):
            self.upload(self.a, self.course_a)

    def test_deleting_the_material_removes_its_file(self):
        material = self.upload(self.a, self.course_a)
        materials.delete(self.a, material.pk, version=1)
        self.assertEqual(materials.stored_ids(self.a), set())
        with self.assertRaises(RecordNotFound):
            materials.read_file(self.a, material.pk)
