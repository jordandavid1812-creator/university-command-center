"""B1c A2/A5 and A3/A4: phase-specific rollback, persistence and cookie evidence."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit
import psycopg
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.db import connections, transaction, OperationalError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts import tokens, views
from accounts.models import Student, AccountToken, AuthThrottle
from .base import AuthenticationCase, PASSWORD, NEW_PASSWORD
from . import test_b1_sessions as lifecycle
from .test_b1_database import thread_call, sqlstate
from .test_b1c_classification import unknown
from .test_b1c_database import admin


class TransactionFailureTests(AuthenticationCase):
    client_state=lifecycle.SessionUnitTests.client_state
    no_new_cookie=lifecycle.SessionUnitTests.no_new_cookie

    def observer(self,sql,params=()):
        with psycopg.connect(**connections['auth'].get_connection_params(),autocommit=True) as c:
            return c.execute(sql,params).fetchall()

    def assert_failure(self,response,status=503):
        self.assertEqual(response.status_code,status);self.assertEqual(response['Cache-Control'],'no-store')
        self.no_new_cookie(response)

    def test_login_finalizer_commit_rollback_and_lost_ack_all_initial_states(self):
        for state in ('N','AN','SA','SX','DA'):
            for committed in (False,True):
                with self.subTest(state=state,committed=committed):
                    Session.objects.using('auth').all().delete();client,key=self.client_state(state)
                    before=self.observer('SELECT session_key,session_data,expire_date FROM django_session ORDER BY session_key')
                    last=self.observer('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk])
                    conn=connections['auth'];real=conn._commit;hits=[]
                    def commit():
                        hits.append(1)
                        if committed:real()
                        raise OperationalError('synthetic commit acknowledgement') from unknown('08000')
                    with patch.object(conn,'_commit',commit):response=self.login(client)
                    self.assert_failure(response);self.assertEqual(hits,[1]);conn.close()
                    after=self.observer('SELECT session_key,session_data,expire_date FROM django_session ORDER BY session_key')
                    self.assertEqual(self.observer('SELECT attempts FROM accounts_auththrottle WHERE attempts>=1')!=[],True)
                    if not committed:
                        self.assertEqual(after,before)
                        self.assertEqual(self.observer('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk]),last)
                    elif state in ('SX','DA'):self.assertEqual(after,[])
                    elif state=='SA':self.assertEqual(after,before)
                    else:
                        self.assertEqual(len(after),1);self.assertNotEqual(after[0][0],key)
                    if state in ('SA','DA') and not committed:
                        self.assertEqual(Session.objects.using('auth').get(pk=key).get_decoded()[SESSION_KEY],str(self.a.pk if state=='SA' else self.b.pk))

    def test_login_last_login_driver_fault_rolls_back_all_states(self):
        for state in ('N','AN','SA','SX','DA'):
            Session.objects.using('auth').all().delete();client,key=self.client_state(state)
            before=self.observer('SELECT session_key,session_data,expire_date FROM django_session ORDER BY session_key');hits=[]
            def fault(execute,sql,params,many,context):
                if sql.startswith('UPDATE "accounts_student"') and '"last_login"' in sql:
                    hits.append(1);raise OperationalError('synthetic') from unknown('55P03')
                return execute(sql,params,many,context)
            with connections['auth'].execute_wrapper(fault):response=self.login(client)
            self.assert_failure(response);self.assertEqual(hits,[1])
            self.assertEqual(self.observer('SELECT session_key,session_data,expire_date FROM django_session ORDER BY session_key'),before)

    def test_response_save_lost_ack_all_states_preserves_permitted_prior_authority(self):
        for state in ('N','AN','SA','SX','DA'):
            Session.objects.using('auth').all().delete();client,key=self.client_state(state);real_save=SessionStore.save
            prior=Session.objects.using('auth').filter(pk=key).first();hits=[]
            def save(store,must_create=False):
                outside=not connections['auth'].in_atomic_block
                result=real_save(store,must_create)
                if outside:
                    hits.append(1);raise OperationalError('synthetic post-execute') from unknown('08000')
                return result
            with patch.object(SessionStore,'save',save):response=self.login(client)
            self.assert_failure(response);self.assertGreaterEqual(len(hits),1);connections['auth'].close()
            rows=list(Session.objects.using('auth').all());self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].get_decoded()[SESSION_KEY],str(self.a.pk))
            if state=='SA':
                self.assertEqual(rows[0].pk,key);self.assertGreaterEqual(rows[0].expire_date,prior.expire_date)
            if state=='DA':self.assertFalse(Session.objects.using('auth').filter(pk=key).exists())

    def test_change_flush_failure_and_precommit_delete_cookie_server_validity(self):
        for phase in ('flush','before_commit','after_commit'):
            Student.objects.using('default').filter(pk=self.a.pk).update(password=self.a.password)
            Session.objects.using('auth').all().delete();client,key=self.client_state('SA');hits=[]
            conn=connections['auth'];real=conn._commit
            def commit():
                hits.append(1)
                if phase=='after_commit':real()
                raise OperationalError('synthetic') from unknown('08000')
            def fault(execute,sql,params,many,context):
                if sql.startswith('DELETE FROM "django_session"'):
                    hits.append(1);raise OperationalError('synthetic') from unknown('55P03')
                return execute(sql,params,many,context)
            with (patch.object(conn,'_commit',commit) if phase!='flush' else conn.execute_wrapper(fault)):
                response=client.post(reverse('accounts:password-change'),{'old_password':PASSWORD,'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
            self.assert_failure(response);self.assertEqual(hits,[1]);conn.close()
            student=Student.objects.using('auth').get(pk=self.a.pk)
            self.assertTrue(student.check_password(NEW_PASSWORD if phase=='after_commit' else PASSWORD))
            self.assertEqual(Session.objects.using('auth').filter(pk=key).exists(),phase!='after_commit')
            if phase=='before_commit':
                self.assertIn(settings.SESSION_COOKIE_NAME,response.cookies)
                self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value,'')
                self.assertEqual(Session.objects.using('auth').get(pk=key).get_decoded()[SESSION_KEY],str(self.a.pk))

    def token_flow(self,flow,state='N'):
        target=self.a if flow=='reset' else self.make_student('verify-synthetic',verified=False)
        tokens.request_email(target.email,flow)
        path=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        token=AccountToken.objects.using('auth').filter(student=target,purpose=flow).latest('created_at')
        client,key=self.client_state(state)
        data={'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD} if flow=='reset' else {}
        return target,token,client,key,path,data

    def test_reset_verify_atomic_writes_and_commit_acknowledgement_matrix(self):
        for flow in ('reset','verify'):
            for state in (('N','SA') if flow=='reset' else ('N',)):
                for phase in ('student_write','token_write','before_commit','after_commit'):
                    with self.subTest(flow=flow,state=state,phase=phase):
                        Student.objects.using('default').filter(pk=self.a.pk).update(password=self.a.password)
                        AccountToken.objects.using('default').filter(student__username='verify-synthetic').delete()
                        Student.objects.using('default').filter(username='verify-synthetic').delete()
                        target,token,client,key,path,data=self.token_flow(flow,state)
                        conn=connections['auth'];real=conn._commit;hits=[]
                        def commit():
                            hits.append(1)
                            if phase=='after_commit':real()
                            raise OperationalError('synthetic uncertain commit') from unknown('08000')
                        def fault(execute,sql,params,many,context):
                            table='accounts_student' if phase=='student_write' else 'accounts_accounttoken'
                            if sql.startswith('UPDATE "'+table+'"'):
                                hits.append(1);raise OperationalError('synthetic') from unknown('55P03')
                            return execute(sql,params,many,context)
                        with (patch.object(conn,'_commit',commit) if 'commit' in phase else conn.execute_wrapper(fault)):
                            response=client.post(path,data)
                        self.assert_failure(response);self.assertEqual(hits,[1]);conn.close()
                        updated=Student.objects.using('auth').get(pk=target.pk);token.refresh_from_db(using='auth')
                        changed=updated.check_password(NEW_PASSWORD) if flow=='reset' else updated.email_verified_at is not None
                        self.assertEqual(changed,phase=='after_commit');self.assertEqual(token.consumed_at is not None,changed)
                        if state=='SA':
                            row=Session.objects.using('auth').filter(pk=key).first()
                            if changed:self.assertIsNone(row)  # committed auth_logout deletes this session
                            else:
                                self.assertIsNotNone(row)
                                self.assertEqual(row.get_decoded()['_auth_user_hash'],updated.get_session_auth_hash())

    def test_reset_verify_real_student_and_token_locks_rollback(self):
        for flow in ('reset','verify'):
            for locked in ('student','token'):
                AccountToken.objects.using('default').filter(student__username='verify-synthetic').delete()
                Student.objects.using('default').filter(username='verify-synthetic').delete()
                target,token,client,key,path,data=self.token_flow(flow)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with transaction.atomic(using='default'):
                        if locked=='student':Student.objects.using('default').select_for_update().get(pk=target.pk)
                        else:AccountToken.objects.using('default').select_for_update().get(pk=token.pk)
                        response=pool.submit(thread_call(lambda:client.post(path,data))).result(timeout=15)
                self.assert_failure(response);token.refresh_from_db(using='auth');self.assertIsNone(token.consumed_at)
                updated=Student.objects.using('auth').get(pk=target.pk)
                self.assertTrue(updated.check_password(PASSWORD));self.assertEqual(updated.email_verified_at,target.email_verified_at)

    def test_real_termination_at_finalizer_commit_retains_only_permitted_states(self):
        client,key=self.client_state('SA');conn=connections['auth'];real=conn._commit;hits=[]
        def commit():
            # Real termination synchronized at the COMMIT-dispatch boundary. Server
            # rollback is observed, not inferred from the resulting HTTP status.
            with conn.cursor() as c:c.execute('SELECT pg_backend_pid()');pid=c.fetchone()[0]
            with admin() as observer:self.assertTrue(observer.execute('SELECT pg_terminate_backend(%s)',[pid]).fetchone()[0])
            hits.append(1);return real()
        last=self.observer('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk])
        try:
            with patch.object(conn,'_commit',commit):response=self.login(client)
            self.assert_failure(response);self.assertEqual(hits,[1])
        finally:conn.close()
        self.assertEqual(self.observer('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk]),last)
        self.assertEqual(Session.objects.using('auth').get(pk=key).get_decoded()[SESSION_KEY],str(self.a.pk))

    def test_same_plaintext_reset_is_valid_but_prior_hash_authority_changes(self):
        self.assertEqual(self.login(self.client_a).status_code,302)
        key=self.client_a.cookies[settings.SESSION_COOKIE_NAME].value
        before=Student.objects.using('auth').get(pk=self.a.pk).password
        tokens.request_email(self.a.email,'reset')
        path=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        response=Client().post(path,{'new_password1':PASSWORD,'new_password2':PASSWORD})
        self.assertEqual(response.status_code,200)
        updated=Student.objects.using('auth').get(pk=self.a.pk)
        self.assertTrue(updated.check_password(PASSWORD));self.assertNotEqual(updated.password,before)
        self.assertIsNotNone(AccountToken.objects.using('auth').filter(student=self.a,purpose='reset').latest('created_at').consumed_at)
        self.assertNotEqual(Session.objects.using('auth').get(pk=key).get_decoded()['_auth_user_hash'],updated.get_session_auth_hash())
