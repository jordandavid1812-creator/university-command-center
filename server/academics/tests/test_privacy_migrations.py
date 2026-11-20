"""Rehearse additive name/profile compatibility on a disposable PostgreSQL database."""
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PrivacyMigrationTests(TransactionTestCase):
    def test_expand_supports_old_and_new_code_and_reverse_preserves_legacy_data(self):
        self.assertEqual(connection.vendor, 'postgresql')
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(latest)  # Other migration tests may leave an earlier academic schema.
        executor = MigrationExecutor(connection)  # Reload the applied-migration state.
        previous = [('accounts', '0006_signup_code_new_email'), ('academics', '0025_profile_grading_scale')]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            OldStudent = old.get_model('accounts', 'Student')
            OldProfile = old.get_model('academics', 'StudentProfile')
            student = OldStudent.objects.create(username='synthetic.migration', email='migration@example.invalid',
                                                 password='!synthetic-unusable')
            profile = OldProfile.objects.create(owner_id=student.pk, display_name='Existing nickname',
                                                matric_number='SYNTHETIC-LEGACY-ID')
            semester = old.get_model('academics', 'Semester').objects.create(owner_id=student.pk, label='Synthetic')
            course = old.get_model('academics', 'Course').objects.create(owner_id=student.pk, semester_id=semester.pk,
                original_code='SYN101', normalized_code='SYN101', name='Synthetic Course', credit_units=3, actual_grade='B')
            executor = MigrationExecutor(connection);executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            Student = new.get_model('accounts', 'Student')
            Profile = new.get_model('academics', 'StudentProfile')
            self.assertEqual(Student.objects.get(pk=student.pk).full_name, '')
            # Negative control: without the DB default, the real old ORM insert fails.
            # Roll back both the synthetic failed INSERT and its DDL change in a savepoint.
            with self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('ALTER TABLE accounts_student ALTER COLUMN full_name DROP DEFAULT')
                OldStudent.objects.create(username='synthetic.without.default', password='!synthetic')
            # Old signup omits the new field: a persistent DB default must keep it working.
            legacy_signup = OldStudent.objects.create(username='synthetic.old.signup', password='!synthetic')
            self.assertEqual(Student.objects.get(pk=legacy_signup.pk).full_name, '')
            old_profile = OldProfile.objects.get(pk=profile.pk)
            old_profile.display_name = 'Old code still works';old_profile.save()
            self.assertEqual(Profile.objects.get(pk=profile.pk).matric_number, 'SYNTHETIC-LEGACY-ID')
            # New profile creation need not collect an ID; the retained column defaults blank.
            new_student = Student.objects.create(username='synthetic.new.signup', password='!synthetic', full_name='Self Reported Name')
            new_profile = Profile.objects.create(owner_id=new_student.pk)
            self.assertEqual(new_profile.matric_number, '')
            for table, column in [('accounts_student', 'full_name'), ('academics_studentprofile', 'matric_number')]:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT column_default FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s', ['public', table, column])
                    self.assertEqual(cursor.fetchone(), ("''::character varying",))
            saved = new.get_model('academics', 'Course').objects.get(pk=course.pk)
            self.assertEqual((saved.actual_grade, saved.credit_units), ('B', 3))
            # Reverse only on this disposable database, never a proposed production action.
            MigrationExecutor(connection).migrate(previous)
            self.assertEqual(OldProfile.objects.get(pk=profile.pk).matric_number, 'SYNTHETIC-LEGACY-ID')
            self.assertTrue(OldStudent.objects.filter(pk=new_student.pk).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
