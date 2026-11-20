"""Edit profile: owner-only, optional fields, no student ID collection, dashboard greeting."""
from django.urls import reverse
from academics import services
from .base import WebsiteCase

FIELDS = {'display_name': 'Ada', 'institution': 'Synthetic University', 'programme': 'B.Sc. Testing',
          'level': '200'}


class ProfilePageTests(WebsiteCase):
    def save(self, client=None, **changes):
        return (client or self.client_a).post(reverse('student_web:profile-edit'), dict(FIELDS, **changes))

    def test_signed_out_visitors_are_sent_to_login(self):
        self.assertRedirects(self.client.get(reverse('student_web:profile-edit')), reverse('accounts:login'),
                             fetch_redirect_response=False)

    def test_first_save_creates_profile_without_collecting_student_id(self):
        self.seed()
        self.assertContains(self.client_a.get(reverse('student_web:settings')), 'Not set')
        self.assertRedirects(self.save(), reverse('student_web:settings'), fetch_redirect_response=False)
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'Profile saved.')
        self.assertContains(page, 'Synthetic University')
        self.assertContains(page, '200 level')
        self.assertNotContains(page, 'Matric / student ID')
        self.assertNotContains(page, 'SYN/2026/123456')

    def test_edit_form_shows_own_values_and_other_students_never_see_them(self):
        self.seed()
        self.save()
        self.assertContains(self.client_a.get(reverse('student_web:profile-edit')), 'Ada')
        for path in ('student_web:settings', 'student_web:profile-edit', 'student_web:dashboard'):
            page = self.client_b.get(reverse(path))
            self.assertNotContains(page, 'Synthetic University')
            self.assertNotContains(page, 'Ada')

    def test_dashboard_greets_by_display_name_or_username(self):
        self.seed()
        self.assertContains(self.client_a.get(reverse('student_web:dashboard')), 'Welcome back, alpha.')
        self.save()
        self.assertContains(self.client_a.get(reverse('student_web:dashboard')), 'Welcome back, Ada.')

    def test_updates_are_versioned_and_all_fields_are_optional(self):
        self.seed()
        self.save()
        profile = services.profiles.current(self.identity_a)
        blank = {name: '' for name in FIELDS}
        response = self.client_a.post(reverse('student_web:profile-edit'), dict(blank, version=1))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(services.profiles.current(self.identity_a).display_name, '')
        stale = self.client_a.post(reverse('student_web:profile-edit'), dict(FIELDS, version=1))
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(profile.pk, services.profiles.current(self.identity_a).pk)

    def test_bad_values_and_extra_fields_are_refused(self):
        self.seed()
        for changes in ({'matric_number': 'SYN 2026'}, {'level': '900'}, {'display_name': 'A\x07B'},
                        {'display_name': 'x' * 81}, {'owner_id': 'anything'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.save(**changes).status_code, 400)
        self.assertIsNone(services.profiles.current(self.identity_a))

    def test_single_dashboard_read_rejects_missing_and_forged_context(self):
        from datetime import date
        from academics import queries
        from academics.ownership import OwnershipRequired
        self.seed()
        for identity in (None, self.a.pk, {'student_id': self.a.pk}):
            with self.assertRaises(OwnershipRequired):
                queries.dashboard_reads(identity, date(2026, 12, 1))

    def test_dashboard_verifies_the_student_exactly_once(self):
        from django.db import connections
        from django.test.utils import CaptureQueriesContext
        self.seed()
        self.save()
        self.client_a.get(reverse('student_web:dashboard'))
        with CaptureQueriesContext(connections['runtime']) as queries:
            self.assertContains(self.client_a.get(reverse('student_web:dashboard')), 'Welcome back, Ada.')
        verifications = [q for q in queries.captured_queries if 'ucc_security.current_student()' in q['sql']
                         and q['sql'].lstrip().upper().startswith('SELECT UCC_SECURITY')]
        self.assertEqual(len(verifications), 1)

    def test_legacy_matric_submissions_are_refused_and_not_stored(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:profile-edit'))
        self.assertNotContains(page, 'name="matric_number"')
        for value in ('AB12', 'SYN/2026/1234', 'ABC12345'):
            with self.subTest(value=value):
                self.assertEqual(self.save(matric_number=value).status_code, 400)
                self.assertIsNone(services.profiles.current(self.identity_a))
