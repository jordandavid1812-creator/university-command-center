"""S0-02A: trusted-device foundation (dormant). Real separate migrator/runtime/auth LOGIN roles."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import re
import time
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlsplit
from django.core import mail, signing
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from academics.ownership import require_runtime_role
from accounts import devices
from accounts.boundary import require_auth_role
from accounts.models import AuthThrottle, LoginLimit, Student, TrustedDevice
from .base import AuthenticationCase, NEW_PASSWORD, PASSWORD

LATEST = ('accounts', '0003_trusted_device_foundation')
PREVIOUS = ('accounts', '0002_accounttoken_auththrottle_student_email_and_more')


def provision():
    call_command('configure_runtime', verbosity=0)
    call_command('configure_auth_role', verbosity=0)


def ensure_latest_schema():
    """The historical schema test leaves accounts at 0002; restore the leaf and grants."""
    executor = MigrationExecutor(connections['default'])
    targets = executor.loader.graph.leaf_nodes()
    if executor.migration_plan(targets):
        executor.migrate(targets)
        provision()


def in_thread(function):
    def run(*args):
        try:
            return function(*args)
        finally:
            connections.close_all()
    return run


def table_names():
    return connections['default'].introspection.table_names()


class DeviceCase(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def issue(self, student=None, **kwargs):
        student = student or self.a
        return devices.issue(student.pk, student.username, **kwargs)

    def rows(self, student=None):
        return TrustedDevice.objects.using('auth').filter(student=student or self.a)


class DeviceLifecycleTests(DeviceCase):
    def test_issue_stores_only_digest_and_cookie_reveals_no_identity(self):
        issued = self.issue()
        identifier = devices.read_cookie(issued.cookie)
        record = self.rows().get()
        self.assertEqual(record.current_digest, devices.identifier_digest(identifier))
        stored = ' '.join(str(value) for value in TrustedDevice.objects.using('auth').values_list(
            'username_key', 'current_digest', 'previous_digest').get())
        self.assertNotIn(identifier, stored)
        self.assertNotIn('alpha', stored)
        payload = signing.b64_decode(issued.cookie.split(':')[0].encode()).decode()
        for secret in ('alpha', str(self.a.pk), str(record.pk), 'example.invalid'):
            self.assertNotIn(secret, payload)
        self.assertEqual(record.expires_at - record.created_at, timedelta(days=30))
        self.assertNotIn('cookie', repr(issued))

    def test_identifiers_are_256_bit_and_unique(self):
        values = {devices.new_identifier() for _ in range(500)}
        self.assertEqual(len(values), 500)
        for value in values:
            self.assertRegex(value, r'\A[A-Za-z0-9_-]{43}\Z')
            self.assertEqual(len(devices.base64.urlsafe_b64decode(value + '=')), 32)

    def test_check_accepts_only_the_bound_account(self):
        issued = self.issue()
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')
        self.assertEqual(devices.check(issued.cookie, 'ALPHA').status, 'trusted')  # casefold
        self.assertEqual(devices.check(issued.cookie, 'bravo').status, 'mismatch')
        self.assertEqual(devices.check(issued.cookie, 'unknown-user').status, 'mismatch')
        self.assertEqual(self.rows().count(), 1)

    def test_invalid_tampered_foreign_and_junk_cookies_are_absent(self):
        issued = self.issue()
        identifier = devices.read_cookie(issued.cookie)
        other_salt = signing.dumps(identifier, salt='ucc.some-other-purpose')
        session_value = self.client_a.cookies['sessionid'].value if 'sessionid' in self.client_a.cookies else 'x' * 32
        tampered = issued.cookie[:-1] + ('A' if issued.cookie[-1] != 'A' else 'B')
        for value in (None, '', 'junk', tampered, other_salt, session_value, identifier, 'x' * 300,
                      signing.dumps('not-an-identifier', salt=devices.COOKIE_SALT),
                      signing.dumps(devices.new_identifier(), salt=devices.COOKIE_SALT)):
            with self.subTest(value=str(value)[:20]):
                self.assertEqual(devices.check(value, 'alpha').status, 'absent')
                self.assertEqual(devices.rotate(value, 'alpha').status, 'absent')
        self.assertEqual(devices.check(issued.cookie, '').status, 'absent')
        self.assertEqual(devices.check(issued.cookie, None).status, 'absent')
        self.assertEqual(self.rows().count(), 1)

    def test_expired_signature_and_expired_record_are_absent(self):
        issued = self.issue()
        identifier = devices.read_cookie(issued.cookie)
        with patch('time.time', return_value=time.time() - 31 * 86400):
            stale_cookie = devices.cookie_value(identifier)  # same identifier, 31-day-old signature
        self.assertIsNone(devices.read_cookie(stale_cookie))
        self.assertEqual(devices.check(stale_cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')
        TrustedDevice.objects.using('default').filter(pk=issued.device_id).update(
            created_at=timezone.now() - timedelta(days=31), last_used_at=timezone.now() - timedelta(days=31),
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.rotate(issued.cookie, 'alpha').status, 'absent')

    def test_deactivated_student_devices_are_absent_and_cannot_be_issued(self):
        issued = self.issue()
        Student.objects.using('default').filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.rotate(issued.cookie, 'alpha').status, 'absent')
        with self.assertRaises(devices.DeviceError):
            self.issue()

    def test_rotation_replaces_identifier_and_renews_expiry(self):
        issued = self.issue(now=timezone.now() - timedelta(days=5))
        rotated = devices.rotate(issued.cookie, 'alpha')
        self.assertEqual(rotated.status, 'rotated')
        self.assertNotEqual(rotated.cookie, issued.cookie)
        record = self.rows().get()
        self.assertEqual(record.previous_digest, devices.identifier_digest(devices.read_cookie(issued.cookie)))
        self.assertEqual(record.current_digest, devices.identifier_digest(devices.read_cookie(rotated.cookie)))
        self.assertGreater(record.expires_at, timezone.now() + timedelta(days=29))
        self.assertEqual(devices.check(rotated.cookie, 'alpha').status, 'trusted')

    def test_superseded_identifier_within_grace_gets_no_new_cookie(self):
        issued = self.issue()
        first = devices.rotate(issued.cookie, 'alpha')
        second = devices.rotate(issued.cookie, 'alpha')
        self.assertEqual((second.status, second.cookie), ('grace', None))
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'grace')
        self.assertEqual(devices.check(first.cookie, 'alpha').status, 'trusted')
        self.assertEqual(self.rows().count(), 1)

    def test_superseded_identifier_after_grace_is_replay_and_revokes(self):
        for operation in (devices.check, devices.rotate):
            with self.subTest(operation=operation.__name__):
                issued = self.issue()
                rotated = devices.rotate(issued.cookie, 'alpha')
                TrustedDevice.objects.using('default').filter(pk=issued.device_id).update(
                    rotated_at=timezone.now() - devices.ROTATION_GRACE - timedelta(seconds=1))
                self.assertEqual(operation(issued.cookie, 'alpha').status, 'replayed')
                self.assertFalse(TrustedDevice.objects.using('auth').filter(pk=issued.device_id).exists())
                self.assertEqual(devices.check(rotated.cookie, 'alpha').status, 'absent')

    def test_replay_is_detected_even_with_another_username(self):
        issued = self.issue()
        devices.rotate(issued.cookie, 'alpha')
        TrustedDevice.objects.using('default').filter(pk=issued.device_id).update(
            rotated_at=timezone.now() - timedelta(minutes=5))
        self.assertEqual(devices.check(issued.cookie, 'bravo').status, 'replayed')
        self.assertEqual(self.rows().count(), 0)

    def test_two_generation_old_identifier_is_absent(self):
        issued = self.issue()
        first = devices.rotate(issued.cookie, 'alpha')
        devices.rotate(first.cookie, 'alpha')
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')

    def test_concurrent_two_tab_rotation_gives_one_cookie_and_one_grace(self):
        issued = self.issue()
        barrier = Barrier(2)

        @in_thread
        def attempt(_):
            barrier.wait()
            return devices.rotate(issued.cookie, 'alpha')
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (1, 2)))
        self.assertEqual(sorted(result.status for result in results), ['grace', 'rotated'])
        winner = next(result for result in results if result.status == 'rotated')
        self.assertEqual(devices.check(winner.cookie, 'alpha').status, 'trusted')
        self.assertEqual(self.rows().count(), 1)

    def test_lost_conditional_update_never_returns_an_unstored_cookie(self):
        from django.db.models.query import QuerySet
        issued = self.issue()
        before = self.rows().get().current_digest
        # Simulate the outcome of losing a rotation race: the conditional UPDATE
        # (current_digest = presented digest) matches no row.
        with patch.object(QuerySet, 'update', lambda queryset, **values: 0):
            result = devices.rotate(issued.cookie, 'alpha')
        self.assertEqual((result.status, result.cookie), ('grace', None))
        self.assertEqual(self.rows().get().current_digest, before)
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')

    def test_cap_evicts_least_recently_used(self):
        start = timezone.now() - timedelta(days=1)
        issued = [self.issue(now=start + timedelta(minutes=index)) for index in range(12)]
        self.assertEqual(self.rows().count(), devices.MAX_DEVICES_PER_STUDENT)
        self.assertEqual([devices.check(item.cookie, 'alpha').status for item in issued[:2]], ['absent', 'absent'])
        self.assertTrue(all(devices.check(item.cookie, 'alpha').status == 'trusted' for item in issued[2:]))
        self.issue(student=self.b)
        self.assertEqual(self.rows(self.b).count(), 1)

    def test_concurrent_issue_never_exceeds_cap(self):
        barrier = Barrier(20)

        @in_thread
        def attempt(_):
            barrier.wait()
            return self.issue()
        with ThreadPoolExecutor(max_workers=20) as executor:
            list(executor.map(attempt, range(20)))
        self.assertEqual(self.rows().count(), devices.MAX_DEVICES_PER_STUDENT)

    def test_revoke_one_and_all_leave_other_students(self):
        first, second = self.issue(), self.issue()
        other = self.issue(student=self.b)
        self.assertEqual(devices.revoke(first.device_id), 1)
        self.assertEqual(devices.check(first.cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.check(second.cookie, 'alpha').status, 'trusted')
        self.issue()
        self.assertEqual(devices.revoke_all(self.a.pk), 2)
        self.assertEqual(self.rows().count(), 0)
        self.assertEqual(devices.check(other.cookie, 'bravo').status, 'trusted')

    def test_cleanup_removes_only_expired_records_in_batches(self):
        live = self.issue()
        past = timezone.now() - timedelta(days=40)
        for _ in range(5):
            self.issue(now=past)
        for index in range(7):
            LoginLimit.objects.using('auth').create(bucket=f'{index:064x}', kind='account_fail', attempts=1,
                                                    expires_at=timezone.now() - timedelta(seconds=1))
        LoginLimit.objects.using('auth').create(bucket='f' * 64, kind='ip_ceiling', attempts=1,
                                                expires_at=timezone.now() + timedelta(minutes=5))
        self.assertEqual(devices.cleanup_expired(batch_size=2), {'devices': 5, 'limits': 7})
        self.assertEqual(devices.cleanup_expired(batch_size=2), {'devices': 0, 'limits': 0})
        self.issue(student=self.b, now=past)
        call_command('clear_auth_artifacts', verbosity=0)
        self.assertEqual(self.rows(self.b).count(), 0)
        self.assertEqual(devices.check(live.cookie, 'alpha').status, 'trusted')
        self.assertEqual(LoginLimit.objects.using('auth').count(), 1)
        for size in (0, 10001, '5'):
            with self.assertRaises(devices.DeviceError):
                devices.cleanup_expired(batch_size=size)

    def test_secret_key_rotation_requires_fallback(self):
        from django.conf import settings
        old = settings.SECRET_KEY
        issued = self.issue()
        with override_settings(SECRET_KEY='n' * 64, SECRET_KEY_FALLBACKS=[old]):
            self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')
        with override_settings(SECRET_KEY='n' * 64, SECRET_KEY_FALLBACKS=[]):
            self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')

    def test_database_constraints_reject_invalid_records(self):
        now = timezone.now()
        good = dict(student_id=self.a.pk, username_key='a' * 64, current_digest='b' * 64,
                    created_at=now, last_used_at=now, expires_at=now + timedelta(days=30))
        bad_values = (
            {'current_digest': 'NOT-HEX'}, {'username_key': 'z' * 64},
            {'previous_digest': 'b' * 64, 'rotated_at': now},               # previous == current
            {'previous_digest': 'c' * 64},                                  # rotated_at missing
            {'expires_at': now - timedelta(seconds=1)},
            {'expires_at': now + timedelta(days=40)},                       # beyond lifetime bound
        )
        for changes in bad_values:
            with self.subTest(changes=list(changes)), self.assertRaises(IntegrityError):
                with transaction.atomic(using='auth'):
                    TrustedDevice.objects.using('auth').create(**{**good, **changes})
        for changes in ({'bucket': 'XYZ'}, {'kind': 'other'}, {'attempts': -1}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                with transaction.atomic(using='auth'):
                    LoginLimit.objects.using('auth').create(**{'bucket': 'd' * 64, 'kind': 'account_fail',
                                                               'attempts': 0, 'expires_at': now, **changes})
        self.assertEqual(TrustedDevice.objects.using('auth').count(), 0)


class DeviceCompatibilityTests(DeviceCase):
    def test_login_behaviour_unchanged_no_device_cookie_or_rows(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertFalse([name for name in response.cookies if 'device' in name.lower()])
        self.assertEqual(TrustedDevice.objects.using('auth').count(), 0)
        self.assertEqual(LoginLimit.objects.using('auth').count(), 0)
        self.assertEqual(AuthThrottle.objects.using('auth').count(), 1)
        failed = Client().post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong'})
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(LoginLimit.objects.using('auth').count(), 0)

    def test_password_change_and_reset_flows_work_with_devices_present(self):
        issued = self.issue()
        self.login()
        response = self.client_a.post(reverse('accounts:password-change'), {
            'old_password': PASSWORD, 'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertRedirects(response, reverse('accounts:login'), fetch_redirect_response=False)
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        link = urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        reset = self.client.post(link, {'new_password1': PASSWORD, 'new_password2': PASSWORD})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(self.login().status_code, 302)
        # S0-02A is dormant: revocation is wired into these flows only in S0-02B.
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')

    def test_revoke_all_is_atomic_with_a_locked_password_update(self):
        self.issue(), self.issue()
        with self.assertRaises(RuntimeError):
            with transaction.atomic(using='auth'):
                student = Student.objects.using('auth').select_for_update().get(pk=self.a.pk)
                student.set_password(NEW_PASSWORD)
                student.save(using='auth', update_fields=['password', 'updated_at'])
                self.assertEqual(devices.revoke_all(self.a.pk), 2)
                raise RuntimeError('simulated failure after revocation')
        self.assertEqual(self.rows().count(), 2)
        self.assertEqual(self.login().status_code, 302)  # password rolled back too
        with transaction.atomic(using='auth'):
            student = Student.objects.using('auth').select_for_update().get(pk=self.a.pk)
            student.set_password(NEW_PASSWORD)
            student.save(using='auth', update_fields=['password', 'updated_at'])
            devices.revoke_all(self.a.pk)
        self.assertEqual(self.rows().count(), 0)


class DeviceRoleTests(DeviceCase):
    def denied(self, alias, statement):
        with self.assertRaises(DatabaseError):
            with transaction.atomic(using=alias), connections[alias].cursor() as cursor:
                cursor.execute(statement)

    def test_auth_role_grants_are_minimal(self):
        with connections['auth'].cursor() as cursor:
            cursor.execute("""SELECT
                has_table_privilege(current_user,'accounts_trusteddevice','SELECT'),
                has_table_privilege(current_user,'accounts_trusteddevice','INSERT'),
                has_table_privilege(current_user,'accounts_trusteddevice','DELETE'),
                has_table_privilege(current_user,'accounts_trusteddevice','UPDATE'),
                has_table_privilege(current_user,'accounts_trusteddevice','TRUNCATE'),
                has_table_privilege(current_user,'accounts_loginlimit','UPDATE')""")
            self.assertEqual(cursor.fetchone(), (True, True, True, False, False, False))
            cursor.execute("""SELECT array_agg(attname ORDER BY attname) FROM pg_attribute
                WHERE attrelid='accounts_trusteddevice'::regclass AND attnum>0 AND NOT attisdropped
                  AND has_column_privilege(current_user, attrelid, attnum, 'UPDATE')""")
            self.assertEqual(cursor.fetchone()[0], ['current_digest', 'expires_at', 'last_used_at',
                                                    'previous_digest', 'rotated_at'])
            cursor.execute("""SELECT array_agg(attname ORDER BY attname) FROM pg_attribute
                WHERE attrelid='accounts_loginlimit'::regclass AND attnum>0 AND NOT attisdropped
                  AND has_column_privilege(current_user, attrelid, attnum, 'UPDATE')""")
            self.assertEqual(cursor.fetchone()[0], ['attempts', 'expires_at'])
        for statement in ('UPDATE accounts_trusteddevice SET student_id = student_id',
                          'UPDATE accounts_trusteddevice SET username_key = username_key',
                          'UPDATE accounts_loginlimit SET kind = kind',
                          'TRUNCATE accounts_trusteddevice'):
            self.denied('auth', statement)

    def test_runtime_role_has_no_access_to_device_tables(self):
        for statement in ('SELECT count(*) FROM accounts_trusteddevice', 'SELECT count(*) FROM accounts_loginlimit',
                          "INSERT INTO accounts_loginlimit VALUES (repeat('a',64),'ip_ceiling',1,now())",
                          'DELETE FROM accounts_trusteddevice', 'UPDATE accounts_loginlimit SET attempts = 0'):
            self.denied('runtime', statement)
        with connections['runtime'].cursor() as cursor:
            cursor.execute("""SELECT has_any_column_privilege(current_user,'accounts_trusteddevice','SELECT, INSERT, UPDATE, REFERENCES'),
                                     has_any_column_privilege(current_user,'accounts_loginlimit','SELECT, INSERT, UPDATE, REFERENCES')""")
            self.assertEqual(cursor.fetchone(), (False, False))
        require_runtime_role(connections['runtime'])

    def test_missing_auth_grant_fails_closed(self):
        role = os.environ['UCC_AUTH_ROLE']
        require_auth_role()
        try:
            for statement in (f'REVOKE SELECT ON accounts_trusteddevice FROM {role}',
                              f'REVOKE DELETE ON accounts_loginlimit FROM {role}',
                              f'REVOKE UPDATE (current_digest) ON accounts_trusteddevice FROM {role}'):
                with self.subTest(statement=statement):
                    with connections['default'].cursor() as cursor:
                        cursor.execute(statement)
                    with self.assertRaises(ImproperlyConfigured):
                        require_auth_role()
                    self.assertEqual(Client().get(reverse('accounts:login')).status_code, 503)
                    call_command('configure_auth_role', verbosity=0)
                    require_auth_role()
        finally:
            call_command('configure_auth_role', verbosity=0)
        self.assertEqual(Client().get(reverse('accounts:login')).status_code, 200)

    def test_over_privileged_roles_fail_closed(self):
        auth, runtime = os.environ['UCC_AUTH_ROLE'], os.environ['UCC_RUNTIME_ROLE']
        try:
            for statement, check in (
                    (f'GRANT UPDATE (student_id) ON accounts_trusteddevice TO {auth}', require_auth_role),
                    (f'GRANT UPDATE (kind) ON accounts_loginlimit TO {auth}', require_auth_role),
                    (f'GRANT TRUNCATE ON accounts_trusteddevice TO {auth}', require_auth_role),
                    (f'GRANT SELECT ON accounts_loginlimit TO {runtime}',
                     lambda: require_runtime_role(connections['runtime'])),
                    (f'GRANT SELECT (id) ON accounts_trusteddevice TO {runtime}',
                     lambda: require_runtime_role(connections['runtime']))):
                with self.subTest(statement=statement):
                    with connections['default'].cursor() as cursor:
                        cursor.execute(statement)
                    with self.assertRaises(ImproperlyConfigured):
                        check()
                    self.assertEqual(Client().get(reverse('accounts:login')).status_code, 503)
                    provision()
                    check()
        finally:
            provision()

    def test_migration_reverses_and_reapplies_with_fail_closed_grants(self):
        executor = MigrationExecutor(connections['default'])
        try:
            executor.migrate([PREVIOUS])
            self.assertNotIn('accounts_trusteddevice', table_names())
            self.assertNotIn('accounts_loginlimit', table_names())
            provision()  # provisioning an older schema still succeeds
            require_auth_role()
            require_runtime_role(connections['runtime'])
            self.assertEqual(self.login().status_code, 302)
            MigrationExecutor(connections['default']).migrate([LATEST])
            self.assertIn('accounts_trusteddevice', table_names())
            with self.assertRaises(ImproperlyConfigured):
                require_auth_role()  # tables exist but grants not yet provisioned
            self.assertEqual(Client().get(reverse('accounts:login')).status_code, 503)
            provision()
            require_auth_role()
            require_runtime_role(connections['runtime'])
        finally:
            ensure_latest_schema()
            provision()
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_class WHERE relname IN ('academics_course','academics_assignment','academics_semester') AND relrowsecurity AND relforcerowsecurity")
            self.assertEqual(cursor.fetchone(), (3,))
        self.assertEqual(devices.check(self.issue().cookie, 'alpha').status, 'trusted')


class DeviceModuleIsolationTests(DeviceCase):
    def test_live_code_does_not_import_device_primitives(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        pattern = re.compile(r'accounts\.devices|from \.devices|from \. import[^\n]*\bdevices\b')
        users = []
        for path in root.rglob('*.py'):
            relative = path.relative_to(root)
            if relative.parts[0].endswith('_tests') or 'tests' in relative.parts or path.name == 'devices.py':
                continue
            if pattern.search(path.read_text()):
                users.append(str(relative))
        self.assertEqual(sorted(users), ['accounts/management/commands/clear_auth_artifacts.py'])
