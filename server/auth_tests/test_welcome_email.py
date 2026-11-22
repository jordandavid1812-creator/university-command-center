"""One welcome email after a student confirms their email (owner's choice). Public profiles only
(UCC_WELCOME_EMAIL); sent after the confirming transaction commits, exactly once; a delivery failure
never affects sign-up. Real PostgreSQL, synthetic identities, in-memory email only."""
import re
from contextlib import nullcontext as committed  # real transactions: on_commit runs as in production
from unittest.mock import patch
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from accounts import welcome
from accounts.models import Student
from .base import AuthenticationCase, PASSWORD
from .test_trusted_devices import ensure_latest_schema

EMAIL = 'welcome@example.invalid'


@override_settings(UCC_SIGNUP_CODE=True, UCC_WELCOME_EMAIL=True)
class WelcomeEmailTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def register(self):
        return self.client.post(reverse('accounts:register'), {
            'username': 'welcome-student', 'email': EMAIL, 'password1': PASSWORD, 'password2': PASSWORD})

    def code(self):
        return re.search(r'code is (\d{6})\b', mail.outbox[-1].body).group(1)

    def enter(self, code):
        return self.client.post(reverse('accounts:verify-code'), {'email': EMAIL, 'code': code, 'action': 'verify'})

    def welcomes(self):
        return [message for message in mail.outbox if message.subject == welcome.SUBJECT]

    def test_confirming_sends_one_welcome_with_three_steps_and_a_link(self):
        self.register()
        code = self.code()
        self.assertEqual(self.welcomes(), [])  # nothing before the email is confirmed
        with committed():
            self.assertContains(self.enter(code), 'Email confirmed')
        [message] = self.welcomes()
        self.assertEqual(message.to, [EMAIL])
        for text in ("You're in!", '1. Add your courses', '2. Upload one lecture note', '3. Set your target',
                     'Mistake bank', 'Get started'):
            self.assertIn(text, message.body)
        self.assertNotIn(code, message.body)
        self.assertNotIn('welcome-student', message.body)  # no username in the email
        html = message.alternatives[0][0]
        self.assertIn("You're in! &#127881;</h1>", html)
        self.assertIn('Open my dashboard</a>', html)
        self.assertIn('Three quick steps', html)
        for forbidden in ('<img', '<script', 'url(', '@import'):  # no images, tracking or external files
            self.assertNotIn(forbidden, html)
        from django.conf import settings
        site = settings.AUTH_LINK_ORIGIN.rstrip('/') + '/'
        self.assertEqual(set(re.findall(r'href="([^"]+)"', html)), {site})  # only the site itself, no tracking
        self.assertIn(site, message.body)

    def test_only_once_and_not_for_a_wrong_code(self):
        self.register()
        code = self.code()
        wrong = f'{(int(code) + 1) % 1_000_000:06d}'
        with committed():
            self.enter(wrong)
        self.assertEqual(self.welcomes(), [])
        with committed():
            self.enter(code)
        with committed():
            self.enter(code)  # already used
        self.assertEqual(len(self.welcomes()), 1)

    @override_settings(UCC_WELCOME_EMAIL=False)
    def test_off_unless_the_public_profile_turns_it_on(self):
        self.register()
        with committed():
            self.assertContains(self.enter(self.code()), 'Email confirmed')
        self.assertEqual(self.welcomes(), [])

    def test_a_delivery_failure_never_affects_sign_up_or_logs_details(self):
        self.register()
        code = self.code()
        with patch('accounts.welcome.send_mail', side_effect=OSError('smtp down for welcome@example.invalid')), \
                self.assertLogs('accounts.welcome', level='WARNING') as logs, \
                committed():
            self.assertContains(self.enter(code), 'Email confirmed')
        self.assertTrue(Student.objects.using('default').get(username='welcome-student').email_verified_at)
        self.assertNotIn(EMAIL, '\n'.join(logs.output))
        self.assertNotIn('smtp down', '\n'.join(logs.output))

    def test_the_public_profiles_turn_it_on(self):
        from pathlib import Path
        from config.settings import auth_common, public_site
        self.assertIn("namespace['UCC_WELCOME_EMAIL'] = True", Path(public_site.__file__).read_text())
        self.assertIn('UCC_WELCOME_EMAIL=False', Path(auth_common.__file__).read_text())  # local and tests: off

    def test_the_privacy_notice_mentions_it(self):
        self.assertContains(self.client.get(reverse('accounts:privacy')), 'one welcome email with tips')
