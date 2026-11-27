"""Sign-up codes last 5 minutes (owner's choice, was 1) and the code page says where to look."""
from datetime import timedelta
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from accounts import signup_codes
from accounts.models import SignupCode
from .base import AuthenticationCase
from .test_signup_codes import SignupCodeTests
from .test_trusted_devices import ensure_latest_schema


@override_settings(UCC_SIGNUP_CODE=True)
class SignupCodeTimeTests(AuthenticationCase):
    # Reuse the original helpers only (not its tests, which run in their own module).
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    register = SignupCodeTests.register
    emailed_code = SignupCodeTests.emailed_code
    enter = SignupCodeTests.enter
    verified = SignupCodeTests.verified

    def test_the_code_works_for_five_minutes_and_the_email_and_page_say_so(self):
        self.assertEqual(signup_codes.LIFETIME, timedelta(minutes=5))
        page = self.register()
        self.assertContains(page, 'It works for 5 minutes.')
        self.assertContains(page, 'Each code works for 5 minutes')
        self.assertContains(page, 'Check your Spam or Promotions folder')
        self.assertNotContains(page, '1 minute')
        self.assertIn('It works for 5 minutes.', mail.outbox[-1].body)
        self.assertIn('It works for 5 minutes.', mail.outbox[-1].alternatives[0][0])

    def test_a_code_found_four_minutes_later_still_works(self):
        self.register()
        code = self.emailed_code()
        late = timezone.now() - timedelta(minutes=4)
        SignupCode.objects.using('default').update(created_at=late, expires_at=late + signup_codes.LIFETIME)
        self.assertFalse(self.verified())
        self.enter(code)
        self.assertTrue(self.verified())

    def test_an_expired_five_minute_code_is_refused(self):
        self.register()
        code = self.emailed_code()
        old = timezone.now() - timedelta(minutes=5, seconds=1)
        SignupCode.objects.using('default').update(created_at=old, expires_at=old + signup_codes.LIFETIME)
        self.assertContains(self.enter(code), 'wrong or has expired')
        self.assertFalse(self.verified())

    def test_the_hint_is_on_the_code_page_itself(self):
        self.assertContains(self.client.get(reverse('accounts:verify-code')), 'mark it')

