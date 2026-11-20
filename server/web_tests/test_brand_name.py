"""The site is called UniCommand (owner's choice, was University Command Center). Students see
only the new name; the privacy notice and terms say what it was called before."""
from django.urls import reverse
from .base import WebsiteCase

OLD = 'University Command Center'


class BrandNameTests(WebsiteCase):
    def test_public_pages_use_the_new_name(self):
        for url in ('/', reverse('accounts:login'), reverse('accounts:register')):
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertContains(page, 'UniCommand')
                self.assertNotContains(page, OLD)

    def test_workspace_pages_use_the_new_name(self):
        self.seed()
        for name in ('dashboard', 'course-list', 'settings'):
            with self.subTest(page=name):
                page = self.client_a.get(reverse(f'student_web:{name}'))
                self.assertContains(page, '<span>UniCommand</span>', html=False)
                self.assertNotContains(page, OLD)

    def test_privacy_and_terms_say_what_it_was_called(self):
        for url in (reverse('accounts:privacy'), reverse('accounts:terms')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn('UniCommand (formerly called University Command Center)', html)
                self.assertEqual(html.count(OLD), 1)
