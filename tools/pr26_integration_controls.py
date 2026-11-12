"""Synthetic PG17 integration/dormancy and mutation controls; never app imports."""
from contextlib import ExitStack
from hashlib import sha256
import unittest
from unittest.mock import patch
from django.db import connections
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts import devices
from accounts.models import LoginLimit, TrustedDevice
from auth_tests import test_trusted_devices as foundation
from auth_tests.base import PASSWORD


class DormantIntegrationTests(foundation.DeviceCase):
    def test_populated_limits_and_cookie_do_not_activate_a_login_lane(self):
        issued = self.issue()
        kinds = [value for value, _ in LoginLimit._meta.get_field('kind').choices]
        for kind in kinds:
            LoginLimit.objects.using('auth').create(
                bucket=sha256(('synthetic-rehearsal-'+kind).encode()).hexdigest(),
                kind=kind, attempts=2147483647,
                expires_at=timezone.now()+devices.DEVICE_LIFETIME)
        client = Client(REMOTE_ADDR='10.26.0.1')
        client.cookies['ucc_device'] = issued.cookie  # Test input, not an HTTP issuer.
        client.cookies['trusted_device'] = issued.cookie
        self.assertEqual(client.get(reverse('accounts:academic')).status_code, 302)
        original = self.rows().get().current_digest
        # Even populated tables/cookie input must not invoke any dormant primitive.
        with ExitStack() as stack:
            for name in ('issue', 'check', 'rotate', 'generation', 'revoke_all'):
                stack.enter_context(patch.object(devices, name, side_effect=AssertionError('Dormant primitive reached')))
            wrong = client.post(reverse('accounts:login'), {'username':'alpha', 'password':'synthetic-wrong'})
            self.assertEqual(wrong.status_code, 200)
            success = client.post(reverse('accounts:login'), {'username':'alpha', 'password':PASSWORD})
            self.assertEqual(success.status_code, 302)
        self.assertFalse([name for name in success.cookies if 'device' in name.lower()])
        self.assertEqual(self.rows().get().current_digest, original)
        self.assertEqual(TrustedDevice.objects.using('auth').count(), 1)
        self.assertEqual(list(LoginLimit.objects.using('auth').values_list('attempts', flat=True)),
                         [2147483647]*len(kinds))


class NegativeControls(unittest.TestCase):
    databases = {'default', 'runtime', 'auth'}

    def rejected(self, case_class, method, expected, failure_count=1):
        result = unittest.TestResult()
        case_class.setUpClass()
        try:
            case_class(method)(result)  # Preserve Django setup/client/flush lifecycle.
        finally:
            case_class.tearDownClass()
            connections.close_all()
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.errors, [], 'Expected assertion failure, not fixture/infrastructure errors')
        self.assertEqual(len(result.failures), failure_count)
        for _, traceback in result.failures:
            self.assertIn(expected, traceback)
        print('NEGATIVE_CONTROL='+method+': expected regression assertion rejected mutation')

    def test_removed_auth_grant_guard_is_detected(self):
        with patch('accounts.boundary.auth_support_violation_sql', return_value='false'):
            self.rejected(foundation.DeviceRoleTests, 'test_missing_auth_grant_fails_closed',
                          'ImproperlyConfigured not raised', failure_count=5)

    def test_unprovisioned_migration_guard_removal_is_detected(self):
        with patch('accounts.boundary.auth_support_violation_sql', return_value='false'):
            self.rejected(foundation.DeviceRoleTests,
                          'test_migration_reverses_and_reapplies_with_fail_closed_grants',
                          'ImproperlyConfigured not raised')

    def test_unexpected_device_cookie_delivery_is_detected(self):
        from accounts import views
        real = views.redirect
        def mutated(*args, **kwargs):
            response = real(*args, **kwargs)
            response.set_cookie('synthetic_device_probe', 'synthetic-only')
            return response
        with patch.object(views, 'redirect', mutated):
            self.rejected(foundation.DeviceCompatibilityTests,
                          'test_login_behaviour_unchanged_no_device_cookie_or_rows', 'is not false')
