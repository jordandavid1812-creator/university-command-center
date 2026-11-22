"""Launch step G: public privacy notice and terms of use, linked from every page and from sign-up."""
from django.urls import reverse
from .base import WebsiteCase


class LegalPageTests(WebsiteCase):
    def test_both_pages_are_public_and_need_no_javascript(self):
        for name, heading in (('accounts:privacy', 'Privacy notice'), ('accounts:terms', 'Terms of use')):
            with self.subTest(page=name):
                page = self.client.get(reverse(name))
                self.assertContains(page, f'<h1 id="{name.split(":")[1]}-heading">{heading}</h1>', html=False)
                self.assertContains(page, 'Last updated 22 November 2026')
                self.assertContains(page, 'mailto:unicommand.info@gmail.com')
                self.assertNotContains(page, '<form')

    def test_privacy_notice_states_the_real_data_flows(self):
        page = self.client.get(reverse('accounts:privacy'))
        for text in ('Nigeria Data Protection Act 2023', 'ndpc.gov.ng', 'Dublin, Ireland', 'Supabase',
                     'Google Gemini', "Gemini's free service", 'people at Google may read it',
                     'up to 60,000 characters', 'Export my data', '__Host-ucc_session', 'ucc_display',
                     'tracking or analytics cookies', 'GitHub', 'deleted automatically after 30 days'):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_pages_only_answer_get(self):
        for name in ('accounts:privacy', 'accounts:terms'):
            with self.subTest(page=name):
                self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    def test_footer_links_on_public_and_signed_in_pages(self):
        privacy, terms = reverse('accounts:privacy'), reverse('accounts:terms')
        login_page = self.client.get(reverse('accounts:login'))
        self.seed()
        dashboard = self.client_a.get(reverse('student_web:dashboard'))
        for page in (login_page, dashboard):
            self.assertContains(page, f'href="{privacy}"')
            self.assertContains(page, f'href="{terms}"')

    def test_sign_up_page_says_what_registering_agrees_to(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertContains(page, 'By creating an account you agree to the')
        self.assertNotContains(self.client.get(reverse('accounts:login')), 'By creating an account')
