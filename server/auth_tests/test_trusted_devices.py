"""S0-02A: trusted-device foundation (dormant). Real separate migrator/runtime/auth LOGIN roles."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import re
import time
import uuid
from unittest import skipUnless
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
from accounts.models import AuthThrottle, DeviceGeneration, LoginLimit, Student, TrustedDevice
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
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        finally:
            connections.close_all()
    return run


def wait_for_lock_waiter(timeout=15):
    """Block until some backend is waiting on a lock (pg_locks is readable by every role)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT count(*) FROM pg_locks WHERE NOT granted')
            if cursor.fetchone()[0]:
                return
        time.sleep(0.02)
    raise AssertionError('No blocked lock waiter observed: the operation did not serialize.')


def table_names():
    return connections['default'].introspection.table_names()


class DeviceCase(AuthenticationCase):
    def setUp(self):
        ensure_latest_schema()
        super().setUp()

    def stamp(self, student=None):
        return Student.objects.using('auth').get(pk=(student or self.a).pk).get_session_auth_hash()

    def issue(self, student=None, **kwargs):
        student = student or self.a
        kwargs.setdefault('generation', devices.generation(student.pk))
        return devices.issue(student.pk, student.username, credential_stamp=self.stamp(student), **kwargs)

    def rows(self, student=None):
        return TrustedDevice.objects.using('auth').filter(student=student or self.a)


class DeviceLifecycleTests(DeviceCase):
    def test_issue_stores_only_digest_and_cookie_reveals_no_identity(self):
        issued = self.issue()
        identifier = devices.read_cookie(issued.cookie)
        record = self.rows().get()
        self.assertEqual(record.current_digest, devices.identifier_digest(identifier))
        stored = ' '.join(str(value) for value in TrustedDevice.objects.using('auth').values_list(
            'current_digest', 'previous_digest').get())
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
        self.assertEqual(devices.check(issued.cookie, 'ALPHA').status, 'mismatch')  # exact identity, no casefold
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
                self.assertEqual(devices.rotate(value, self.a.pk).status, 'absent')
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
        moment = timezone.now()
        TrustedDevice.objects.using('default').filter(pk=issued.device_id).update(
            created_at=moment - timedelta(days=31), last_used_at=moment - timedelta(days=31),
            expires_at=moment - timedelta(days=1))  # exactly last use + 30 days, already past
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.rotate(issued.cookie, self.a.pk).status, 'absent')

    def test_deactivated_student_devices_are_absent_and_cannot_be_issued(self):
        issued = self.issue()
        Student.objects.using('default').filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')
        self.assertEqual(devices.rotate(issued.cookie, self.a.pk).status, 'absent')
        with self.assertRaises(devices.DeviceError):
            self.issue()

    def test_rotation_replaces_identifier_and_renews_expiry(self):
        issued = self.issue(now=timezone.now() - timedelta(days=5))
        rotated = devices.rotate(issued.cookie, self.a.pk)
        self.assertEqual(rotated.status, 'rotated')
        self.assertNotEqual(rotated.cookie, issued.cookie)
        record = self.rows().get()
        self.assertEqual(record.previous_digest, devices.identifier_digest(devices.read_cookie(issued.cookie)))
        self.assertEqual(record.current_digest, devices.identifier_digest(devices.read_cookie(rotated.cookie)))
        self.assertGreater(record.expires_at, timezone.now() + timedelta(days=29))
        self.assertEqual(devices.check(rotated.cookie, 'alpha').status, 'trusted')

    def test_superseded_identifier_within_grace_gets_no_new_cookie(self):
        issued = self.issue()
        first = devices.rotate(issued.cookie, self.a.pk)
        second = devices.rotate(issued.cookie, self.a.pk)
        self.assertEqual((second.status, second.cookie), ('grace', None))
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'grace')
        self.assertEqual(devices.check(first.cookie, 'alpha').status, 'trusted')
        self.assertEqual(self.rows().count(), 1)

    def test_superseded_identifier_after_grace_is_replay_and_revokes(self):
        for name, operation in (('check', lambda cookie: devices.check(cookie, 'alpha')),
                                ('rotate', lambda cookie: devices.rotate(cookie, self.a.pk))):
            with self.subTest(operation=name):
                issued = self.issue()
                rotated = devices.rotate(issued.cookie, self.a.pk)
                TrustedDevice.objects.using('default').filter(pk=issued.device_id).update(
                    rotated_at=timezone.now() - devices.ROTATION_GRACE - timedelta(seconds=1))
                self.assertEqual(operation(issued.cookie).status, 'replayed')
                self.assertFalse(TrustedDevice.objects.using('auth').filter(pk=issued.device_id).exists())
                self.assertEqual(devices.check(rotated.cookie, 'alpha').status, 'absent')

    def test_two_generation_old_identifier_is_absent(self):
        issued = self.issue()
        first = devices.rotate(issued.cookie, self.a.pk)
        devices.rotate(first.cookie, self.a.pk)
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'absent')

    def test_concurrent_two_tab_rotation_gives_one_cookie_and_one_grace(self):
        issued = self.issue()
        barrier = Barrier(2)

        @in_thread
        def attempt(_):
            barrier.wait()
            return devices.rotate(issued.cookie, self.a.pk)
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
            result = devices.rotate(issued.cookie, self.a.pk)
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
        good = dict(student_id=self.a.pk, current_digest='b' * 64,
                    created_at=now, last_used_at=now, expires_at=now + timedelta(days=30))
        bad_values = (
            {'current_digest': 'NOT-HEX'}, {'current_digest': 'Z' * 64},
            {'previous_digest': 'b' * 64, 'rotated_at': now},               # previous == current
            {'previous_digest': 'c' * 64},                                  # rotated_at missing
            {'expires_at': now - timedelta(seconds=1)},
            {'expires_at': now + timedelta(days=30, microseconds=1)},       # one microsecond beyond 30 days
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


class DeviceIdentityBindingTests(DeviceCase):
    """Codex F02: device trust must follow the backend's exact account identity, never casefold."""

    def setUp(self):
        super().setUp()
        self.upper = self.account('Jordan', 'jordan-upper@example.invalid')
        self.lower = self.account('jordan', 'jordan-lower@example.invalid')

    def account(self, username, email):
        return Student.objects.db_manager('default').create_user(
            username, PASSWORD, email=email, email_verified_at=timezone.now())

    def authenticated(self, username):
        from accounts.backends import StudentBackend
        student = StudentBackend().authenticate(None, username=username, password=PASSWORD)
        return student.pk if student else None

    def test_case_distinct_accounts_exist_and_backend_distinguishes_them(self):
        self.assertNotEqual(self.upper.pk, self.lower.pk)
        self.assertEqual(self.authenticated('Jordan'), self.upper.pk)
        self.assertEqual(self.authenticated('jordan'), self.lower.pk)
        self.assertIsNone(self.authenticated('JORDAN'))

    def test_device_for_one_case_variant_never_selects_another_accounts_lane(self):
        for owner, other in ((self.upper, self.lower), (self.lower, self.upper)):
            with self.subTest(owner=owner.username):
                issued = self.issue(student=owner)
                self.assertEqual(devices.check(issued.cookie, owner.username).status, 'trusted')
                for candidate in (other.username, 'JORDAN', 'jOrDaN'):
                    result = devices.check(issued.cookie, candidate)
                    self.assertEqual(result.status, 'mismatch', candidate)
                    self.assertFalse(result.selects_trusted_limits)
                self.assertEqual(self.rows(owner).count(), 1)  # mismatch never mutates the owner's device

    def test_device_check_agrees_exactly_with_backend_identity(self):
        import unicodedata
        candidates = ['alpha', 'Alpha', 'ALPHA', 'alpha ', ' alpha', 'alpha\u200b', 'bravo',
                      '\uff41\uff4c\uff50\uff48\uff41',  # fullwidth "alpha"
                      unicodedata.normalize('NFKC', '\uff41\uff4c\uff50\uff48\uff41'),
                      'Jordan', 'jordan', 'JORDAN']
        for owner in (self.a, self.upper, self.lower):
            issued = self.issue(student=owner)
            for candidate in candidates:
                with self.subTest(owner=owner.username, candidate=repr(candidate)):
                    expected = self.authenticated(candidate) == owner.pk
                    self.assertEqual(devices.check(issued.cookie, candidate).selects_trusted_limits, expected)

    def test_stored_non_nfkc_and_nfkc_accounts_are_never_interchangeable(self):
        normalized = self.account('fiona', 'fiona@example.invalid')
        raw = Student.objects.db_manager('default').create(  # bypasses clean(): stores the ligature
            username='\ufb01ona', email='raw-fiona@example.invalid', email_verified_at=timezone.now())
        raw.set_password(PASSWORD)
        raw.save(using='default', update_fields=['password'])
        self.assertEqual(self.authenticated('fiona'), normalized.pk)
        self.assertEqual(self.authenticated('\ufb01ona'), raw.pk)
        normal_device, raw_device = self.issue(student=normalized), self.issue(student=raw)
        self.assertEqual(devices.check(normal_device.cookie, 'fiona').status, 'trusted')
        self.assertEqual(devices.check(normal_device.cookie, '\ufb01ona').status, 'mismatch')
        self.assertEqual(devices.check(raw_device.cookie, '\ufb01ona').status, 'trusted')
        self.assertEqual(devices.check(raw_device.cookie, 'fiona').status, 'mismatch')

    def test_issue_requires_the_exact_stored_username(self):
        stamp = self.stamp(self.upper)
        for candidate in ('jordan', 'JORDAN'):
            with self.subTest(candidate=candidate), self.assertRaises(devices.DeviceError):
                devices.issue(self.upper.pk, candidate, credential_stamp=stamp, generation=0)
        self.assertEqual(self.rows(self.upper).count(), 0)

    def test_rotation_requires_the_authenticated_student_uuid(self):
        issued = self.issue(student=self.upper)
        before = self.rows(self.upper).get().current_digest
        for wrong in (self.lower.pk, self.a.pk, str(self.upper.pk), None):
            with self.subTest(wrong=wrong):
                result = devices.rotate(issued.cookie, wrong)
                self.assertIn(result.status, ('mismatch', 'absent'))
                self.assertIsNone(result.cookie)
        self.assertEqual(self.rows(self.upper).get().current_digest, before)
        self.assertEqual(devices.rotate(issued.cookie, self.upper.pk).status, 'rotated')

    def test_forged_or_foreign_identifiers_never_select_the_trusted_lane(self):
        victim_device = self.issue(student=self.lower)
        attacker_device = self.issue(student=self.upper)
        forged = devices.cookie_value(devices.new_identifier())
        self.assertFalse(devices.check(forged, 'jordan').selects_trusted_limits)
        self.assertFalse(devices.check(attacker_device.cookie, 'jordan').selects_trusted_limits)
        self.assertTrue(devices.check(victim_device.cookie, 'jordan').selects_trusted_limits)

    def test_binding_is_the_student_foreign_key_not_a_username_hash(self):
        names = {field.name for field in TrustedDevice._meta.get_fields()}
        self.assertNotIn('username_key', names)
        self.assertEqual(self.rows(self.upper).count(), 0)
        issued = self.issue(student=self.upper)
        self.assertEqual(TrustedDevice.objects.using('auth').get(pk=issued.device_id).student_id, self.upper.pk)


def server_version():
    with connections['default'].cursor():
        return connections['default'].pg_version


class WrongAccountReplayTests(DeviceCase):
    """Correction A (Codex P26-05): identity is checked BEFORE any destructive replay action."""

    def rotated(self, at):
        issued = self.issue(now=at - timedelta(minutes=1))
        current = devices.rotate(issued.cookie, self.a.pk, now=at)
        self.assertEqual(current.status, 'rotated')
        return issued.cookie, current.cookie, issued.device_id

    def test_old_cookie_for_another_account_never_revokes_the_owner_after_grace(self):
        start = timezone.now()
        previous, current, device = self.rotated(start)
        later = start + devices.ROTATION_GRACE + timedelta(seconds=1)
        self.assertEqual(devices.check(previous, 'bravo', now=later).status, 'mismatch')
        self.assertEqual(devices.rotate(previous, self.b.pk, now=later).status, 'mismatch')
        self.assertTrue(TrustedDevice.objects.using('auth').filter(pk=device).exists())
        self.assertEqual(devices.check(current, 'alpha', now=later).status, 'trusted')

    def test_old_cookie_for_another_account_inside_grace_is_mismatch_and_unchanged(self):
        start = timezone.now()
        previous, current, device = self.rotated(start)
        before = self.rows().values_list('current_digest', 'previous_digest', 'rotated_at', 'expires_at').get()
        inside = start + timedelta(seconds=5)
        self.assertEqual(devices.check(previous, 'bravo', now=inside).status, 'mismatch')
        result = devices.rotate(previous, self.b.pk, now=inside)
        self.assertEqual((result.status, result.cookie), ('mismatch', None))
        self.assertEqual(self.rows().values_list('current_digest', 'previous_digest', 'rotated_at', 'expires_at').get(), before)

    def test_current_cookie_for_another_account_is_mismatch_and_unchanged(self):
        issued = self.issue()
        before = self.rows().values_list('current_digest', 'previous_digest', 'rotated_at').get()
        self.assertEqual(devices.check(issued.cookie, 'bravo').status, 'mismatch')
        self.assertEqual(devices.rotate(issued.cookie, self.b.pk).status, 'mismatch')
        self.assertEqual(self.rows().values_list('current_digest', 'previous_digest', 'rotated_at').get(), before)

    def test_unknown_or_malformed_uuid_never_revokes(self):
        start = timezone.now()
        previous, _, device = self.rotated(start)
        later = start + devices.ROTATION_GRACE + timedelta(seconds=1)
        self.assertEqual(devices.rotate(previous, uuid.uuid4(), now=later).status, 'mismatch')
        for bad in (None, str(self.a.pk), self.a.pk.hex):
            self.assertEqual(devices.rotate(previous, bad, now=later).status, 'absent')
        self.assertTrue(TrustedDevice.objects.using('auth').filter(pk=device).exists())

    def test_same_account_replay_after_grace_still_revokes(self):
        for name, operation in (('check', lambda cookie, at: devices.check(cookie, 'alpha', now=at)),
                                ('rotate', lambda cookie, at: devices.rotate(cookie, self.a.pk, now=at))):
            with self.subTest(operation=name):
                start = timezone.now()
                previous, current, device = self.rotated(start)
                at_limit = start + devices.ROTATION_GRACE
                self.assertEqual(devices.check(previous, 'alpha', now=at_limit).status, 'grace')  # boundary inclusive
                result = operation(previous, at_limit + timedelta(microseconds=1))
                self.assertEqual(result.status, 'replayed')
                self.assertFalse(TrustedDevice.objects.using('auth').filter(pk=device).exists())
                self.assertEqual(devices.check(current, 'alpha').status, 'absent')

    def test_two_generation_old_cookie_is_absent_for_every_account(self):
        start = timezone.now()
        previous, current, device = self.rotated(start)
        devices.rotate(current, self.a.pk, now=start + timedelta(minutes=5))
        later = start + timedelta(minutes=10)
        for username, student in (('alpha', self.a), ('bravo', self.b)):
            self.assertEqual(devices.check(previous, username, now=later).status, 'absent')
            self.assertEqual(devices.rotate(previous, student.pk, now=later).status, 'absent')
        self.assertTrue(TrustedDevice.objects.using('auth').filter(pk=device).exists())


class RotationConstraintTests(DeviceCase):
    """Correction C (Codex P26-03): the rotation pair is all-NULL or all-valid, never UNKNOWN."""

    def row(self, **changes):
        now = timezone.now()
        values = dict(student_id=self.a.pk, current_digest='a' * 64, previous_digest=None, rotated_at=None,
                      created_at=now, last_used_at=now, expires_at=now + timedelta(days=30))
        values.update(changes)
        return values

    def test_rotation_pair_truth_table_on_insert(self):
        now = timezone.now()
        valid = {'unrotated': {}, 'rotated': {'previous_digest': 'b' * 64, 'rotated_at': now}}
        invalid = {
            'previous NULL, rotated_at set': {'rotated_at': now},
            'previous set, rotated_at NULL': {'previous_digest': 'b' * 64},
            'previous equals current': {'previous_digest': 'a' * 64, 'rotated_at': now},
            'previous not hex': {'previous_digest': 'B' * 64, 'rotated_at': now},
        }
        for label, changes in valid.items():
            with self.subTest(valid=label):
                with transaction.atomic(using='auth'):
                    TrustedDevice.objects.using('auth').create(**self.row(**changes))
                    transaction.set_rollback(True, using='auth')
        for label, changes in invalid.items():
            with self.subTest(invalid=label), self.assertRaises(IntegrityError):
                with transaction.atomic(using='auth'):
                    TrustedDevice.objects.using('auth').create(**self.row(**changes))
        self.assertEqual(TrustedDevice.objects.using('auth').count(), 0)

    def test_rotation_pair_truth_table_on_update(self):
        record = TrustedDevice.objects.using('auth').create(**self.row())
        for label, changes in {'only rotated_at': {'rotated_at': timezone.now()},
                               'only previous_digest': {'previous_digest': 'c' * 64}}.items():
            with self.subTest(update=label), self.assertRaises(IntegrityError):
                with transaction.atomic(using='auth'):
                    TrustedDevice.objects.using('auth').filter(pk=record.pk).update(**changes)
        TrustedDevice.objects.using('auth').filter(pk=record.pk).update(
            previous_digest='c' * 64, rotated_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic(using='auth'):
            TrustedDevice.objects.using('auth').filter(pk=record.pk).update(previous_digest=None)

    def test_raw_sql_cannot_insert_the_null_rotation_combination(self):
        with self.assertRaises(IntegrityError), transaction.atomic(using='auth'):
            with connections['auth'].cursor() as cursor:
                cursor.execute("""INSERT INTO accounts_trusteddevice
                    (id, student_id, current_digest, previous_digest, rotated_at, created_at, last_used_at, expires_at)
                    VALUES (gen_random_uuid(), %s, repeat('d', 64), NULL, now(), now(), now(), now() + interval '1 day')""",
                               [self.a.pk])


class RoleDriftTests(DeviceCase):
    """Correction B (Codex P26-02): exact grant allowlist, every required column, PG17 MAINTAIN."""

    REQUIRED_UPDATES = {
        'accounts_trusteddevice': ('current_digest', 'previous_digest', 'rotated_at', 'last_used_at', 'expires_at'),
        'accounts_loginlimit': ('attempts', 'expires_at'),
        'accounts_devicegeneration': ('generation',),
    }

    def run_sql(self, statement):
        with connections['default'].cursor() as cursor:
            cursor.execute(statement)

    def assert_auth_rejected_then_restore(self, statement):
        self.run_sql(statement)
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_auth_role()
            self.assertEqual(Client().get(reverse('accounts:login')).status_code, 503)
        finally:
            provision()
        require_auth_role()

    def assert_runtime_rejected_then_restore(self, statement):
        self.run_sql(statement)
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_runtime_role(connections['runtime'])
        finally:
            provision()
        require_runtime_role(connections['runtime'])

    def test_every_required_column_update_grant_is_verified(self):
        role = os.environ['UCC_AUTH_ROLE']
        for table, columns in self.REQUIRED_UPDATES.items():
            for column in columns:
                with self.subTest(table=table, column=column):
                    self.assert_auth_rejected_then_restore(f'REVOKE UPDATE ({column}) ON {table} FROM {role}')

    def test_unexpected_auth_privileges_and_grant_options_are_rejected(self):
        role = os.environ['UCC_AUTH_ROLE']
        for statement in (f'GRANT UPDATE (id) ON accounts_trusteddevice TO {role}',
                          f'GRANT UPDATE (created_at) ON accounts_trusteddevice TO {role}',
                          f'GRANT UPDATE (bucket) ON accounts_loginlimit TO {role}',
                          f'GRANT REFERENCES ON accounts_trusteddevice TO {role}',
                          f'GRANT REFERENCES (bucket) ON accounts_loginlimit TO {role}',
                          f'GRANT TRIGGER ON accounts_devicegeneration TO {role}',
                          f'GRANT SELECT ON accounts_trusteddevice TO {role} WITH GRANT OPTION',
                          f'GRANT UPDATE (attempts) ON accounts_loginlimit TO {role} WITH GRANT OPTION'):
            with self.subTest(statement=statement):
                self.assert_auth_rejected_then_restore(statement)

    def test_partial_support_schema_is_rejected(self):
        self.run_sql('ALTER TABLE accounts_loginlimit RENAME TO accounts_loginlimit_moved')
        try:
            with self.assertRaises(ImproperlyConfigured):
                require_auth_role()
        finally:
            self.run_sql('ALTER TABLE accounts_loginlimit_moved RENAME TO accounts_loginlimit')
            provision()
        require_auth_role()

    @skipUnless(server_version() >= 170000, 'MAINTAIN privilege exists only on PostgreSQL 17+')
    def test_postgresql17_maintain_is_rejected_for_auth_and_runtime(self):
        auth, runtime = os.environ['UCC_AUTH_ROLE'], os.environ['UCC_RUNTIME_ROLE']
        for table in ('accounts_trusteddevice', 'accounts_loginlimit', 'accounts_devicegeneration',
                      'accounts_student', 'django_session'):
            with self.subTest(role='auth', table=table):
                self.assert_auth_rejected_then_restore(f'GRANT MAINTAIN ON {table} TO {auth}')
        for table in ('accounts_trusteddevice', 'accounts_loginlimit', 'accounts_devicegeneration',
                      'academics_semester', 'academics_course', 'academics_assignment', 'accounts_student'):
            with self.subTest(role='runtime', table=table):
                self.assert_runtime_rejected_then_restore(f'GRANT MAINTAIN ON {table} TO {runtime}')


class DeviceGenerationAndExpiryTests(DeviceCase):
    """Owner-approved additions: forget-all generation barrier and the exact 30-day contract."""

    def generation_row(self, student=None):
        return DeviceGeneration.objects.using('auth').filter(student=student or self.a).first()

    def test_generation_starts_at_zero_and_each_revocation_increments_it(self):
        self.assertEqual(devices.generation(self.a.pk), 0)
        self.assertIsNone(self.generation_row())  # created lazily, only by a revocation
        for expected in (1, 2, 3):
            devices.revoke_all(self.a.pk)
            self.assertEqual(devices.generation(self.a.pk), expected)
        self.assertEqual(devices.generation(self.b.pk), 0)

    def test_issue_with_a_generation_observed_before_forget_all_is_refused(self):
        observed = devices.generation(self.a.pk)
        devices.revoke_all(self.a.pk)  # explicit forget-all; the password is unchanged
        with self.assertRaises(devices.DeviceError):
            devices.issue(self.a.pk, 'alpha', credential_stamp=self.stamp(), generation=observed)
        self.assertEqual(self.rows().count(), 0)
        for bad in (None, -1, '1', 1.0, True):
            with self.subTest(bad=bad), self.assertRaises(devices.DeviceError):
                devices.issue(self.a.pk, 'alpha', credential_stamp=self.stamp(), generation=bad)
        self.issue()  # the current generation is accepted
        self.assertEqual(self.rows().count(), 1)

    def test_forget_all_during_an_inflight_login_blocks_reissue(self):
        stamp, observed = self.stamp(), devices.generation(self.a.pk)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='auth'):
                devices.revoke_all(self.a.pk)  # holds the Student lock until commit
                pending = executor.submit(in_thread(devices.issue), self.a.pk, 'alpha',
                                          credential_stamp=stamp, generation=observed)
                wait_for_lock_waiter()
            with self.assertRaises(devices.DeviceError):
                pending.result(timeout=30)
        self.assertEqual(self.rows().count(), 0)
        self.assertEqual(devices.generation(self.a.pk), 1)

    def test_concurrent_revocations_increment_exactly_once_each(self):
        barrier = Barrier(10)

        @in_thread
        def revoke(_):
            barrier.wait()
            return devices.revoke_all(self.a.pk)
        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(revoke, range(10)))
        self.assertEqual(devices.generation(self.a.pk), 10)

    def test_concurrent_issue_rotate_and_forget_all_leave_no_stale_device(self):
        seed = self.issue()
        observed, stamp = devices.generation(self.a.pk), self.stamp()
        barrier = Barrier(9)

        @in_thread
        def work(index):
            barrier.wait()
            if index == 0:
                return ('revoke', devices.revoke_all(self.a.pk))
            if index < 4:
                return ('rotate', devices.rotate(seed.cookie, self.a.pk).status)
            try:
                return ('issue', devices.issue(self.a.pk, 'alpha', credential_stamp=stamp, generation=observed).device_id)
            except devices.DeviceError:
                return ('issue', None)
        with ThreadPoolExecutor(max_workers=9) as executor:
            results = list(executor.map(work, range(9)))
        # Every device that survives was issued before the revocation committed is impossible:
        # revoke_all deletes all rows it can see after taking the Student lock, and any issue
        # serialized after it fails the generation check. So nothing may survive.
        self.assertEqual(self.rows().count(), 0, results)
        self.assertEqual(devices.generation(self.a.pk), observed + 1)
        self.assertEqual(devices.check(seed.cookie, 'alpha').status, 'absent')

    def test_auth_role_cannot_delete_or_reset_the_generation(self):
        devices.revoke_all(self.a.pk)
        for statement in ('DELETE FROM accounts_devicegeneration',
                          'TRUNCATE accounts_devicegeneration',
                          'UPDATE accounts_devicegeneration SET student_id = student_id'):
            with self.subTest(statement=statement), self.assertRaises(DatabaseError):
                with transaction.atomic(using='auth'), connections['auth'].cursor() as cursor:
                    cursor.execute(statement)
        self.assertEqual(devices.generation(self.a.pk), 1)

    def test_record_expiry_boundary_is_exactly_thirty_days(self):
        start = timezone.now()
        issued = self.issue(now=start)
        record = self.rows().get()
        self.assertEqual(record.expires_at - record.last_used_at, timedelta(days=30))
        edge = start + timedelta(days=30)
        self.assertEqual(devices.check(issued.cookie, 'alpha', now=edge - timedelta(microseconds=1)).status, 'trusted')
        self.assertEqual(devices.check(issued.cookie, 'alpha', now=edge).status, 'absent')
        self.assertEqual(devices.rotate(issued.cookie, self.a.pk, now=edge).status, 'absent')
        rotated = devices.rotate(issued.cookie, self.a.pk, now=start + timedelta(days=10))
        renewed = self.rows().get()
        self.assertEqual(renewed.expires_at - renewed.last_used_at, timedelta(days=30))
        self.assertEqual(rotated.status, 'rotated')

    def test_database_accepts_exactly_thirty_days_and_rejects_beyond(self):
        now = timezone.now()
        base = dict(student_id=self.a.pk, created_at=now, last_used_at=now)
        TrustedDevice.objects.using('auth').create(current_digest='1' * 64, expires_at=now + timedelta(days=30), **base)
        with self.assertRaises(IntegrityError), transaction.atomic(using='auth'):
            TrustedDevice.objects.using('auth').create(
                current_digest='2' * 64, expires_at=now + timedelta(days=30, microseconds=1), **base)

    def test_signed_cookie_age_boundary_is_thirty_days(self):
        identifier = devices.read_cookie(self.issue().cookie)
        real = time.time()
        with patch('time.time', return_value=real - 30 * 86400 + 5):
            young = devices.cookie_value(identifier)
        with patch('time.time', return_value=real - 30 * 86400 - 5):
            old = devices.cookie_value(identifier)
        self.assertEqual(devices.read_cookie(young), identifier)
        self.assertIsNone(devices.read_cookie(old))


class DeviceBindingAndRevocationTests(DeviceCase):
    """Review issues 1-3: record binding, revocation races and grace semantics."""

    def test_issue_binds_to_the_student_record_not_the_supplied_username(self):
        stamp = self.stamp()
        for username in ('bravo', 'ALPHA', 'nobody', 'alpha '):
            with self.subTest(username=username), self.assertRaises(devices.DeviceError):
                devices.issue(self.a.pk, username, credential_stamp=stamp, generation=0)
        with self.assertRaises(devices.DeviceError):
            devices.issue(self.a.pk, 'alpha', credential_stamp=self.stamp(self.b), generation=0)  # another student's stamp
        for stamp_value in (None, ''):
            with self.assertRaises(devices.DeviceError):
                devices.issue(self.a.pk, 'alpha', credential_stamp=stamp_value, generation=0)
        self.assertEqual(TrustedDevice.objects.using('auth').count(), 0)
        issued = devices.issue(self.a.pk, 'alpha', credential_stamp=stamp, generation=0)
        self.assertEqual(self.rows().get().student_id, self.a.pk)
        self.assertEqual(devices.check(issued.cookie, 'alpha').status, 'trusted')

    def test_issue_with_stamp_from_before_a_password_change_is_refused(self):
        old_stamp = self.stamp()
        student = Student.objects.using('auth').get(pk=self.a.pk)
        student.set_password(NEW_PASSWORD)
        student.save(using='auth', update_fields=['password', 'updated_at'])
        with self.assertRaises(devices.DeviceError):
            devices.issue(self.a.pk, 'alpha', credential_stamp=old_stamp, generation=0)
        self.assertEqual(self.rows().count(), 0)

    def test_issue_waiting_on_a_password_reset_cannot_recreate_trust(self):
        self.issue()
        old_stamp, observed = self.stamp(), devices.generation(self.a.pk)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='auth'):
                student = Student.objects.using('auth').select_for_update().get(pk=self.a.pk)
                student.set_password(NEW_PASSWORD)
                student.save(using='auth', update_fields=['password', 'updated_at'])
                devices.revoke_all(self.a.pk)
                pending = executor.submit(in_thread(devices.issue), self.a.pk, 'alpha',
                                          credential_stamp=old_stamp, generation=observed)
                wait_for_lock_waiter()  # the login-side issuance is blocked on the Student lock
            with self.assertRaises(devices.DeviceError):
                pending.result(timeout=30)
        self.assertEqual(self.rows().count(), 0)

    def test_revoke_all_waits_for_inflight_issuance_and_removes_it(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='auth'):
                inflight = self.issue()  # holds the Student lock until this block commits
                pending = executor.submit(in_thread(devices.revoke_all), self.a.pk)
                wait_for_lock_waiter()
            self.assertEqual(pending.result(timeout=30), 1)
        self.assertEqual(self.rows().count(), 0)
        self.assertEqual(devices.check(inflight.cookie, 'alpha').status, 'absent')

    def test_revoke_all_removes_a_device_rotated_concurrently(self):
        issued = self.issue()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='auth'):
                rotated = devices.rotate(issued.cookie, self.a.pk)  # holds the device-row lock
                pending = executor.submit(in_thread(devices.revoke_all), self.a.pk)
                wait_for_lock_waiter()
            self.assertEqual(pending.result(timeout=30), 1)
        self.assertEqual(rotated.status, 'rotated')
        for cookie in (issued.cookie, rotated.cookie):
            self.assertEqual(devices.check(cookie, 'alpha').status, 'absent')
            self.assertEqual(devices.rotate(cookie, self.a.pk).status, 'absent')

    def test_mixed_concurrent_issue_rotate_revoke_never_deadlock(self):
        seed = [self.issue() for _ in range(4)]
        barrier = Barrier(12)

        @in_thread
        def work(index):
            barrier.wait()
            if index % 3 == 0:
                return devices.revoke_all(self.a.pk)
            if index % 3 == 1:
                return devices.rotate(seed[index % 4].cookie, self.a.pk).status
            try:
                return self.issue().device_id
            except devices.DeviceError:
                return None  # expected: a concurrent forget-all advanced the generation
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(work, range(12)))  # a deadlock would raise here
        self.assertEqual(len(results), 12)
        self.assertLessEqual(self.rows().count(), devices.MAX_DEVICES_PER_STUDENT)

    def test_grace_never_selects_trusted_limits_or_renews(self):
        issued = self.issue()
        rotated = devices.rotate(issued.cookie, self.a.pk)
        before = self.rows().values_list('current_digest', 'last_used_at', 'expires_at').get()
        for _ in range(5):
            result = devices.check(issued.cookie, 'alpha')
            self.assertEqual(result.status, 'grace')
            self.assertFalse(result.selects_trusted_limits)
            again = devices.rotate(issued.cookie, self.a.pk)
            self.assertEqual((again.status, again.cookie), ('grace', None))
        self.assertEqual(self.rows().values_list('current_digest', 'last_used_at', 'expires_at').get(), before)
        self.assertTrue(devices.check(rotated.cookie, 'alpha').selects_trusted_limits)
        self.assertEqual(devices.check(issued.cookie, 'bravo').status, 'mismatch')
        for value in ('junk', None):
            self.assertFalse(devices.check(value, 'alpha').selects_trusted_limits)


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
            cursor.execute("""SELECT
                has_table_privilege(current_user,'accounts_devicegeneration','SELECT'),
                has_table_privilege(current_user,'accounts_devicegeneration','INSERT'),
                has_table_privilege(current_user,'accounts_devicegeneration','DELETE'),
                has_table_privilege(current_user,'accounts_devicegeneration','TRUNCATE'),
                has_column_privilege(current_user,'accounts_devicegeneration','generation','UPDATE'),
                has_column_privilege(current_user,'accounts_devicegeneration','student_id','UPDATE')""")
            self.assertEqual(cursor.fetchone(), (True, True, False, False, True, False))
        for statement in ('UPDATE accounts_trusteddevice SET student_id = student_id',
                          'UPDATE accounts_trusteddevice SET created_at = created_at',
                          'UPDATE accounts_loginlimit SET kind = kind',
                          'TRUNCATE accounts_trusteddevice'):
            self.denied('auth', statement)

    def test_runtime_role_has_no_access_to_device_tables(self):
        for statement in ('SELECT count(*) FROM accounts_trusteddevice', 'SELECT count(*) FROM accounts_loginlimit',
                          'SELECT count(*) FROM accounts_devicegeneration',
                          "INSERT INTO accounts_devicegeneration VALUES (gen_random_uuid(), 0)",
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
                              f'REVOKE UPDATE (generation) ON accounts_devicegeneration FROM {role}',
                              f'REVOKE INSERT ON accounts_devicegeneration FROM {role}',
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
                    (f'GRANT DELETE ON accounts_devicegeneration TO {auth}', require_auth_role),
                    (f'GRANT SELECT ON accounts_devicegeneration TO {runtime}',
                     lambda: require_runtime_role(connections['runtime'])),
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
            self.assertNotIn('accounts_devicegeneration', table_names())
            # Current login code loads the unrelated name field introduced in accounts.0007.
            # Supply that field ONLY as a disposable fixture while checking the historical
            # trusted-device schema; do not make production auth guess at missing columns.
            field = Student._meta.get_field('full_name')
            with connections['default'].schema_editor() as editor:
                editor.add_field(Student, field)
            try:
                provision()  # provisioning an older trusted-device schema still succeeds
                require_auth_role()
                require_runtime_role(connections['runtime'])
                self.assertEqual(self.login().status_code, 302)
            finally:
                with connections['default'].schema_editor() as editor:
                    editor.remove_field(Student, field)
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
