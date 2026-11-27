"""The public welcome page at the main link: signed-out visitors see what the site does and how
to join; signed-in students still get their dashboard. No student data, never cached."""
from django.urls import reverse
from .base import WebsiteCase


class LandingPageTests(WebsiteCase):
    def test_signed_out_visitors_see_the_welcome_page(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, 'student_web/landing.html')
        for text in ('Your GPA, deadlines and study plans in one place.', 'Know your GPA and CGPA',
                     'Stay organised', 'Study help from your notes', 'Free and private', 'How it works'):
            self.assertContains(page, text)
        self.assertContains(page, f'href="{reverse("accounts:register")}"')
        self.assertContains(page, f'href="{reverse("accounts:login")}"')
        self.assertContains(page, f'href="{reverse("accounts:privacy")}"')
        self.assertContains(page, '/static/student_web/landing.css')
        self.assertIn('no-cache', page['Cache-Control'])  # the same address shows a private dashboard
        self.assertNotIn('Gemini', page.content.decode())  # the provider is named only in the privacy notice

    def test_it_works_without_javascript_and_has_one_main_heading(self):
        html = self.client.get('/').content.decode()
        self.assertEqual(html.count('<h1'), 1)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<form method="post"', html)

    def test_signed_in_students_still_get_their_dashboard(self):
        self.seed()
        page = self.client_a.get('/')
        self.assertTemplateUsed(page, 'student_web/dashboard.html')
        self.assertNotContains(page, 'Create a free account')

    def test_only_get_and_head(self):
        self.assertEqual(self.client.head('/').status_code, 200)
        self.assertEqual(self.client.post('/').status_code, 405)

    def test_a_stale_session_is_signed_out_rather_than_shown_the_dashboard(self):
        self.seed()
        self.client_a.post(reverse('accounts:logout'))
        page = self.client_a.get('/')
        self.assertTemplateUsed(page, 'student_web/landing.html')
