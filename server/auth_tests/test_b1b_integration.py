"""Actual request failure sinks on PostgreSQL; no response-policy changes."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import logging
import time
from unittest.mock import patch
from uuid import uuid4
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import SuspiciousOperation
from django.db import connections, transaction, DatabaseError, OperationalError
from django.test import Client
from django.urls import reverse
from accounts.models import Student
from .base import AuthenticationCase
from .test_b1_database import thread_call, sqlstate
from .test_b1b_logging import S


class RequestSinkTests(AuthenticationCase):
    def sink(self,stream):return patch.object(logging.getLogger().handlers[0],'stream',stream)

    def assert_private(self,stream):
        output=stream.getvalue();self.assertIn('ucc-log ',output);self.assertNotIn(S,output)
        for line in output.splitlines():self.assertTrue(line.startswith('ucc-log '))

    def test_existing_500_400_csrf_and_404_token_paths_have_private_sink_bytes(self):
        headers={'HTTP_AUTHORIZATION':S,'HTTP_COOKIE':'sessionid='+S,'HTTP_USER_AGENT':S,
                 'REMOTE_ADDR':'192.0.2.44'}
        client=Client(raise_request_exception=False,**headers);stream=StringIO()
        with self.sink(stream):
            with patch('accounts.views.rate_limit',side_effect=OperationalError(S)):
                response=client.post(reverse('accounts:login')+'?'+S,{'username':S,'password':S})
            self.assertEqual(response.status_code,500)
            with patch('accounts.views.rate_limit',side_effect=SuspiciousOperation(S)):
                self.assertEqual(client.post(reverse('accounts:login'),{'password':S}).status_code,400)
            for prefix in ('reset','verify'):
                url=f'/accounts/{prefix}/{uuid4()}/{S}/?{S}'
                self.assertEqual(Client(enforce_csrf_checks=True,**headers).post(url,{'password':S}).status_code,403)
            self.assertEqual(client.get('/accounts/reset/malformed/'+S+'/?'+S).status_code,404)
        self.assert_private(stream);self.assertNotIn('192.0.2.44',stream.getvalue())

    def test_genuine_session_update_failure_keeps_400_and_sanitizes_traceback(self):
        client=Client(raise_request_exception=False,REMOTE_ADDR='10.74.0.1');self.login(client)
        real=SessionStore.save;stream=StringIO()
        def fail(store,must_create=False):
            if not connections['auth'].in_atomic_block:raise UpdateError(S)
            return real(store,must_create)
        with self.sink(stream),patch.object(SessionStore,'save',fail):response=self.login(client)
        self.assertEqual(response.status_code,400);self.assert_private(stream)
        self.assertNotIn('sessionid',response.cookies)

    def test_real_session_lock_and_auth_statement_timeouts_are_sanitized(self):
        client=Client(raise_request_exception=False,REMOTE_ADDR='10.74.0.2');self.login(client)
        key=client.cookies['sessionid'].value;stream=StringIO()
        with self.sink(stream),ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                Session.objects.using('default').select_for_update().get(pk=key)
                response=pool.submit(thread_call(lambda:self.login(client))).result(timeout=15)
        self.assertEqual(response.status_code,400);self.assert_private(stream)
        self.assertIn('55P03',stream.getvalue())
        stream=StringIO()
        def delayed(execute,sql,params,many,context):
            if 'INSERT INTO accounts_auththrottle' in sql:execute('SELECT pg_sleep(6)',None,False,context)
            return execute(sql,params,many,context)
        with self.sink(stream),connections['auth'].execute_wrapper(delayed):response=self.login(client)
        self.assertEqual(response.status_code,500);self.assert_private(stream);self.assertIn('57014',stream.getvalue())

    def test_real_idle_termination_logs_only_known_labels(self):
        connection=connections['auth'];stream=StringIO()
        try:
            with connection.cursor() as cursor:cursor.execute('BEGIN');cursor.execute('SELECT 1')
            time.sleep(16)
            with self.sink(stream):
                try:
                    with connection.cursor() as cursor:cursor.execute('SELECT 1')
                except DatabaseError as error:
                    self.assertEqual(sqlstate(error),'25P03')
                    logging.getLogger('django.db.backends').error(S,exc_info=True,extra={'ucc_probe':S})
                else:self.fail('Expected the configured idle timeout')
        finally:connection.close()
        self.assert_private(stream);self.assertIn('25P03',stream.getvalue())
