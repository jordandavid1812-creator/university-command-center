"""Launch step 3: invite-only sign-up, on real PostgreSQL with the separate auth and runtime roles."""
from datetime import timedelta
from io import StringIO
import os
import re
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connections, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from academics.ownership import require_runtime_role
from accounts import checks, invites
from accounts.boundary import require_auth_role
from accounts.models import InviteCode, Student
from .base import AuthenticationCase, PASSWORD
from .test_trusted_devices import ensure_latest_schema, provision

CODE_SHAPE = re.compile(r'[A-HJKMNP-TV-Z2-9]{4}(-[A-HJKMNP-TV-Z2-9]{4}){4}')


@override_settings(UCC_REQUIRE_INVITE=True)
class InviteSignUpTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def make_codes(self, count=1, days=14):
        return invites.create(count, days, using='default')

    def register(self, code=None, **changes):
        values = {'username': 'new-student', 'email': 'new@example.invalid', 'password1': PASSWORD, 'password2': PASSWORD}
        if code is not None:
            values['invite_code'] = code
        values.update(changes)
        return self.client.post(reverse('accounts:register'), values)

    def new_accounts(self):
        return Student.objects.using('default').filter(username='new-student').count()

    def used(self):
        return InviteCode.objects.using('default').filter(used_at__isnull=False).count()

    def test_codes_are_readable_random_and_only_digests_are_stored(self):
        codes = self.make_codes(20)
        self.assertEqual(len(set(codes)), 20)
        self.assertTrue(all(CODE_SHAPE.fullmatch(code) for code in codes), codes)
        stored = list(InviteCode.objects.using('default').values_list('code_hash', flat=True))
        for code in codes:
            plain = code.replace('-', '')
            self.assertFalse(any(plain in value or code in value for value in stored))
        self.assertEqual(sorted(stored), sorted(invites.digest(code.replace('-', '')) for code in codes))

    def test_form_asks_for_a_code(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertContains(page, 'name="invite_code"')
        self.assertContains(page, 'Invite code')

    def test_no_code_or_a_wrong_code_creates_nothing(self):
        self.make_codes()
        for code in (None, '', 'AAAA-AAAA-AAAA-AAAA-AAA0', 'AAAA-AAAA-AAAA-AAAA-AAAA', 'x' * 65):  # 5: the hourly limit
            with self.subTest(code=code):
                response = self.register(code)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="invite_code"')
                self.assertEqual(self.new_accounts(), 0)
        self.assertEqual(self.used(), 0)

    def test_a_valid_code_works_once(self):
        [code] = self.make_codes()
        response = self.register(code)
        self.assertContains(response, 'If these details are eligible')
        self.assertEqual(self.new_accounts(), 1)
        self.assertEqual(self.used(), 1)
        again = self.register(code, username='second-student', email='second@example.invalid')
        self.assertContains(again, invites.INVALID)
        self.assertFalse(Student.objects.using('default').filter(username='second-student').exists())

    def test_codes_are_forgiving_about_case_spaces_and_dashes(self):
        [code] = self.make_codes()
        typed = ' ' + code.lower().replace('-', ' ') + ' '
        self.assertContains(self.register(typed), 'If these details are eligible')
        self.assertEqual(self.new_accounts(), 1)

    def test_expired_and_cancelled_codes_are_refused(self):
        expired, cancelled = self.make_codes(2)
        InviteCode.objects.using('default').filter(code_hash=invites.digest(expired.replace('-', ''))).update(
            created_at=timezone.now() - timedelta(days=20), expires_at=timezone.now() - timedelta(days=1))
        number = InviteCode.objects.using('default').get(code_hash=invites.digest(cancelled.replace('-', ''))).pk
        call_command('invites', 'cancel', str(number), stdout=StringIO())
        for code in (expired, cancelled):
            with self.subTest(code=code):
                self.assertContains(self.register(code), invites.INVALID)
        self.assertEqual(self.new_accounts(), 0)

    def test_other_form_errors_keep_the_code_unused(self):
        [code] = self.make_codes()
        response = self.register(code, password2='Different-Synthetic!11')
        self.assertContains(response, 'Passwords do not match')
        self.assertEqual(self.used(), 0)
        self.assertContains(self.register(code), 'If these details are eligible')

    def test_a_failure_while_creating_the_account_keeps_the_code_unused(self):
        [code] = self.make_codes()
        with patch('accounts.tokens.register', side_effect=DatabaseError('synthetic failure')):
            with self.assertRaises(DatabaseError):
                self.register(code)
        self.assertEqual(self.used(), 0)
        self.assertEqual(self.new_accounts(), 0)

    def test_an_existing_username_uses_the_code_and_gets_the_same_reply(self):
        """A code cannot be replayed to discover which usernames or emails exist."""
        [code] = self.make_codes()
        response = self.register(code, username='alpha')
        self.assertContains(response, 'If these details are eligible')
        self.assertEqual(self.used(), 1)
        self.assertEqual(Student.objects.using('default').filter(username='alpha').count(), 1)

    def test_sign_up_limit_still_applies_before_codes_are_checked(self):
        codes = self.make_codes(7)
        statuses = [self.register(code, username=f'limit-{n}', email=f'limit{n}@example.invalid').status_code
                    for n, code in enumerate(codes)]
        self.assertEqual(statuses[-1], 429)
        self.assertEqual(self.used(), 5)  # register limit: 5 per hour per address


class InviteSettingTests(AuthenticationCase):
    def test_local_website_does_not_ask_for_codes(self):
        page = self.client.get(reverse('accounts:register'))
        self.assertNotContains(page, 'invite_code')

    def test_public_site_without_email_codes_fails_its_system_check(self):
        # Open sign-up replaced invite-only sign-up: the public site must confirm emails by code.
        for invite in (False, True):
            with override_settings(UCC_PUBLIC_SITE=True, UCC_SIGNUP_CODE=False, UCC_REQUIRE_INVITE=invite):
                self.assertEqual([e.id for e in checks.public_invite_check()], ['accounts.E106'])
        with override_settings(UCC_PUBLIC_SITE=True, UCC_SIGNUP_CODE=True):
            self.assertEqual(checks.public_invite_check(), [])
        self.assertEqual(checks.public_invite_check(), [])  # local profiles are not public


class InviteGrantTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()
        invites.create(1, 14, using='default')

    def run_sql(self, statement):
        with connections['default'].cursor() as cursor:
            cursor.execute(statement)

    def test_auth_role_can_only_read_codes_and_mark_them_used(self):
        with transaction.atomic(using='auth'):
            invite = InviteCode.objects.using('auth').select_for_update().first()
            InviteCode.objects.using('auth').filter(pk=invite.pk).update(used_at=timezone.now())
        for attempt in (lambda: invites.create(1, 1, using='auth'),
                        lambda: InviteCode.objects.using('auth').all().delete(),
                        lambda: InviteCode.objects.using('auth').update(expires_at=timezone.now()),
                        lambda: InviteCode.objects.using('auth').update(note='changed')):
            with self.subTest(), self.assertRaises(DatabaseError), transaction.atomic(using='auth'):
                attempt()

    def test_runtime_role_cannot_read_codes(self):
        with self.assertRaises(DatabaseError), transaction.atomic(using='runtime'):
            InviteCode.objects.using('runtime').count()

    def test_extra_or_missing_grants_stop_the_website(self):
        auth, runtime = os.environ['UCC_AUTH_ROLE'], os.environ['UCC_RUNTIME_ROLE']
        for statement in (f'GRANT INSERT ON accounts_invitecode TO {auth}',
                          f'GRANT DELETE ON accounts_invitecode TO {auth}',
                          f'GRANT UPDATE (expires_at) ON accounts_invitecode TO {auth}',
                          f'GRANT SELECT ON accounts_invitecode TO {auth} WITH GRANT OPTION',
                          f'REVOKE UPDATE (used_at) ON accounts_invitecode FROM {auth}',
                          f'REVOKE SELECT ON accounts_invitecode FROM {auth}'):
            with self.subTest(statement=statement):
                self.run_sql(statement)
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        require_auth_role()
                    self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 503)
                finally:
                    self.run_sql(f'REVOKE ALL ON accounts_invitecode FROM {auth}')
                    provision()
                require_auth_role()
        for statement in (f'GRANT SELECT ON accounts_invitecode TO {runtime}',
                          f'GRANT SELECT (note) ON accounts_invitecode TO {runtime}'):
            with self.subTest(statement=statement):
                self.run_sql(statement)
                try:
                    with self.assertRaises(ImproperlyConfigured):
                        require_runtime_role(connections['runtime'])
                finally:
                    self.run_sql(f'REVOKE ALL ON accounts_invitecode FROM {runtime}')
                    provision()
                require_runtime_role(connections['runtime'])


class InviteCommandTests(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def run_command(self, *args):
        output = StringIO()
        call_command('invites', *args, stdout=output)
        return output.getvalue()

    def test_create_shows_codes_once_and_list_never_shows_them(self):
        created = self.run_command('create', '--count', '3', '--days', '7', '--note', 'Synthetic class rep')
        codes = [match.group(0) for match in CODE_SHAPE.finditer(created)]
        self.assertEqual(len(codes), 3)
        self.assertIn('valid for 7 days', created)
        listing = self.run_command('list')
        self.assertEqual(listing.count('Synthetic class rep'), 3)
        self.assertEqual(listing.count('unused until'), 3)
        self.assertFalse(any(code in listing or code.replace('-', '') in listing for code in codes))
        with override_settings(UCC_REQUIRE_INVITE=True):
            self.client.post(reverse('accounts:register'), {
                'username': 'new-student', 'email': 'new@example.invalid', 'password1': PASSWORD,
                'password2': PASSWORD, 'invite_code': codes[0]})
        listing = self.run_command('list')
        self.assertEqual(len(re.findall(r'(?<!un)used \d{4}-\d\d-\d\d', listing)), 1)
        self.assertEqual(listing.count('unused until'), 2)

    def test_cancel_only_unused_codes(self):
        self.run_command('create')
        number = str(InviteCode.objects.using('default').get().pk)
        self.assertIn('cancelled', self.run_command('cancel', number))
        self.assertIn('expired', self.run_command('list'))
        with self.assertRaises(CommandError):
            self.run_command('cancel', number)

    def test_bad_values_are_refused(self):
        for args in (['create', '--count', '0'], ['create', '--count', '51'], ['create', '--days', '61'],
                     ['create', '--note', 'x' * 61], ['create', '--note', 'line\nbreak'], ['cancel', '0']):
            with self.subTest(args=args), self.assertRaises(CommandError):
                self.run_command(*args)
        self.assertEqual(InviteCode.objects.using('default').count(), 0)
