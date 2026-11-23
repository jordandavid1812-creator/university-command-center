"""Owner's choice: a required "I agree" box on sign-up (UCC_TERMS_TICK) and a slim essential-cookie
notice with an OK button (UCC_COOKIE_NOTICE). Both are on only in the public profiles. The notice
works without JavaScript and only remembers that OK was pressed. Synthetic identities only."""
from pathlib import Path
from django.test import override_settings
from django.urls import reverse
from accounts.models import Student
from .base import WebsiteCase

PASSWORD = 'Synthetic-pass-2026!'


class TermsTickTests(WebsiteCase):
    def register(self, **extra):
        values = {'username': 'tick-student', 'email': 'tick@example.invalid', 'password1': PASSWORD,
                  'password2': PASSWORD, **extra}
        return self.client.post(reverse('accounts:register'), values)

    @override_settings(UCC_TERMS_TICK=True)
    def test_the_box_is_required_and_links_to_both_documents(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertContains(page, 'name="agree_terms"')
        self.assertContains(page, 'required')
        self.assertContains(page, 'I agree to the Terms of use and have read the Privacy notice')
        self.assertContains(page, f'href="{reverse("accounts:terms")}"')
        self.assertContains(page, f'href="{reverse("accounts:privacy")}"')
        self.assertContains(page, '/static/student_web/notice.css')
        refused = self.register()
        self.assertContains(refused, 'Tick the box to agree to the Terms of use and Privacy notice.')
        self.assertFalse(Student.objects.using('default').filter(username='tick-student').exists())
        self.register(agree_terms='on')
        self.assertTrue(Student.objects.using('default').filter(username='tick-student').exists())

    def test_off_unless_the_public_profile_turns_it_on(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertNotContains(page, 'agree_terms')
        self.assertContains(page, 'By creating an account you agree to the')

    def test_the_public_profiles_turn_both_on(self):
        from config.settings import auth_common, public_site
        source = Path(public_site.__file__).read_text()
        self.assertIn("namespace['UCC_TERMS_TICK'] = True", source)
        self.assertIn("namespace['UCC_COOKIE_NOTICE'] = True", source)
        defaults = Path(auth_common.__file__).read_text()
        self.assertIn('UCC_TERMS_TICK=False', defaults)
        self.assertIn('UCC_COOKIE_NOTICE=False', defaults)


@override_settings(UCC_COOKIE_NOTICE=True)
class CookieNoticeTests(WebsiteCase):
    def ok(self, target):
        return self.client.post(reverse('student_web:cookie-notice-ok'), {'next': target})

    def test_shown_until_ok_then_remembered(self):
        login = reverse('accounts:login')
        page = self.client.get(login)
        self.assertContains(page, 'class="cookie-notice"')
        self.assertContains(page, 'We only use essential cookies')
        self.assertContains(page, f'action="{reverse("student_web:cookie-notice-ok")}"')
        self.assertContains(page, 'csrfmiddlewaretoken')
        self.assertContains(page, f'href="{reverse("accounts:privacy")}#cookies"')
        self.assertContains(page, '/static/student_web/notice.css')
        response = self.ok(login)
        self.assertRedirects(response, login, fetch_redirect_response=False)
        cookie = response.cookies['ucc_cookie_ok']
        self.assertEqual(cookie.value, '1')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(int(cookie['max-age']), 365 * 24 * 60 * 60)
        after = self.client.get(login)
        self.assertNotContains(after, 'class="cookie-notice"')
        self.assertNotContains(after, 'notice.css')

    def test_also_on_signed_in_pages(self):
        self.login()
        self.assertContains(self.client_a.get(reverse('student_web:dashboard')), 'class="cookie-notice"')

    def test_only_same_site_paths_are_followed(self):
        for target in ('https://evil.example.invalid/', '//evil.example.invalid/x', 'javascript:alert(1)', ''):
            with self.subTest(target=target):
                self.assertRedirects(self.ok(target), '/', fetch_redirect_response=False)

    def test_only_post_and_other_cookie_values_still_show_it(self):
        self.assertEqual(self.client.get(reverse('student_web:cookie-notice-ok')).status_code, 405)
        self.client.cookies['ucc_cookie_ok'] = 'yes'
        self.assertContains(self.client.get(reverse('accounts:login')), 'class="cookie-notice"')

    @override_settings(UCC_COOKIE_NOTICE=False)
    def test_off_unless_the_public_profile_turns_it_on(self):
        page = self.client.get(reverse('accounts:login'))
        self.assertNotContains(page, 'cookie-notice')
        self.assertNotContains(page, 'notice.css')

    def test_the_privacy_notice_lists_the_cookie(self):
        page = self.client.get(reverse('accounts:privacy'))
        self.assertContains(page, '<h2 id="cookies">Cookies</h2>', html=False)
        self.assertContains(page, '<code>ucc_cookie_ok</code>', html=False)
        self.assertContains(page, 'Last updated 23 November 2026')
