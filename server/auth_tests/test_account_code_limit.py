"""At most ACCOUNT_CODES_PER_HOUR code emails per account per hour (owner's choice), whatever
network asks, with the same reply. Synthetic data on real PostgreSQL."""
from datetime import timedelta
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from accounts import signup_codes
from accounts.models import SignupCode
from .base import AuthenticationCase
from .test_signup_codes import EMAIL, SignupCodeTests
from .test_trusted_devices import ensure_latest_schema

WIDE = {'verify-code': (100, 3600), 'register': (100, 3600), 'resend': (100, 3600)}


@override_settings(UCC_SIGNUP_CODE=True, AUTH_RATE_LIMITS=dict(WIDE, login=(100, 900), reset=(100, 3600),
                   verify=(100, 3600), **{'reset-confirm': (100, 3600), 'password-change': (100, 900),
                   'delete-account': (100, 3600), 'change-email': (100, 3600), 'change-email-code': (100, 3600)}))
class AccountCodeLimitTests(AuthenticationCase):
    register = SignupCodeTests.register
    emailed_code = SignupCodeTests.emailed_code
    enter = SignupCodeTests.enter
    verified = SignupCodeTests.verified

    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def test_the_sixth_code_in_an_hour_is_not_sent_but_the_reply_is_the_same(self):
        self.assertEqual(signup_codes.ACCOUNT_CODES_PER_HOUR, 5)
        self.register()
        for _ in range(4):
            self.assertContains(self.enter('', action='resend'), 'sent it a 6-digit code')
        self.assertEqual(len(mail.outbox), 5)
        newest = self.emailed_code()
        self.assertContains(self.enter('', action='resend'), 'sent it a 6-digit code')
        self.assertEqual(len(mail.outbox), 5)  # nothing more is sent
        self.assertContains(self.enter(newest), 'Email confirmed')  # and the last code still works

    def test_the_limit_resets_after_an_hour(self):
        self.register()
        for _ in range(4):
            self.enter('', action='resend')
        earlier = timezone.now() - timedelta(minutes=61)
        SignupCode.objects.using('default').update(created_at=earlier, expires_at=earlier + timedelta(minutes=5))
        self.enter('', action='resend')
        self.assertEqual(len(mail.outbox), 6)
