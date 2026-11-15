"""Display modes: System (default), Light and Dark, remembered in this browser only."""
from django.urls import reverse
from .base import WebsiteCase

DARK = 'student_web/theme-dark.css'
SYSTEM_MEDIA = 'media="screen and (prefers-color-scheme: dark)"'


class DisplayThemeTests(WebsiteCase):
    def choose(self, theme, client=None):
        return (client or self.client_a).post(reverse('student_web:display-preference'), {'theme': theme})

    def test_default_is_system_and_follows_the_device(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:dashboard'))
        self.assertContains(page, DARK)
        self.assertContains(page, SYSTEM_MEDIA)
        login = self.client.get(reverse('accounts:login'))
        self.assertContains(login, SYSTEM_MEDIA)

    def test_dark_and_light_are_saved_in_this_browser(self):
        self.seed()
        response = self.choose('dark')
        self.assertRedirects(response, reverse('student_web:settings'), fetch_redirect_response=False)
        cookie = response.cookies['ucc_display']
        self.assertEqual(cookie.value, 'dark')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'media="screen"')
        self.assertNotContains(page, SYSTEM_MEDIA)
        self.assertContains(page, 'Display set to Dark.')
        self.assertRegex(page.content.decode(), r'value="dark"[^>]*checked')
        self.choose('light')
        self.assertNotContains(self.client_a.get(reverse('student_web:dashboard')), DARK)

    def test_unknown_or_tampered_values_are_refused_or_ignored(self):
        self.seed()
        self.assertEqual(self.choose('purple').status_code, 400)
        self.assertNotIn('ucc_display', self.client_a.cookies)
        self.client_a.cookies['ucc_display'] = '"><script>'
        page = self.client_a.get(reverse('student_web:dashboard'))
        self.assertContains(page, SYSTEM_MEDIA)
        self.assertNotContains(page, '"><script>')

    def test_switch_needs_sign_in_post_and_csrf(self):
        self.assertRedirects(self.choose('dark', self.client), reverse('accounts:login'), fetch_redirect_response=False)
        self.seed()
        self.assertEqual(self.client_a.get(reverse('student_web:display-preference')).status_code, 405)
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client_a.cookies
        self.assertEqual(strict.post(reverse('student_web:display-preference'), {'theme': 'dark'}).status_code, 403)

    def test_print_and_settings_form_work_without_javascript(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, '<form method="post" action="%s"' % reverse('student_web:display-preference'))
        for value in ('system', 'light', 'dark'):
            self.assertContains(page, 'value="%s"' % value)
        self.assertNotContains(page, 'media="print')
