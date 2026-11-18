"""The Content-Security-Policy header: sent on every page, and never weakens a stricter one."""
from django.test import Client
from django.urls import reverse
from accounts.middleware import CONTENT_SECURITY_POLICY
from academics import services
from .base import WebsiteCase

SANDBOX = "default-src 'none'; sandbox"


class ContentSecurityPolicyTests(WebsiteCase):
    def test_policy_allows_only_this_site(self):
        rules = dict(rule.split(' ', 1) for rule in CONTENT_SECURITY_POLICY.split('; '))
        self.assertEqual(rules['script-src'], "'self'")  # no inline or outside scripts
        self.assertEqual(rules['style-src-elem'], "'self'")  # no <style> blocks or outside sheets
        self.assertEqual(rules['object-src'], "'none'")
        self.assertEqual(rules['base-uri'], "'none'")
        self.assertEqual(rules['frame-ancestors'], "'none'")
        self.assertEqual(rules['form-action'], "'self'")
        self.assertNotIn('http', CONTENT_SECURITY_POLICY)
        self.assertNotIn("'unsafe-eval'", CONTENT_SECURITY_POLICY)
        self.assertNotIn('data:', CONTENT_SECURITY_POLICY)

    def test_every_student_page_sends_the_policy(self):
        self.seed()
        names = ('dashboard', 'semester-list', 'course-list', 'assignment-list', 'overview', 'predictor',
                 'planner', 'standing-print', 'settings', 'class-bands', 'material-list', 'material-upload',
                 'material-search', 'timetable', 'study-plans', 'study-plan-create')
        for name in names:
            with self.subTest(page=name):
                response = self.client_a.get(reverse(f'student_web:{name}'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Security-Policy'], CONTENT_SECURITY_POLICY)

    def test_signed_out_and_error_pages_send_the_policy(self):
        for path, status in (('/accounts/login/', 200), ('/accounts/register/', 200), ('/no-such-page/', 404)):
            with self.subTest(path=path):
                response = Client().get(path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response['Content-Security-Policy'], CONTENT_SECURITY_POLICY)

    def test_downloads_and_export_keep_their_stricter_sandbox(self):
        self.seed()
        material = services.materials.create_with_file(
            self.identity_a, title='Week 1', course_id=self.course_a.pk,
            original_filename='notes.txt', file_type='txt', content=b'Synthetic notes')
        for url in (reverse('student_web:material-download', args=[material.pk]),
                    reverse('student_web:data-export')):
            with self.subTest(url=url):
                response = self.client_a.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Security-Policy'], SANDBOX)
