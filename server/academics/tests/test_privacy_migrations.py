"""Destructive ID removal is rehearsed on the disposable foundation database only."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from accounts.models import Student


class PrivacyMigrationTests(TransactionTestCase):
    def test_upgrade_erases_matric_preserves_academics_and_reverse_cannot_recover_it(self):
        self.assertEqual(connection.vendor, 'postgresql')
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [('academics', '0025_profile_grading_scale')]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            student = Student.objects.create(username='synthetic.migration', email='migration@example.invalid',
                                             full_name='Existing Self Reported Name', password='!synthetic-unusable')
            profile = old.get_model('academics', 'StudentProfile').objects.create(
                owner_id=student.pk, display_name='Existing nickname', matric_number='SYNTHETIC-ID-REMOVE')
            semester = old.get_model('academics', 'Semester').objects.create(owner_id=student.pk, label='Synthetic')
            course = old.get_model('academics', 'Course').objects.create(owner_id=student.pk, semester_id=semester.pk,
                original_code='SYN101', normalized_code='SYN101', name='Synthetic Course', credit_units=3, actual_grade='B')
            executor = MigrationExecutor(connection);executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            Profile = new.get_model('academics', 'StudentProfile')
            self.assertNotIn('matric_number', {f.name for f in Profile._meta.fields})
            self.assertEqual(Profile.objects.get(pk=profile.pk).display_name, 'Existing nickname')
            saved = new.get_model('academics', 'Course').objects.get(pk=course.pk)
            self.assertEqual((saved.actual_grade, saved.credit_units), ('B', 3))
            student.refresh_from_db()
            self.assertEqual((student.full_name, student.password), ('Existing Self Reported Name', '!synthetic-unusable'))
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_attribute WHERE attrelid='academics_studentprofile'::regclass AND attname='matric_number' AND NOT attisdropped")
                self.assertEqual(cursor.fetchone(), (0,))
            # Reversal recreates a blank column; it cannot undo erasure of the original ID.
            executor = MigrationExecutor(connection);executor.migrate(previous)
            restored = executor.loader.project_state(previous).apps.get_model('academics', 'StudentProfile')
            self.assertEqual(restored.objects.get(pk=profile.pk).matric_number, '')
        finally:
            MigrationExecutor(connection).migrate(latest)
