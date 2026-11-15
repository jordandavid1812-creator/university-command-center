"""Settings: storage usage, owner-only "Download my data" export, and the sessions note."""
import json
from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from academics import queries, services
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
                self.assertContains(page, '15\xa0bytes of 200.0\xa0MB')
        self.assertContains(self.client_b.get(reverse('student_web:settings')), 'Storage used: 0 of 50 files')

    def test_settings_explains_how_to_sign_out_everywhere(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'Changing your password signs out every other session.')
        self.assertContains(page, reverse('student_web:data-export'))

    def test_export_is_an_owner_only_json_attachment(self):
        self.seed()
        services.profiles.create(self.identity_a, display_name='Ada', matric_number='SYN/2026/1234')
        self.add_material(self.identity_a, self.course_a, 'Week 1')
        self.add_material(self.identity_b, self.course_b, 'Other student file')
        response = self.export()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="ucc-my-data-'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', response['Cache-Control'])
        data = json.loads(response.content)
        self.assertEqual((data['format'], data['version']), ('university-command-center-export', 1))
        self.assertEqual(data['account']['username'], 'alpha')
        self.assertEqual(data['profile']['matric_number'], 'SYN/2026/1234')
        self.assertEqual([c['name'] for c in data['courses']], ['Synthetic A course'])
        self.assertIsInstance(data['courses'][0]['credit_units'], str)
        self.assertEqual(Decimal(data['courses'][0]['credit_units']), Decimal('3'))
        self.assertEqual([a['title'] for a in data['assignments']], ['Synthetic A task'])
        self.assertEqual([(m['title'], m['file_stored']) for m in data['study_materials']], [('Week 1', True)])
        text = response.content.decode()
        for foreign in ('Synthetic B course', 'Synthetic B task', 'Other student file', 'bravo'):
            self.assertNotIn(foreign, text)

    def test_export_needs_sign_in_and_get(self):
        self.assertRedirects(self.export(self.client), reverse('accounts:login'), fetch_redirect_response=False)
        self.seed()
        self.assertEqual(self.client_a.post(reverse('student_web:data-export')).status_code, 405)
        for identity in (None, self.a.pk, {'student_id': self.a.pk}):
            with self.assertRaises(OwnershipRequired):
                queries.export_records(identity)

    def test_too_large_workspace_gets_a_clear_page_and_no_partial_file(self):
        self.seed()
        with patch.object(queries, 'MAX_EXPORT_ASSIGNMENTS', 0):
            response = self.export()
        self.assertContains(response, 'too large to export', status_code=413)
        self.assertNotIn('Content-Disposition', response)
