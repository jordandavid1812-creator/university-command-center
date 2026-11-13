"""B1a observes Django's existing session units; it does not change their policy."""
from concurrent.futures import ThreadPoolExecutor
import sys
from unittest.mock import patch
from django.core.signals import got_request_exception
from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import connections, transaction, OperationalError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from accounts import views
from accounts.models import Student
from .base import AuthenticationCase, PASSWORD, NEW_PASSWORD
from .test_b1_database import thread_call, sqlstate


def capture_auth_errors(errors):
    """Record (SQL text with placeholders only, SQLSTATE) for each failing auth statement
    in this thread. Parameters are never captured or printed."""
    def capture(execute,sql,params,many,context):
        try:return execute(sql,params,many,context)
        except Exception as exc:
            errors.append((' '.join(sql.split()),sqlstate(exc)));raise
    return connections['auth'].execute_wrapper(capture)


class RequestExceptions:
    """got_request_exception receiver, connected only for one request and always removed."""
    def __init__(self):self.states=[]
    def receive(self,sender,request=None,**kwargs):self.states.append(sqlstate(sys.exc_info()[1]))
    def __enter__(self):
        got_request_exception.connect(self.receive,weak=False,dispatch_uid='b1a-l3-capture');return self
    def __exit__(self,*exc):
        got_request_exception.disconnect(dispatch_uid='b1a-l3-capture');return False


class SessionUnitTests(AuthenticationCase):
    def client_state(self, state):
        self._client_index=getattr(self,'_client_index',0)+1
        client=Client(raise_request_exception=False,REMOTE_ADDR=f'10.62.0.{self._client_index}')
        if state=='AN':
            session=client.session;session['synthetic']=True;session.save()
        elif state in ('SA','SX','DA'):
            self.assertEqual(self.login(client,username='bravo' if state=='DA' else 'alpha').status_code,302)
            if state=='SX':
                session=client.session;session[HASH_SESSION_KEY]='synthetic-stale-hash';session.save()
        key=client.cookies.get(settings.SESSION_COOKIE_NAME)
        return client,key.value if key else None

    def no_new_cookie(self,response,old=None):
        cookie=response.cookies.get(settings.SESSION_COOKIE_NAME)
        if cookie:
            self.assertEqual(cookie.value,'','Failure must not deliver/renew an authenticated key')

    def test_all_five_successful_login_lifecycles_and_save_kinds(self):
        for state in ('N','AN','SA','SX','DA'):
            with self.subTest(state=state):
                Session.objects.using('auth').all().delete()
                client,old=self.client_state(state);cycles=[];inside=[];saves=[]
                real_cycle=SessionStore.cycle_key;real_login=views.auth_login
                def cycle(store):cycles.append(1);return real_cycle(store)
                def login(request,user):
                    result=real_login(request,user)
                    inside.append((request.session.session_key,Session.objects.using('auth').count()))
                    return result
                def inspect(execute,sql,params,many,context):
                    if 'django_session' in sql and sql.startswith(('UPDATE','INSERT')):saves.append(sql.split()[0])
                    return execute(sql,params,many,context)
                with patch.object(SessionStore,'cycle_key',cycle),patch.object(views,'auth_login',login),connections['auth'].execute_wrapper(inspect):
                    response=self.login(client)
                self.assertEqual(response.status_code,302)
                self.assertEqual(len(cycles),1 if state in ('N','AN') else 0)
                self.assertEqual(inside[0][1],0 if state in ('SX','DA') else 1)
                self.assertEqual(inside[0][0] is None,state in ('SX','DA'))
                key=client.cookies[settings.SESSION_COOKIE_NAME].value
                self.assertEqual(key==old,state=='SA')
                self.assertEqual(saves[-1],'INSERT' if state in ('SX','DA') else 'UPDATE')
                self.assertEqual(Session.objects.using('auth').count(),1)
                self.assertEqual(client.session[SESSION_KEY],str(self.a.pk))

    def test_session_insert_and_exists_failures_deliver_no_new_key(self):
        for state in ('N','AN','SA','SX','DA'):
            # L4i is the response-phase INSERT/exists path only for SX/DA.
            if state not in ('SX','DA'):continue
            for kind in ('SELECT','INSERT'):
                with self.subTest(state=state,kind=kind):
                    Session.objects.using('auth').all().delete();client,old=self.client_state(state);seen=[];armed=[]
                    real_save=SessionStore.save
                    def save(store,must_create=False):
                        if not connections['auth'].in_atomic_block:armed.append(True)
                        return real_save(store,must_create=must_create)
                    def fault(execute,sql,params,many,context):
                        if armed and 'django_session' in sql and sql.startswith(kind):
                            seen.append(1);raise OperationalError('synthetic response creation fault')
                        return execute(sql,params,many,context)
                    with connections['auth'].execute_wrapper(fault),patch.object(SessionStore,'save',save):response=self.login(client)
                    self.assertEqual(response.status_code,500);self.assertEqual(len(seen),1)
                    self.no_new_cookie(response,old)
                    self.assertEqual(Session.objects.using('auth').count(),0)

    def test_response_save_precommit_rollback_and_postcommit_persistence(self):
        for state in ('N','AN','SA','SX','DA'):
            for committed in (False,True):
                with self.subTest(state=state,committed=committed):
                    Session.objects.using('auth').all().delete();client,old=self.client_state(state)
                    before=list(Session.objects.using('auth').values_list('session_key','expire_date'))
                    store_real=SessionStore.save;armed=[];count=[]
                    def save(store,must_create=False):
                        # auth_login create/cycle is inside finalizer, response save is outside it.
                        if not connections['auth'].in_atomic_block:armed.append(True)
                        return store_real(store,must_create=must_create)
                    real_commit=connections['auth']._commit
                    def commit():
                        if armed:
                            count.append(1)
                            if committed:real_commit()
                            raise OperationalError('synthetic response commit fault')
                        return real_commit()
                    with patch.object(SessionStore,'save',save),patch.object(connections['auth'],'_commit',commit):
                        response=self.login(client)
                    self.assertEqual(response.status_code,500 if state in ('SX','DA') else 400);self.assertEqual(count,[1])
                    self.no_new_cookie(response,old)
                    connections['auth'].close()
                    rows=list(Session.objects.using('auth').all())
                    if state in ('SX','DA'):
                        self.assertEqual(len(rows),1 if committed else 0)
                    else:
                        self.assertEqual(len(rows),1)
                        if committed:self.assertEqual(rows[0].get_decoded()[SESSION_KEY],str(self.a.pk))
                        elif state=='SA':self.assertTrue((rows[0].session_key,rows[0].expire_date)==before[0])
                        else:self.assertNotIn(SESSION_KEY,rows[0].get_decoded())
                    if state=='SA':
                        self.assertTrue(rows[0].session_key==old)
                        prior=before[0][1];after=rows[0].expire_date
                        # L-5: existing semantics allow renewal (D-B1-1); never a shorter expiry.
                        self.assertGreaterEqual(after,prior)
                        outcome='renewed' if after>prior else 'preserved'
                        if not committed:self.assertEqual(outcome,'preserved')
                        print(f'B1A_SA_L5U_EXPIRY committed={committed} outcome={outcome}')

    def test_real_session_update_lock_timeout_keeps_prior_key_and_expiry(self):
        client,old=self.client_state('SA');before=Session.objects.using('auth').get(pk=old).expire_date
        errors=[]
        def request():
            with capture_auth_errors(errors):return self.login(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                Session.objects.using('default').select_for_update().get(pk=old)
                response=pool.submit(thread_call(request)).result(timeout=15)
        self.assertEqual(response.status_code,503)
        # L-3: the 503 must come from a real lock timeout on the response session UPDATE.
        self.assertEqual(len(errors),1)
        self.assertTrue(errors[0][0].startswith('UPDATE "django_session" SET'))
        self.assertEqual(errors[0][1],'55P03')
        self.no_new_cookie(response,old)
        saved=Session.objects.using('auth').get(pk=old)
        self.assertEqual(saved.expire_date,before)
        self.assertEqual(saved.get_decoded()[SESSION_KEY],str(self.a.pk))

    def test_password_change_lock_timeout_keeps_existing_authority(self):
        client,old=self.client_state('SA')
        def request():
            return client.post(reverse('accounts:password-change'),{
                'old_password':PASSWORD,'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                response=pool.submit(thread_call(request)).result(timeout=15)
        self.assertEqual(response.status_code,503);self.no_new_cookie(response,old)
        self.assertEqual(Session.objects.using('auth').get(pk=old).get_decoded()[SESSION_KEY],str(self.a.pk))
        self.assertTrue(Student.objects.using('auth').get(pk=self.a.pk).check_password(PASSWORD))

    def test_django_createerror_key_collision_retry_is_preserved(self):
        client,old=self.client_state('SA');store=SessionStore();fresh=store._get_new_session_key()
        sent=[]
        def inspect(execute,sql,params,many,context):
            if sql.startswith('INSERT INTO "django_session"'):sent.append(1)
            return execute(sql,params,many,context)
        with patch.object(store,'_get_new_session_key',side_effect=[old,fresh]),connections['auth'].execute_wrapper(inspect):
            store['synthetic']=True;store.create()
        self.assertEqual(len(sent),2)
        self.assertTrue(store.session_key==fresh)
        self.assertEqual(Session.objects.using('auth').count(),2)

    def test_login_l0_l1_timeouts_preserve_prior_authority_for_all_states(self):
        from accounts.models import AuthThrottle
        from django.utils.crypto import salted_hmac
        from datetime import timedelta
        for state in ('N','AN','SA','SX','DA'):
            for phase in ('L0','L1'):
                with self.subTest(state=state,phase=phase):
                    Session.objects.using('auth').all().delete()
                    client,old=self.client_state(state)
                    before=list(Session.objects.using('auth').values_list('session_key','session_data','expire_date'))
                    bucket=salted_hmac('ucc-auth-rate',f"login|{client.defaults['REMOTE_ADDR']}",algorithm='sha256').hexdigest()
                    AuthThrottle.objects.using('auth').update_or_create(bucket=bucket,defaults={
                        'attempts':1,'expires_at':timezone.now()+timedelta(minutes=15)})
                    errors=[]
                    def request():
                        with capture_auth_errors(errors),RequestExceptions() as raised:
                            return self.login(client),raised.states
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        with transaction.atomic(using='default'):
                            if phase=='L0':AuthThrottle.objects.using('default').select_for_update().get(pk=bucket)
                            else:Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                            response,raised=pool.submit(thread_call(request)).result(timeout=15)
                    self.assertEqual(response.status_code,503)
                    # L-3: exactly the nominated statement failed with a real lock timeout,
                    # and that exception (not another error) produced the classified response.
                    self.assertEqual(len(errors),1)
                    statement,state_code=errors[0]
                    self.assertEqual(state_code,'55P03')
                    if phase=='L0':self.assertTrue(statement.startswith('INSERT INTO accounts_auththrottle'))
                    else:self.assertTrue(statement.startswith('SELECT') and 'FROM "accounts_student"' in statement
                                         and statement.endswith('FOR UPDATE'))
                    self.assertEqual(raised,[])  # B1c consumes the proven outage before got_request_exception.
                    self.no_new_cookie(response,old)
                    after=list(Session.objects.using('auth').values_list('session_key','session_data','expire_date'))
                    self.assertEqual(after,before)
                    if state in ('SA','DA'):
                        expected=self.b if state=='DA' else self.a
                        self.assertEqual(Session.objects.using('auth').get(pk=old).get_decoded()[SESSION_KEY],str(expected.pk))
