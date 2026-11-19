"""Open sign-up with a 6-digit email code (1 minute, 5 tries), on real PostgreSQL with the
separate auth and runtime roles. Synthetic identities only."""
from datetime import timedelta
import os
import re
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from academics.ownership import require_runtime_role
from accounts import signup_codes
from accounts.boundary import require_auth_role
from accounts.models import AccountToken, SignupCode, Student
from .base import AuthenticationCase, PASSWORD
from .test_trusted_devices import ensure_latest_schema, provision

EMAIL = 'new@example.invalid'


@override_settings(UCC_SIGNUP_CODE=True)
class SignupCodeTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def register(self, **changes):
        values = {'username': 'new-student', 'email': EMAIL, 'password1': PASSWORD, 'password2': PASSWORD}
        values.update(changes)
        return self.client.post(reverse('accounts:register'), values)

    def emailed_code(self):
        return re.search(r'code is (\d{6})\b', mail.outbox[-1].body).group(1)

    def enter(self, code, email=EMAIL, action='verify'):
        return self.client.post(reverse('accounts:verify-code'), {'email': email, 'code': code, 'action': action})

    def verified(self):
        return Student.objects.using('default').get(username='new-student').email_verified_at is not None

    def wrong(self, code):
        return f'{(int(code) + 1) % 1_000_000:06d}'

    def test_no_invite_needed_and_the_code_page_follows_registering(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertNotContains(page, 'invite_code')
        response = self.register()
        self.assertContains(response, 'Enter your code')
        self.assertContains(response, f'value="{EMAIL}"')  # email filled in for the student
        self.assertContains(response, 'name="action" value="resend"')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        code = self.emailed_code()
        self.assertIn(code, mail.outbox[0].subject)
        self.assertNotIn('/accounts/verify/', mail.outbox[0].body.split('or at')[0])  # a code, not a link
        self.assertFalse(AccountToken.objects.using('default').exists())

    def test_right_code_verifies_once_and_then_login_works(self):
        self.register()
        code = self.emailed_code()
        self.assertEqual(self.client.post(reverse('accounts:login'),
                                          {'username': 'new-student', 'password': PASSWORD}).status_code, 200)
        self.assertContains(self.enter(f'{code[:3]} {code[3:]}'), 'Email confirmed')  # spaces allowed
        self.assertTrue(self.verified())
        self.assertContains(self.enter(code), 'wrong or has expired')  # used up
        login = self.client.post(reverse('accounts:login'), {'username': 'new-student', 'password': PASSWORD})
        self.assertEqual(login.status_code, 302)

    def test_only_a_digest_is_stored(self):
        self.register()
        code = self.emailed_code()
        record = SignupCode.objects.using('default').get()
        self.assertNotIn(code, record.digest)
        self.assertRegex(record.digest, r'^[0-9a-f]{64}$')
        self.assertEqual(record.expires_at - record.created_at, timedelta(minutes=1))

    def test_code_expires_after_one_minute(self):
        self.register()
        code = self.emailed_code()
        SignupCode.objects.using('default').update(created_at=timezone.now() - timedelta(minutes=2),
                                                   expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.enter(code), 'wrong or has expired')
        self.assertFalse(self.verified())

    def test_five_wrong_tries_lock_the_code(self):
        self.register()
        code = self.emailed_code()
        for _ in range(5):
            self.assertContains(self.enter(self.wrong(code)), 'wrong or has expired')
        self.assertEqual(SignupCode.objects.using('default').get().attempts, 5)
        self.assertContains(self.enter(code), 'wrong or has expired')  # even the right one now
        self.assertFalse(self.verified())

    def test_new_code_replaces_the_old_one(self):
        self.register()
        old = self.emailed_code()
        response = self.enter('', action='resend')
        self.assertContains(response, 'sent it a 6-digit code')
        self.assertEqual(len(mail.outbox), 2)
        new = self.emailed_code()
        if new != old:
            self.assertContains(self.enter(old), 'wrong or has expired')
        self.assertContains(self.enter(new), 'Email confirmed')

    def test_replies_do_not_reveal_accounts(self):
        unknown = self.enter('', email='nobody@example.invalid', action='resend')
        verified = self.enter('', email='alpha@example.invalid', action='resend')
        self.assertEqual(unknown.status_code, verified.status_code)
        self.assertContains(unknown, 'sent it a 6-digit code')
        self.assertContains(verified, 'sent it a 6-digit code')
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.enter('123456', email='nobody@example.invalid'), 'wrong or has expired')
        # A duplicate sign-up gets the same page as a new one, and no email.
        self.register()
        mail.outbox = []
        self.assertContains(self.register(username='other-student'), 'Enter your code')
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_page_sends_a_code_on_the_public_site(self):
        self.register()
        response = self.client.post(reverse('accounts:resend'), {'email': EMAIL})
        self.assertContains(response, 'Enter your code')
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(self.enter(self.emailed_code()), 'Email confirmed')

    def test_bad_input_is_refused_without_counting(self):
        self.register()
        for value in ('12345', '1234567', 'abcdef', '١٢٣٤٥٦'):
            with self.subTest(value=value):
                self.assertContains(self.enter(value), 'wrong or has expired')
        self.assertEqual(SignupCode.objects.using('default').get().attempts, 0)
        self.assertFalse(signup_codes.verify(EMAIL, None))

    @override_settings(AUTH_RATE_LIMITS={'verify-code': (3, 60), 'register': (5, 60), 'resend': (2, 60)})
    def test_code_and_resend_buttons_are_rate_limited(self):
        self.register()
        statuses = [self.enter('000000').status_code for _ in range(4)]
        self.assertEqual(statuses, [200, 200, 200, 429])
        statuses = [self.enter('', action='resend').status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])

    def test_page_works_without_javascript(self):
        page = self.client.get(reverse('accounts:verify-code'))
        self.assertContains(page, '<form method="post"')
        self.assertContains(page, 'autocomplete="one-time-code"')
        self.assertNotContains(page, '<script>')


class SignupCodeOffLocallyTests(AuthenticationCase):
    def test_local_profiles_keep_the_email_link_and_no_code_page(self):
        self.assertEqual(self.client.get(reverse('accounts:verify-code')).status_code, 404)


class SignupCodeGrantTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def run_sql(self, statement):
        with connections['default'].cursor() as cursor:
            cursor.execute(statement)

    def test_who_and_digest_can_never_be_changed_by_the_website(self):
        student = self.make_student('charlie', verified=False)
        with transaction.atomic(using='auth'):
            signup_codes.issue_locked(Student.objects.using('auth').select_for_update().get(pk=student.pk))
        for attempt in (lambda: SignupCode.objects.using('auth').update(digest='0' * 64),
                        lambda: SignupCode.objects.using('auth').update(expires_at=timezone.now() + timedelta(days=1)),
                        lambda: SignupCode.objects.using('auth').update(student=student)):
            with self.subTest(), self.assertRaises(DatabaseError), transaction.atomic(using='auth'):
                attempt()
        with transaction.atomic(using='auth'):
            SignupCode.objects.using('auth').update(attempts=1)
        with self.assertRaises(DatabaseError), transaction.atomic(using='auth'):
            SignupCode.objects.using('auth').update(attempts=6)  # database refuses more than 5
        with self.assertRaises(DatabaseError), transaction.atomic(using='runtime'):
            SignupCode.objects.using('runtime').count()

    def test_extra_or_missing_grants_stop_the_website(self):
        auth, runtime = os.environ['UCC_AUTH_ROLE'], os.environ['UCC_RUNTIME_ROLE']
        for statement in (f'GRANT UPDATE (digest) ON accounts_signupcode TO {auth}',
                          f'GRANT TRUNCATE ON accounts_signupcode TO {auth}',
                          f'REVOKE UPDATE (attempts) ON accounts_signupcode FROM {auth}',
                          f'REVOKE INSERT ON accounts_signupcode FROM {auth}'):
            with self.subTest(statement=statement):
                self.run_sql(statement)
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        require_auth_role()
                finally:
                    self.run_sql(f'REVOKE ALL ON accounts_signupcode FROM {auth}')
                    provision()
                require_auth_role()
        self.run_sql(f'GRANT SELECT ON accounts_signupcode TO {runtime}')
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections['runtime'])
        finally:
            self.run_sql(f'REVOKE ALL ON accounts_signupcode FROM {runtime}')
            provision()
        require_runtime_role(connections['runtime'])
