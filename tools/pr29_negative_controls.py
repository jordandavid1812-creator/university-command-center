"""Test-only mutations for the isolated PR29 candidate; never imported by the app.

Run through AuthenticationTestRunner on disposable PostgreSQL with separate roles:
PYTHONPATH=tools python server/manage.py test pr29_negative_controls --settings=config.settings.auth_test
The inner regressions must FAIL under each mutation; the outer controls then PASS.
No application source files are modified.
"""
import unittest
from unittest.mock import patch
from auth_tests import test_password_upgrade_race as race
from django.db import connections


class RaceNegativeControls(unittest.TestCase):
    databases = {'default', 'runtime', 'auth'}

    def rejected(self, method, expected):
        result = unittest.TestResult()
        case_class = race.PasswordUpgradeRaceTests
        case_class.setUpClass()
        try:
            # Django's __call__ supplies _pre_setup/_post_teardown; .run alone
            # bypasses the client/flush lifecycle and is not a valid control.
            case_class(method)(result)
        finally:
            case_class.tearDownClass()
            connections.close_all()
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.errors, [], 'Mutation must fail an assertion, not test infrastructure')
        self.assertEqual(len(result.failures), 1, 'Known unsafe behavior must be detected')
        self.assertIn(expected, result.failures[0][1])
        print('NEGATIVE_CONTROL=' + method + ': expected regression assertion rejected mutation')

    def test_unsafe_hash_setter_is_detected(self):
        def unsafe_upgrade(student, raw_password):
            # Recreates the stale model-saving behavior replaced by the approved CAS.
            student.set_password(raw_password)
            student.save(using='auth', update_fields=['password'])
            return True
        with patch('accounts.backends.upgrade_password_hash', unsafe_upgrade):
            self.rejected('test_reset_committed_before_verification_is_not_overwritten',
                          'new password must remain valid')

    def test_missing_password_revalidation_is_detected(self):
        # Test-only removal of the credential-generation comparison at finalization.
        with patch('accounts.views.constant_time_compare', return_value=True):
            self.rejected('test_stale_verification_without_upgrade_creates_no_session',
                          '302 != 200')
