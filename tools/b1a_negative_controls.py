"""B1a mutation controls (L-1). Run with Django's auth/web test runner on real PostgreSQL.

Each control alters PRODUCTION behaviour, never a test-module name, by one of:

* in-memory: a context-managed patch of a production object (restored on exit), with a
  hit counter proving the mutated code actually ran during the target test;
* checkout: an exact-once text replacement in a disposable copy of ``server/`` inside a
  TemporaryDirectory, with the real target test run in a fresh subprocess whose
  imports are verified to come from that copy. Tracked files are never written.

A control counts as DETECTED only if (1) the unmutated target passes in the same
mechanism, (2) the mutation was exercised, (3) the mutated target records at least one
assertion failure and (4) no infrastructure error occurs. Anything else is UNDETECTED
and fails this module. Output lines: B1A_MUTATION_DETECTED=<id> / B1A_MUTATION_UNDETECTED=<id>.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.db import connections, OperationalError
from django.test import TransactionTestCase
from accounts import checks, dbsafety, throttling, views
from auth_tests import test_b1_database, test_b1_sessions, test_b1_settings

SERVER = Path(test_b1_settings.__file__).resolve().parents[1]
SETTINGS_TARGETS = {
    'fixed': 'auth_tests.test_b1_settings.SafetyConfigurationTests.test_fixed_options_tls_idempotence_and_migrator_exclusion',
    'types': 'auth_tests.test_b1_settings.SafetyConfigurationTests.test_bad_types_ranges_and_cross_alias_relationships_are_rejected',
    'conflict': 'auth_tests.test_b1_settings.SafetyConfigurationTests.test_conflicting_options_connect_timeout_and_pgoptions_fail_before_mutation',
    'e101': 'auth_tests.test_b1_settings.SafetyConfigurationTests.test_e101_is_specific_flag_gated_and_detects_missing_options',
    'profiles': 'auth_tests.test_b1_settings.SafetyConfigurationTests.test_profiles_and_real_web_secure_check_command',
}
CHECKOUT_DRIVER = r'''
import json, os, sys, unittest
import django
django.setup()
import accounts.dbsafety, accounts.apps, config.settings.auth_common
root = os.path.realpath(sys.argv[1])
files = [accounts.dbsafety.__file__, accounts.apps.__file__, config.settings.auth_common.__file__]
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:])
result = unittest.TestResult()
suite(result)
print('B1A_DRIVER=' + json.dumps({
    'inside_checkout': all(os.path.realpath(f).startswith(root + os.sep) for f in files),
    'run': result.testsRun, 'failures': len(result.failures),
    'errors': [type(e[0]).__name__ + ':' + e[1].strip().splitlines()[-1][:160] for e in result.errors]}))
'''


class Counter:
    def __init__(self):self.hits=0


def outcome(result):
    return {'run': result.testsRun, 'failures': len(result.failures),
            'errors': [e[1].strip().splitlines()[-1][:160] for e in result.errors]}


def run_in_process(case_class, method):
    result = unittest.TestResult()
    case_class(method)(result)  # __call__: Django pre-setup/teardown (flush) for DB cases
    connections.close_all()
    return outcome(result)


def run_in_checkout(replacements, targets):
    """Copy server/, apply exact-once replacements, run targets in a fresh subprocess."""
    with tempfile.TemporaryDirectory(prefix='b1a-mutant-') as temp:
        copy = Path(temp, 'server')
        shutil.copytree(SERVER, copy, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        # Mirror the repository layout: server code imports top-level shared modules
        # (for example academic_logic) from the parent of server/.
        for module in SERVER.parent.glob('*.py'):
            shutil.copy2(module, Path(temp, module.name))
        for relative, old, new in replacements:
            path = copy / relative
            text = path.read_text()
            if text.count(old) != 1:
                return {'run': 0, 'failures': 0, 'errors': [f'replacement not exactly once in {relative}'],
                        'inside_checkout': False}
            path.write_text(text.replace(old, new))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(copy), temp)), DJANGO_SETTINGS_MODULE='config.settings.web_test',
                   PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.run([sys.executable, '-c', CHECKOUT_DRIVER, str(copy), *targets],
                                 cwd=copy, env=env, capture_output=True, text=True, timeout=240)
        lines = [line for line in process.stdout.splitlines() if line.startswith('B1A_DRIVER=')]
        if process.returncode != 0 or len(lines) != 1:
            tail = (process.stderr.strip().splitlines() or ['no output'])[-1][:160]
            return {'run': 0, 'failures': 0, 'errors': [f'driver exit {process.returncode}: {tail}'],
                    'inside_checkout': False}
        return json.loads(lines[0][len('B1A_DRIVER='):])


class NegativeControls(TransactionTestCase):
    databases = {'default', 'runtime', 'auth'}

    def judge(self, control, baseline, mutated, exercised):
        valid = (baseline['run'] >= 1 and baseline['failures'] == 0 and not baseline['errors']
                 and baseline.get('inside_checkout', True))
        detected = (valid and exercised and mutated['run'] == baseline['run'] and mutated['failures'] > 0
                    and not mutated['errors'] and mutated.get('inside_checkout', True))
        print(('B1A_MUTATION_DETECTED=' if detected else 'B1A_MUTATION_UNDETECTED=') + control +
              ('' if detected else ' ' + json.dumps({'baseline': baseline, 'mutated': mutated, 'exercised': exercised})))
        return detected

    def run_controls(self, controls):
        undetected = [name for name, run in controls if not run()]
        self.assertEqual(undetected, [], 'Mutations not detected (or not exercised)')

    # ---- In-memory production mutations: settings helper and E101 ----------------------
    def in_memory(self, control, case_class, method, mutation):
        baseline = run_in_process(case_class, method)
        counter = Counter()
        with mutation(counter):
            mutated = run_in_process(case_class, method)
        return self.judge(control, baseline, mutated, counter.hits > 0)

    def test_in_memory_settings_mutations_are_detected(self):
        settings_case = test_b1_settings.SafetyConfigurationTests

        @contextmanager
        def missing_lock_option(counter):
            real = dbsafety.options_for
            def mutant(values, key):
                counter.hits += 1
                return real(values, key).replace('-c lock_timeout=%d ' % values['lock_ms'], '')
            with patch.object(dbsafety, 'options_for', mutant):yield

        @contextmanager
        def timers_leak_to_migrator(counter):
            real = dbsafety.expected
            def mutant(namespace):
                counter.hits += 1
                values, aliases = real(namespace)
                return values, dict(aliases, default=dbsafety.options_for(values, 'runtime_statement_ms'))
            with patch.object(dbsafety, 'expected', mutant):yield

        @contextmanager
        def pgoptions_ignored(counter):
            real = dbsafety.expected
            def mutant(namespace):
                counter.hits += 'PGOPTIONS' in os.environ
                environment = dict(os.environ);environment.pop('PGOPTIONS', None)
                with patch.dict(os.environ, environment, clear=True):return real(namespace)
            with patch.object(dbsafety, 'expected', mutant):yield

        @contextmanager
        def e101_validation_removed(counter):
            def mutant(namespace):counter.hits += 1
            with patch.object(checks, 'validate_db_safety', mutant):yield

        self.run_controls([
            ('in_memory.options_missing_lock_timeout', lambda: self.in_memory(
                'in_memory.options_missing_lock_timeout', settings_case, SETTINGS_TARGETS['fixed'].rsplit('.', 1)[1], missing_lock_option)),
            ('in_memory.timers_leak_to_migrator', lambda: self.in_memory(
                'in_memory.timers_leak_to_migrator', settings_case, SETTINGS_TARGETS['fixed'].rsplit('.', 1)[1], timers_leak_to_migrator)),
            ('in_memory.pgoptions_ignored', lambda: self.in_memory(
                'in_memory.pgoptions_ignored', settings_case, SETTINGS_TARGETS['conflict'].rsplit('.', 1)[1], pgoptions_ignored)),
            ('in_memory.e101_validation_removed', lambda: self.in_memory(
                'in_memory.e101_validation_removed', settings_case, SETTINGS_TARGETS['e101'].rsplit('.', 1)[1], e101_validation_removed)),
        ])

    # ---- Disposable-checkout mutations (settings import, subprocess profiles) ----------
    def test_checkout_mutations_are_detected(self):
        targets = [SETTINGS_TARGETS[key] for key in ('fixed', 'types', 'conflict', 'profiles')]
        baseline_all = run_in_checkout([], targets)
        def checkout(control, replacements, target):
            baseline = dict(baseline_all, run=1) if (baseline_all['run'] == len(targets) and not baseline_all['failures']) else baseline_all
            mutated = run_in_checkout(replacements, [target])
            # Exercise: every replacement applied exactly once and imports came from the copy.
            return self.judge(control, baseline, mutated, mutated.get('inside_checkout', False))
        self.run_controls([
            ('checkout.apply_helper_call_removed', lambda: checkout('checkout.apply_helper_call_removed', [
                ('config/settings/auth_common.py', '    apply_db_safety(namespace)\n', '    pass  # mutant\n')],
                SETTINGS_TARGETS['profiles'])),
            ('checkout.e101_runs_in_inactive_profiles', lambda: checkout('checkout.e101_runs_in_inactive_profiles', [
                ('accounts/apps.py', "if getattr(settings, 'UCC_DB_SAFETY_CONFIGURED', False) is True:", 'if True:'),
                ('accounts/checks.py', "if getattr(settings, 'UCC_DB_SAFETY_CONFIGURED', False) is not True:", 'if False:')],
                SETTINGS_TARGETS['profiles'])),
            ('checkout.tls_options_overwritten', lambda: checkout('checkout.tls_options_overwritten', [
                ('accounts/dbsafety.py', "current.update(options=options, connect_timeout=values['connect_seconds'])",
                 "db['OPTIONS'] = {'options': options, 'connect_timeout': values['connect_seconds']}")],
                SETTINGS_TARGETS['fixed'])),
            ('checkout.float_decimal_silently_coerced', lambda: checkout('checkout.float_decimal_silently_coerced', [
                ('accounts/dbsafety.py', '    if type(value) is int:\n        return value\n',
                 "    if type(value) is int:\n        return value\n    if type(value).__name__ in ('float', 'Decimal'):\n        return int(value)\n")],
                SETTINGS_TARGETS['types'])),
            ('checkout.conflicting_options_overwritten', lambda: checkout('checkout.conflicting_options_overwritten', [
                ('accounts/dbsafety.py', "if not isinstance(existing, str) or existing not in ('', options):", 'if False:')],
                SETTINGS_TARGETS['conflict'])),
        ])

    # ---- In-memory production mutations: session lifecycle and unit persistence --------
    def test_lifecycle_and_persistence_mutations_are_detected(self):
        sessions = test_b1_sessions.SessionUnitTests
        database = test_b1_database.DatabaseTimerTests

        @contextmanager
        def same_account_login_cycles_key(counter):
            real = views.auth_login
            def mutant(request, user):
                session = request.session
                if (session.get(SESSION_KEY) == str(user.pk)
                        and session.get(HASH_SESSION_KEY) == user.get_session_auth_hash()):
                    counter.hits += 1;session.cycle_key()
                return real(request, user)
            with patch.object(views, 'auth_login', mutant):yield

        @contextmanager
        def flush_keeps_prior_session_row(counter):
            def mutant(store):
                counter.hits += 1;store.cycle_key()  # keeps prior data/row instead of deleting it
            with patch.object(SessionStore, 'flush', mutant):yield

        @contextmanager
        def throttle_write_retried(counter):
            real = throttling.rate_limit
            def mutant(request, action):
                try:return real(request, action)
                except Exception:
                    counter.hits += 1;return real(request, action)
            with patch.object(views, 'rate_limit', mutant):yield

        @contextmanager
        def commit_hook_without_real_commit(counter):
            connection = connections['auth']
            def mutant():
                counter.hits += 1;raise OperationalError('mutant: COMMIT reported without committing')
            try:
                with patch.object(connection, '_commit', mutant):yield
            finally:connection.close()

        @contextmanager
        def autocommit_writes_rolled_back_with_request(counter):
            # Wraps each auth request in one transaction, so a later failure would roll
            # back the throttle increment that is currently an independent autocommit unit.
            from django.core.handlers.base import BaseHandler
            settings_dict = connections.settings['auth']
            original = settings_dict['ATOMIC_REQUESTS']
            real_wrap = BaseHandler.make_view_atomic
            def counting_wrap(handler, view):
                wrapped = real_wrap(handler, view)
                counter.hits += wrapped is not view  # exercised only if a view was really wrapped
                return wrapped
            settings_dict['ATOMIC_REQUESTS'] = True
            try:
                with patch.object(BaseHandler, 'make_view_atomic', counting_wrap):yield
            finally:
                settings_dict['ATOMIC_REQUESTS'] = original
                connections.close_all()

        self.run_controls([
            ('in_memory.same_account_login_cycles_key', lambda: self.in_memory(
                'in_memory.same_account_login_cycles_key', sessions,
                'test_all_five_successful_login_lifecycles_and_save_kinds', same_account_login_cycles_key)),
            ('in_memory.flush_keeps_prior_session_row', lambda: self.in_memory(
                'in_memory.flush_keeps_prior_session_row', sessions,
                'test_all_five_successful_login_lifecycles_and_save_kinds', flush_keeps_prior_session_row)),
            ('in_memory.throttle_write_retried', lambda: self.in_memory(
                'in_memory.throttle_write_retried', database,
                'test_timed_out_throttle_does_not_increment_or_retry', throttle_write_retried)),
            ('in_memory.commit_hook_without_real_commit', lambda: self.in_memory(
                'in_memory.commit_hook_without_real_commit', database,
                'test_explicit_rollback_and_real_commit_then_lost_ack_are_distinct', commit_hook_without_real_commit)),
            ('in_memory.autocommit_writes_rolled_back_with_request', lambda: self.in_memory(
                'in_memory.autocommit_writes_rolled_back_with_request', database,
                'test_autocommit_post_execute_error_does_not_undo_throttle', autocommit_writes_rolled_back_with_request)),
        ])

    def test_real_missing_connection_option_is_detected(self):
        conn=connections['auth']; original=deepcopy(conn.settings_dict['OPTIONS'])
        try:
            conn.close()
            conn.settings_dict['OPTIONS']['options']=original['options'].replace('-c lock_timeout=3000 ','')
            with conn.cursor() as cursor:
                cursor.execute('SHOW lock_timeout');actual=cursor.fetchone()[0]
            with self.assertRaises(AssertionError):self.assertEqual(actual,'3s')
            self.assertEqual(actual,'0')
            print('B1A_MUTATION_DETECTED=real_connection.missing_lock_timeout')
        finally:
            conn.close();conn.settings_dict['OPTIONS']=original
