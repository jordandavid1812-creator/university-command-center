"""Settings: storage usage, owner-only "Download my data" export, and the sessions note."""
import json
from unittest.mock import patch
from django.db import connections
from django.urls import reverse
from academics import queries, services
from academics.models import StudyMaterial
from academics.ownership import OwnershipRequired
from .base import WebsiteCase


class SettingsDataTests(WebsiteCase):
    def add_material(self, identity, course, title, content=b'Synthetic notes'):
        return services.materials.create_with_file(identity, title=title, course_id=course.pk,
                                                   original_filename='notes.txt', file_type='txt', content=content)

    def export(self, client=None):
        return (client or self.client_a).get(reverse('student_web:data-export'))

    def test_storage_usage_shows_on_materials_and_settings(self):
        self.seed()
        self.add_material(self.identity_a, self.course_a, 'Week 1')
        for path in ('student_web:material-list', 'student_web:settings'):
            with self.subTest(path=path):
                page = self.client_a.get(reverse(path))
                self.assertContains(page, 'Storage used: 1 of 50 files')
                self.assertContains(page, '15\xa0bytes of 200 MiB')
        self.assertContains(self.client_b.get(reverse('student_web:settings')), 'Storage used: 0 of 50 files')

    def test_storage_counts_real_stored_bytes_not_the_recorded_size(self):
        self.seed()
        material = self.add_material(self.identity_a, self.course_a, 'Week 1')
        services.materials.create(self.identity_a, course_id=self.course_a.pk, title='Details only',
                                  original_filename='old.txt', file_type='txt', size_bytes=5000)
        # Make the recorded size differ from the stored bytes (the migrator briefly lifts forced RLS).
        with connections['default'].cursor() as cursor:
            cursor.execute('ALTER TABLE academics_studymaterial NO FORCE ROW LEVEL SECURITY')
            try:
                StudyMaterial.objects.using('default').filter(pk=material.pk).update(size_bytes=999)
            finally:
                cursor.execute('ALTER TABLE academics_studymaterial FORCE ROW LEVEL SECURITY')
        storage = services.materials.storage(self.identity_a)
        self.assertEqual((storage['files'], storage['bytes']), (1, len(b'Synthetic notes')))

    def test_settings_explains_how_to_sign_out_everywhere(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'Changing your password signs out every other session.')
        self.assertContains(page, reverse('student_web:data-export'))

    def test_export_is_an_owner_only_json_attachment(self):
        self.seed()
        services.profiles.create(self.identity_a, display_name='Ada')
        services.profiles.create(self.identity_b, display_name='Bravo profile')
        services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='TWO',
                                name='Synthetic half course', credit_units='2.5', actual_grade='A')
        self.add_material(self.identity_a, self.course_a, 'Week 1')
        self.add_material(self.identity_b, self.course_b, 'Other student file')
        response = self.export()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="ucc-my-data-'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', response['Cache-Control'])
        data = json.loads(response.content)
        self.assertEqual((data['format'], data['version']), ('university-command-center-export', 2))
        self.assertEqual(data['account']['username'], 'alpha')
        self.assertNotIn('matric_number', data['profile'])
        self.assertIn('full_name', data['account'])
        self.assertEqual(response['Content-Security-Policy'], "default-src 'none'; sandbox")
        self.assertEqual(data['semesters'][0]['label'], 'Synthetic A semester')
        self.assertEqual({c['name']: c['credit_units'] for c in data['courses']},
                         {'Synthetic A course': '3', 'Synthetic half course': '2.5'})  # float would give '3.0'
        self.assertEqual([a['title'] for a in data['assignments']], ['Synthetic A task'])
        self.assertEqual([(m['title'], m['file_stored']) for m in data['study_materials']], [('Week 1', True)])
        text = response.content.decode()
        for foreign in ('Synthetic B semester', 'Synthetic B course', 'Synthetic B task', 'Other student file',
                        'bravo', 'Bravo profile', 'SYN/OTHER/9999'):
            self.assertNotIn(foreign, text)
        # File contents and fingerprints never leave the server in the export.
        self.assertNotIn('Synthetic notes', text)
        self.assertNotIn('sha256', text)
        self.assertEqual(data['notes'], 'Study file contents are not included; download each stored file from Study materials.')

    def test_export_needs_sign_in_and_get(self):
        self.assertRedirects(self.export(self.client), reverse('accounts:login'), fetch_redirect_response=False)
        self.seed()
        self.assertEqual(self.client_a.post(reverse('student_web:data-export')).status_code, 405)
        for identity in (None, self.a.pk, {'student_id': self.a.pk}):
            with self.assertRaises(OwnershipRequired):
                queries.export_records(identity)

    def test_too_large_workspace_gets_a_clear_page_and_no_partial_file(self):
        self.seed()
        self.add_material(self.identity_a, self.course_a, 'Week 1')
        for limit in ('MAX_SEMESTERS', 'MAX_COURSES', 'MAX_EXPORT_ASSIGNMENTS', 'MAX_EXPORT_MATERIALS'):
            with self.subTest(limit=limit), patch.object(queries, limit, 0):
                response = self.export()
                self.assertContains(response, 'too large to export', status_code=413)
                self.assertNotIn('Content-Disposition', response)
        self.assertEqual(self.export().status_code, 200)

    def test_file_name_uses_the_local_date(self):
        from datetime import datetime, timezone as dt_timezone
        self.seed()
        # 23:30 UTC on 14 Nov is 00:30 on 15 Nov in Lagos.
        with patch('student_web.views.timezone.now', return_value=datetime(2026, 11, 14, 23, 30, tzinfo=dt_timezone.utc)):
            response = self.export()
        self.assertIn('ucc-my-data-2026-11-15.json', response['Content-Disposition'])
