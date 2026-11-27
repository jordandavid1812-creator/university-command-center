"""Study material service: owner-only CRUD with file facts fixed at upload."""
import uuid
from decimal import Decimal
from academics.services import InvalidRecord, RecordConflict, RecordNotFound, courses, materials
from .base import StudentSecurityCase

FILE_FACTS = {"original_filename": "notes.txt", "file_type": "txt", "size_bytes": 10}


class StudyMaterialServiceTests(StudentSecurityCase):
    def create_for(self, identity, course, title="Synthetic notes"):
        return materials.create(identity, course_id=course.pk, title=title, **FILE_FACTS)

    def second_course_a(self):
        return courses.create(self.a, semester_id=self.sem_a.pk, original_code="CSC102",
                              name="Synthetic A2", credit_units=Decimal("3"))

    def test_create_and_list_only_own_materials(self):
        mine = self.create_for(self.a, self.course_a)
        self.create_for(self.b, self.course_b)
        self.assertEqual([m.pk for m in materials.list(self.a)], [mine.pk])
        self.assertEqual((mine.owner_id, mine.record_version), (self.a.student_id, 1))

    def test_cannot_use_or_reach_another_students_records(self):
        with self.assertRaises(RecordNotFound):
            self.create_for(self.a, self.course_b)
        theirs = self.create_for(self.b, self.course_b)
        with self.assertRaises(RecordNotFound):
            materials.retrieve(self.a, theirs.pk)
        with self.assertRaises(RecordNotFound):
            materials.update(self.a, theirs.pk, version=1, title="Changed")
        with self.assertRaises(RecordNotFound):
            materials.delete(self.a, theirs.pk, version=1)
        self.assertEqual(materials.retrieve(self.b, theirs.pk).title, "Synthetic notes")

    def test_server_owned_fields_are_rejected(self):
        for extra in ({"owner_id": self.b.student_id}, {"id": uuid.uuid4()}, {"record_version": 5}):
            with self.assertRaises(InvalidRecord):
                materials.create(self.a, course_id=self.course_a.pk, title="X", **FILE_FACTS, **extra)

    def test_invalid_file_facts_are_rejected(self):
        for bad in ({"file_type": "exe"}, {"size_bytes": 0}, {"original_filename": "../notes.txt"},
                    {"original_filename": "  "}):
            with self.assertRaises(InvalidRecord):
                materials.create(self.a, course_id=self.course_a.pk, title="X", **{**FILE_FACTS, **bad})

    def test_file_facts_cannot_change_after_upload(self):
        mine = self.create_for(self.a, self.course_a)
        for change in ({"original_filename": "other.pdf"}, {"file_type": "pdf"}, {"size_bytes": 5}):
            with self.assertRaises(InvalidRecord):
                materials.update(self.a, mine.pk, version=1, **change)
        self.assertEqual(materials.retrieve(self.a, mine.pk).size_bytes, 10)

    def test_rename_move_and_delete_own_material_with_versions(self):
        other = self.second_course_a()
        mine = self.create_for(self.a, self.course_a)
        changed = materials.update(self.a, mine.pk, version=1, title="Week 1", course_id=other.pk)
        self.assertEqual((changed.title, changed.course_id, changed.record_version), ("Week 1", other.pk, 2))
        with self.assertRaises(RecordConflict):
            materials.update(self.a, mine.pk, version=1, title="Stale tab")
        materials.delete(self.a, mine.pk, version=2)
        self.assertEqual(materials.list(self.a), [])

    def test_course_with_materials_cannot_be_deleted(self):
        other = self.second_course_a()
        self.create_for(self.a, other)
        with self.assertRaises(InvalidRecord):
            courses.delete(self.a, other.pk, version=1)