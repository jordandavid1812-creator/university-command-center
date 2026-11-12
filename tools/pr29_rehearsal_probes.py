"""Independent PR29 probes. Import against the pinned implementation, not this docs branch.
Run with auth_test settings, PostgreSQL 17 and AuthenticationTestRunner; see audit report.
All identities are synthetic. Hooks schedule races or inject faults; no fix is patched in.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password, make_password
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.core import mail
from django.db import OperationalError, connections, transaction
from django.test import Client, override_settings
from django.urls import reverse

from accounts.backends import upgrade_password_hash
from accounts.models import Student
from accounts.principals import session_student
from auth_tests.base import AuthenticationCase, PASSWORD, NEW_PASSWORD


class IndependentRaceTests(AuthenticationCase):
    def blocked(self, pid):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with connections['default'].cursor() as cursor:
                cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0', [pid])
                if cursor.fetchone()[0]:
                    return
            time.sleep(.01)
        self.fail('Worker did not actually block on a PostgreSQL lock')

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher',
                                       'django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_cas_rechecks_predicate_after_waiting_for_committed_reset(self):
        weak = PBKDF2PasswordHasher().encode(PASSWORD, 'synthetic-audit-salt', iterations=1000)
        Student.objects.using('default').filter(pk=self.a.pk).update(password=weak)
        entered = Event()
        state = {}

        def worker():
            try:
                stale = Student.objects.using('auth').get(pk=self.a.pk)
                with connections['auth'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    state['pid'] = cursor.fetchone()[0]
                entered.set()
                return upgrade_password_hash(stale, PASSWORD)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='default'):
                Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                future = executor.submit(worker)
                self.assertTrue(entered.wait(10))
                self.blocked(state['pid'])
                Student.objects.using('default').filter(pk=self.a.pk).update(password=make_password(NEW_PASSWORD))
            self.assertFalse(future.result(timeout=20))
        saved = Student.objects.using('default').get(pk=self.a.pk).password
        self.assertTrue(check_password(NEW_PASSWORD, saved))
        self.assertFalse(check_password(PASSWORD, saved))

    def test_login_lock_rechecks_new_password_after_waiting(self):
        entered = Event()
        state = {}
        client = Client(REMOTE_ADDR='10.29.0.1')

        def worker():
            try:
                with connections['auth'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    state['pid'] = cursor.fetchone()[0]
                def inspect(execute, sql, params, many, context):
                    if 'FOR UPDATE' in sql and 'accounts_student' in sql:
                        entered.set()
                    return execute(sql, params, many, context)
                with connections['auth'].execute_wrapper(inspect):
                    return self.login(client).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='default'):
                Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                future = executor.submit(worker)
                self.assertTrue(entered.wait(10))
                self.blocked(state['pid'])
                Student.objects.using('default').filter(pk=self.a.pk).update(password=make_password(NEW_PASSWORD))
            self.assertEqual(future.result(timeout=20), 200)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_reset_between_login_commit_and_session_middleware_save_denies_session(self):
        self.client.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        link = urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        real = SessionMiddleware.process_response
        state = {}

        def process(middleware, request, response):
            if request.path == reverse('accounts:login') and response.status_code == 302:
                self.assertFalse(connections['auth'].in_atomic_block)
                reset = Client(REMOTE_ADDR='10.29.0.2').post(link, {
                    'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
                self.assertEqual(reset.status_code, 200)
                state['ran'] = True
            return real(middleware, request, response)

        client = Client(REMOTE_ADDR='10.29.0.3')
        with patch.object(SessionMiddleware, 'process_response', process):
            self.assertEqual(self.login(client).status_code, 302)
        self.assertTrue(state['ran'])
        key = client.cookies['sessionid'].value
        # The obsolete auth payload really is persisted AFTER reset, but confers no authority.
        stored = Session.objects.using('auth').get(session_key=key).get_decoded()
        self.assertEqual(stored[SESSION_KEY], str(self.a.pk))
        self.assertNotEqual(stored[HASH_SESSION_KEY], Student.objects.using('auth').get(pk=self.a.pk).get_session_auth_hash())
        self.assertIsNone(session_student(key))
        self.assertEqual(client.get(reverse('accounts:password-change')).status_code, 302)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_lock_database_error_fails_without_persisting_authentication(self):
        def fault(execute, sql, params, many, context):
            if 'FOR UPDATE' in sql and 'accounts_student' in sql:
                raise OperationalError('synthetic lock failure')
            return execute(sql, params, many, context)
        client = Client(raise_request_exception=False, REMOTE_ADDR='10.29.0.4')
        with connections['auth'].execute_wrapper(fault):
            self.assertEqual(self.login(client).status_code, 500)
        self.assertEqual(Session.objects.using('auth').count(), 0)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_failure_after_auth_login_rolls_back_session_row_and_last_login(self):
        from django.contrib.auth.signals import user_logged_in
        def fail(**kwargs):
            raise OperationalError('synthetic post-login failure')
        user_logged_in.connect(fail, weak=False, dispatch_uid='independent-pr29-fault')
        try:
            client = Client(raise_request_exception=False, REMOTE_ADDR='10.29.0.5')
            self.assertEqual(self.login(client).status_code, 500)
            self.assertEqual(Session.objects.using('auth').count(), 0)
            self.assertNotIn(SESSION_KEY, client.session)
            self.assertIsNone(Student.objects.using('auth').get(pk=self.a.pk).last_login)
        finally:
            user_logged_in.disconnect(dispatch_uid='independent-pr29-fault')

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher',
                                       'django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_simultaneous_login_sessions_remain_usable(self):
        weak = PBKDF2PasswordHasher().encode(PASSWORD, 'synthetic-concurrent-salt', iterations=1000)
        Student.objects.using('default').filter(pk=self.a.pk).update(password=weak)
        from threading import Barrier
        barrier = Barrier(4)
        def worker(index):
            client = Client(REMOTE_ADDR=f'10.29.1.{index + 1}')
            try:
                barrier.wait(timeout=10)
                return client, self.login(client).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(worker, range(4)))
        for client, status in results:
            self.assertEqual(status, 302)
            self.assertIsNotNone(session_student(client.cookies['sessionid'].value))
            self.assertEqual(client.get(reverse('accounts:password-change')).status_code, 200)

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher',
                                       'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher'])
    def test_algorithm_migration_upgrades_without_changing_secret(self):
        Student.objects.using('default').filter(pk=self.a.pk).update(
            password=make_password(PASSWORD, hasher='pbkdf2_sha1'))
        self.assertEqual(self.login().status_code, 302)
        encoded = Student.objects.using('auth').get(pk=self.a.pk).password
        self.assertTrue(encoded.startswith('pbkdf2_sha256$'))
        self.assertTrue(check_password(PASSWORD, encoded))

    def test_account_disabled_after_verification_is_rejected(self):
        from accounts import backends
        real = backends.upgrade_password_hash
        def disable(student, raw):
            result = real(student, raw)
            Student.objects.using('default').filter(pk=student.pk).update(is_active=False)
            return result
        client = Client(REMOTE_ADDR='10.29.0.6')
        with patch.object(backends, 'upgrade_password_hash', disable):
            self.assertEqual(self.login(client).status_code, 200)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_real_postgresql_lock_timeout_denies_login(self):
        def worker():
            try:
                with connections['auth'].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '100ms'")
                client = Client(raise_request_exception=False, REMOTE_ADDR='10.29.0.7')
                response = self.login(client)
                return response.status_code, 'sessionid' in client.cookies
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='default'):
                Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                status, has_session_cookie = executor.submit(worker).result(timeout=20)
        self.assertEqual(status, 500)
        self.assertFalse(has_session_cookie)
        self.assertEqual(Session.objects.using('auth').count(), 0)
