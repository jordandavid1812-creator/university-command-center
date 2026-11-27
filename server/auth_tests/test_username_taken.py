"""Open sign-up says when a USERNAME is taken (owner's choice), but never whether an EMAIL has an
account. Synthetic data on real PostgreSQL."""
from unittest.mock import patch
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from accounts import tokens
from accounts.models import SignupCode, Student
from .base import AuthenticationCase, PASSWORD
from .test_trusted_devices import ensure_latest_schema

TAKEN = 'That username is already taken. Please choose another.'


@override_settings(UCC_SIGNUP_CODE=True, UCC_REQUIRE_INVITE=False)
class UsernameTakenTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()
        self.make_student('existing-name')
        mail.outbox.clear()

    def register(self, **changes):
        values = {'full_name': 'Synthetic Person', 'username': 'existing-name', 'email': 'brand-new@example.invalid',
                  'password1': PASSWORD, 'password2': PASSWORD}
        values.update(changes)
        return self.client.post(reverse('accounts:register'), values)

    def test_a_taken_username_is_reported_and_the_other_answers_are_kept(self):
        page = self.register()
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, TAKEN)
        self.assertContains(page, 'value="brand-new@example.invalid"')
        self.assertContains(page, 'value="Synthetic Person"')
        self.assertNotContains(page, PASSWORD)  # passwords are never sent back
        self.assertNotContains(page, 'Enter your code')
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Student.objects.using('auth').filter(email='brand-new@example.invalid').exists())
        self.assertEqual(SignupCode.objects.using('auth').count(), 0)

    def test_choosing_another_username_then_works(self):
        self.register()
        page = self.register(username='fresh-name')
        self.assertContains(page, 'Enter your code')
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Student.objects.using('auth').filter(username='fresh-name').exists())

    def test_usernames_stay_case_sensitive_like_the_database(self):
        self.assertContains(self.register(username='Existing-Name'), 'Enter your code')

    def test_a_taken_email_is_still_never_revealed(self):
        first = self.register(username='first-name', email='same@example.invalid')
        mail.outbox.clear()
        again = self.register(username='second-name', email='SAME@example.invalid')
        self.assertNotContains(again, TAKEN)
        self.assertEqual(first.content.decode().count('Enter your code'), again.content.decode().count('Enter your code'))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Student.objects.using('auth').filter(username='second-name').exists())

    def test_a_username_taken_at_the_same_moment_is_still_reported(self):
        # The first check passes, the insert then hits the database's unique rule.
        with patch.object(tokens, '_username_taken', side_effect=[False, True]):
            self.assertContains(self.register(), TAKEN)
        self.assertEqual(mail.outbox, [])


@override_settings(UCC_REQUIRE_INVITE=True)
class InviteOnlyStaysGenericTests(AuthenticationCase):
    def test_invite_only_sign_up_never_reports_usernames(self):
        self.make_student('existing-name')
        self.assertFalse(tokens._username_taken({'username': 'existing-name'}))
