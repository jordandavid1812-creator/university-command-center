"""Run with Django's auth/web test runner: synthetic mutation controls, no policy changes."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from django.db import connections
from accounts import dbsafety, checks
from auth_tests import test_b1_settings as contracts
from auth_tests.base import AuthenticationCase


class NegativeControls(AuthenticationCase):
    def killed(self, method):
        # These nested cases are settings-only; the outer Django case owns DB fixtures.
        case=contracts.SafetyConfigurationTests(method)
        result=unittest.TestResult()
        case.run(result)
        self.assertEqual(result.errors,[], 'Infrastructure errors do not count as killed mutants')
        self.assertGreater(len(result.failures),0,'Mutation escaped its nominated assertion')
        self.assertEqual(result.testsRun,1)
        print('B1A_MUTATION_KILLED='+method)

    def test_settings_mutations_are_detected(self):
        real=dbsafety.options_for
        with patch.object(dbsafety,'options_for',lambda values,key:real(values,key).replace('-c lock_timeout=3000 ','')):
            self.killed('test_fixed_options_tls_idempotence_and_migrator_exclusion')
        real_apply=contracts.apply_db_safety
        def leak(namespace):
            real_apply(namespace)
            namespace['DATABASES']['default']['OPTIONS']['options']='-c lock_timeout=3000'
        with patch.object(contracts,'apply_db_safety',leak):
            self.killed('test_fixed_options_tls_idempotence_and_migrator_exclusion')
        # The TLS mutation must produce an assertion, not a KeyError.
        def overwrite_tls(namespace):
            real_apply(namespace)
            namespace['DATABASES']['auth']['OPTIONS']['sslrootcert']='incorrect-ca.pem'
        with patch.object(contracts,'apply_db_safety',overwrite_tls):
            self.killed('test_fixed_options_tls_idempotence_and_migrator_exclusion')
        with patch.object(contracts,'validate_values',lambda values:dict(dbsafety.DEFAULTS)):
            self.killed('test_bad_types_ranges_and_cross_alias_relationships_are_rejected')
        def overwrite_options(namespace):
            namespace['DATABASES']['auth']['OPTIONS'].pop('options',None)
            real_apply(namespace)
        with patch.object(contracts,'apply_db_safety',overwrite_options):
            self.killed('test_conflicting_options_connect_timeout_and_pgoptions_fail_before_mutation')
        real_expected=dbsafety.expected
        def ignore_pgoptions(namespace):
            environment=dict(os.environ);environment.pop('PGOPTIONS',None)
            with patch.dict(os.environ,environment,clear=True):return real_expected(namespace)
        with patch.object(dbsafety,'expected',ignore_pgoptions):
            self.killed('test_conflicting_options_connect_timeout_and_pgoptions_fail_before_mutation')
        with patch.object(checks,'validate_db_safety',lambda namespace:None):
            self.killed('test_e101_is_specific_flag_gated_and_detects_missing_options')

    def test_real_missing_connection_option_is_detected(self):
        conn=connections['auth']; original=deepcopy(conn.settings_dict['OPTIONS'])
        try:
            conn.close()
            conn.settings_dict['OPTIONS']['options']=original['options'].replace('-c lock_timeout=3000 ','')
            with conn.cursor() as cursor:
                cursor.execute('SHOW lock_timeout');actual=cursor.fetchone()[0]
            with self.assertRaises(AssertionError):self.assertEqual(actual,'3s')
            self.assertEqual(actual,'0')
            print('B1A_MUTATION_KILLED=real_missing_lock_timeout')
        finally:
            conn.close();conn.settings_dict['OPTIONS']=original
