"""Launch step F: Settings → Delete account. Password and the word DELETE are required; everything
goes in one transaction; the student is signed out and emailed; nobody else is touched."""
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from academics import services
from accounts.models import Student
from auth_tests.base import PASSWORD
from .base import WebsiteCase


class AccountDeletePageTests(WebsiteCase):
    def url(self):
        return reverse('student_web:account-delete')

    def delete(self, password=PASSWORD, confirm='DELETE', client=None):
        return (client or self.client_a).post(self.url(), {'password': password, 'confirm': confirm})

    def exists(self, name):
        return Student.objects.using('default').filter(username=name).exists()

    def test_signed_out_visitors_are_sent_to_login(self):
        self.assertRedirects(self.client.get(self.url()), reverse('accounts:login'), fetch_redirect_response=False)
        self.assertEqual(self.client.post(self.url(), {'password': PASSWORD, 'confirm': 'DELETE'}).status_code, 302)

    def test_settings_links_to_a_clear_warning_page_that_works_without_javascript(self):
        self.seed()
        self.assertContains(self.client_a.get(reverse('student_web:settings')), f'href="{self.url()}"')
        page = self.client_a.get(self.url())
        self.assertContains(page, 'This cannot be undone')
        self.assertContains(page, '<form method="post"', html=False)
        self.assertContains(page, 'name="password"')
        self.assertContains(page, reverse('student_web:data-export'))
        self.assertNotContains(page, '<script>')

    def test_wrong_password_or_missing_word_deletes_nothing(self):
        self.seed()
        self.assertContains(self.delete(password='Wrong-Passphrase-99'), 'That password is not right', status_code=400)
        self.assertContains(self.delete(confirm='delete'), 'Type DELETE in capital letters', status_code=400)
        self.assertContains(self.delete(confirm=''), 'Type DELETE', status_code=400)
        self.assertTrue(self.exists('alpha'))
        self.assertEqual(len(services.semesters.list(self.identity_a)), 1)
        self.assertEqual(mail.outbox, [])

    def test_deleting_removes_the_account_signs_out_and_emails_and_leaves_others(self):
        self.seed()
        bravo_semesters = len(services.semesters.list(self.identity_b))
        response = self.delete()
        self.assertContains(response, 'have been deleted')
        self.assertFalse(self.exists('alpha'))
        self.assertTrue(self.exists('bravo'))
        self.assertEqual(len(services.semesters.list(self.identity_b)), bravo_semesters)
        self.assertEqual(self.client_a.get(reverse('student_web:dashboard')).status_code, 302)  # signed out
        self.assertEqual(self.login(self.client_a).status_code, 200)  # the account is gone
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alpha@example.invalid'])
        self.assertIn('was deleted', mail.outbox[0].subject)
        self.assertEqual(self.client_b.get(reverse('student_web:dashboard')).status_code, 200)

    def test_extra_fields_are_refused(self):
        self.seed()
        response = self.client_a.post(self.url(), {'password': PASSWORD, 'confirm': 'DELETE', 'student_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.exists('alpha'))

    @override_settings(AUTH_RATE_LIMITS={'delete-account': (2, 60), 'login': (10, 900)})
    def test_attempts_are_rate_limited(self):
        self.seed()
        statuses = [self.delete(password='Wrong-Passphrase-99').status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])
        self.assertTrue(self.exists('alpha'))
