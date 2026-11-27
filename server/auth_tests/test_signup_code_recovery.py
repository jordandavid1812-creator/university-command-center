"""A student is never stuck with an expired code (owner's choice): entering an expired or locked
code emails a fresh one automatically, within the resend limit, with the same reply for every
email so nothing about accounts is revealed. Synthetic data on real PostgreSQL."""
from datetime import timedelta
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import SignupCode
from .base import AuthenticationCase
from .test_signup_codes import EMAIL, SignupCodeTests
from .test_trusted_devices import ensure_latest_schema

NEW_ONE = 'we have just emailed you a new one'


@override_settings(UCC_SIGNUP_CODE=True)
class SignupCodeRecoveryTests(AuthenticationCase):
    register = SignupCodeTests.register
    emailed_code = SignupCodeTests.emailed_code
    enter = SignupCodeTests.enter
    verified = SignupCodeTests.verified
    wrong = SignupCodeTests.wrong

    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def expire(self):
        past = timezone.now() - timedelta(minutes=10)
        SignupCode.objects.using('default').update(created_at=past, expires_at=past + timedelta(minutes=5))

    def test_an_expired_code_brings_a_fresh_one_that_works(self):
        self.register()
        old = self.emailed_code()
        self.expire()
        page = self.enter(old)
        self.assertContains(page, 'wrong or has expired')
        self.assertContains(page, NEW_ONE)
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse(self.verified())
        self.assertContains(self.enter(self.emailed_code()), 'Email confirmed')

    def test_a_wrong_guess_on_a_live_code_sends_nothing(self):
        self.register()
        code = self.emailed_code()
        self.enter(self.wrong(code))
        self.assertEqual(len(mail.outbox), 1)

    def test_the_guess_that_locks_the_code_sends_nothing_but_the_next_try_does(self):
        self.register()
        code = self.emailed_code()
        for _ in range(5):
            self.enter(self.wrong(code))
        self.assertEqual(len(mail.outbox), 1)
        self.enter(code)  # locked: a fresh code is sent
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(self.enter(self.emailed_code()), 'Email confirmed')

    def test_same_reply_and_no_email_for_unknown_or_confirmed_addresses(self):
        unknown = self.enter('123456', email='nobody@example.invalid')
        self.assertContains(unknown, NEW_ONE)
        self.register()
        self.enter(self.emailed_code())  # confirmed now
        mail.outbox = []
        self.expire()
        self.assertContains(self.enter('123456'), NEW_ONE)
        self.assertEqual(mail.outbox, [])

    def test_badly_formed_codes_never_send(self):
        self.register()
        self.expire()
        for value in ('', '12345', 'abcdef'):
            self.enter(value)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(AUTH_RATE_LIMITS={'verify-code': (20, 3600), 'register': (5, 3600), 'resend': (1, 3600)})
    def test_automatic_codes_respect_the_resend_limit(self):
        self.register()
        self.expire()
        self.enter('000000')
        self.assertEqual(len(mail.outbox), 2)
        self.expire()
        self.enter('000000')
        self.assertEqual(len(mail.outbox), 2)  # limit reached: no third email

    def test_the_code_page_keeps_the_email_and_explains_the_options(self):
        page = self.register()
        self.assertContains(page, f'value="{EMAIL}"')
        self.assertContains(page, 'autocomplete="email"')
        self.assertContains(page, 'Code expired? Just enter it anyway')
        self.assertContains(page, 'Send me a new code')
        again = self.enter('000000')
        self.assertContains(again, f'value="{EMAIL}"')  # still filled in after a failed try
        self.assertContains(self.client.get(reverse('accounts:verify-code')), 'autocomplete="email"')
