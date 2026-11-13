"""Real PG17, restricted-role B1c routes and per-phase session evidence."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from io import StringIO
import logging
import os
import select
import socket
from threading import Event, Thread
import time
from unittest.mock import patch
from urllib.parse import urlsplit
import psycopg
from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import BadRequest
from django.db import connections, transaction, DatabaseError, OperationalError
from django.http import HttpResponse
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from accounts import views, tokens, failure_classification as fc, failure_response as fr
from accounts.models import Student, AccountToken, AuthThrottle
from accounts.logging import FailureCategory as C
from .base import AuthenticationCase, PASSWORD, NEW_PASSWORD
from . import test_b1_sessions as lifecycle
from .test_b1_database import thread_call, sqlstate
from .test_b1c_classification import unknown

S='B1C-PRIVATE-SENTINEL'


def admin():
    """Test-only termination fixture; credentials never enter application settings."""
    name=connections['auth'].settings_dict['NAME']
    if os.environ.get('UCC_DISPOSABLE_TEST_CLUSTER')!='1' or not name.startswith('test_'):
        raise AssertionError('Termination requires a disposable test database')
    return psycopg.connect(host=os.environ['PGHOST'],port=os.environ['PGPORT'],
                          user=os.environ['UCC_TEST_DBA_USER'],dbname=name,autocommit=True)


class FailureRouteTests(AuthenticationCase):
    client_state=lifecycle.SessionUnitTests.client_state
    no_new_cookie=lifecycle.SessionUnitTests.no_new_cookie

    def headers(self,response,category):
        self.assertEqual(response.status_code,503 if category in (C.OUTAGE,C.CONFIGURATION,C.CONNECTION_UNAVAILABLE) else 500)
        self.assertIn('no-store',[v.strip() for v in response.get('Cache-Control','').split(',')])
        self.assertEqual(response.get('Retry-After'),'5' if category is C.OUTAGE else None)
        self.assertEqual(response['Content-Type'],'text/plain; charset=utf-8')
        self.no_new_cookie(response)

    def test_unknown_operational_defects_route_500_and_sink_masks_codes(self):
        client=Client(raise_request_exception=False);stream=StringIO()
        with patch.object(logging.getLogger().handlers[0],'stream',stream):
            for code in ('27ZZZ','2FZZZ','38ZZZ','39ZZZ','3BZZZ','40ZZZ','54ZZZ','55ZZZ','57ZZZ','58ZZZ','F0ZZZ','HVZZZ'):
                with self.subTest(code=code),patch.object(views,'rate_limit',side_effect=unknown(code)):
                    self.headers(self.login(client),C.DEFECT)
        self.assertNotIn(S,stream.getvalue())
        for code in ('55ZZZ','54ZZZ','58ZZZ','F0ZZZ','40ZZZ'):self.assertNotIn(code,stream.getvalue())
        self.assertNotIn('logger=accounts.failures ',stream.getvalue())

    def test_response_update_driver_errors_and_insert_exists_handlers(self):
        for state in ('N','AN','SA','SX','DA'):
            for code,category in [('55P03',C.OUTAGE),('42703',C.DEFECT),('42P01',C.DEFECT),('42501',C.CONFIGURATION),(None,C.CONNECTION_UNAVAILABLE)]:
                for kind in (('SELECT','INSERT') if state in ('SX','DA') else ('UPDATE',)):
                    with self.subTest(state=state,code=code,kind=kind):
                        Session.objects.using('auth').all().delete();client,old=self.client_state(state);hits=[];armed=[]
                        before=list(Session.objects.using('auth').values_list('session_key','session_data','expire_date'))
                        real=SessionStore.save
                        def save(store,must_create=False):
                            if not connections['auth'].in_atomic_block:armed.append(True)
                            return real(store,must_create)
                        def fault(execute,sql,params,many,context):
                            if armed and 'django_session' in sql and sql.startswith(kind):
                                hits.append(1)
                                raise OperationalError(S) from (unknown(code) if code else psycopg.OperationalError(S))
                            return execute(sql,params,many,context)
                        with patch.object(SessionStore,'save',save),connections['auth'].execute_wrapper(fault):response=self.login(client)
                        self.headers(response,category);self.assertEqual(hits,[1])
                        after=list(Session.objects.using('auth').values_list('session_key','session_data','expire_date'))
                        if state in ('SX','DA'):self.assertEqual(after,[])
                        elif state=='SA':self.assertEqual(after,before)
                        else:
                            # N/AN finalizer creates/cycles an anonymous row before
                            # the failed response UPDATE; it must have no authority.
                            self.assertEqual(len(after),1)
                            row=Session.objects.using('auth').get(pk=after[0][0])
                            self.assertNotIn(SESSION_KEY,row.get_decoded())
                            if state=='AN':self.assertFalse(Session.objects.using('auth').filter(pk=old).exists())

    def test_real_concurrent_deletion_and_non_db_badrequest_keep_original_400(self):
        client,key=self.client_state('SA');real=SessionStore.save;hits=[]
        def save(store,must_create=False):
            if not connections['auth'].in_atomic_block:
                hits.append(1);Session.objects.using('default').filter(pk=key).delete()
            return real(store,must_create)
        with patch.object(SessionStore,'save',save):response=self.login(client)
        self.assertEqual(response.status_code,400);self.assertEqual(hits,[1]);self.no_new_cookie(response)
        with patch.object(views,'rate_limit',side_effect=BadRequest(S)):
            self.assertEqual(self.login(client).status_code,400)
        if settings.ROOT_URLCONF=='config.web_urls':self.assertContains(response,'Check your request',status_code=400)

    def test_real_missing_column_on_lazy_session_load_is_minimal500(self):
        client,key=self.client_state('SA');observed=[]
        def read_session(request,*args):
            try:request.session.get('synthetic')
            except DatabaseError as exc:observed.append(sqlstate(exc));raise
        try:
            with connections['default'].cursor() as c:c.execute('ALTER TABLE django_session RENAME COLUMN session_data TO b1c_missing_data')
            with patch.object(views,'rate_limit',read_session):response=self.login(client)
        finally:
            with connections['default'].cursor() as c:c.execute('ALTER TABLE django_session RENAME COLUMN b1c_missing_data TO session_data')
        self.headers(response,C.DEFECT);self.assertEqual(observed,['42703'])

    def test_real_session_lock_timeout_and_prior_key_expiry(self):
        client,key=self.client_state('SA');before=Session.objects.using('auth').get(pk=key).expire_date
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                Session.objects.using('default').select_for_update().get(pk=key)
                response=pool.submit(thread_call(lambda:self.login(client))).result(timeout=15)
        self.headers(response,C.OUTAGE)
        row=Session.objects.using('auth').get(pk=key);self.assertEqual(row.expire_date,before)
        self.assertEqual(row.get_decoded()[SESSION_KEY],str(self.a.pk))

    def test_real_statement_and_idle_timers_on_account_routes(self):
        for mode in ('statement','idle'):
            observed=[]
            def fault(request,*args):
                conn=connections['auth']
                try:
                    with conn.cursor() as c:
                        if mode=='statement':c.execute('SELECT pg_sleep(6)')
                        else:
                            c.execute('BEGIN');c.execute('SELECT pg_backend_pid()');pid=c.fetchone()[0]
                            deadline=time.monotonic()+settings.UCC_DB_SAFETY_VALUES['idle_ms']/1000+5
                            while time.monotonic()<deadline:
                                with connections['default'].cursor() as observer:
                                    observer.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s',[pid]);alive=observer.fetchone()[0]
                                if not alive:break
                                time.sleep(.1)
                            self.assertFalse(alive,'Idle timeout did not terminate the observed auth backend')
                            c.execute('SELECT 1')
                except DatabaseError as exc:observed.append(sqlstate(exc));raise
            try:
                with patch.object(views,'rate_limit',fault):response=self.login(Client(raise_request_exception=False))
                self.headers(response,C.OUTAGE);self.assertEqual(observed,['57014' if mode=='statement' else '25P03'])
            finally:connections['auth'].close()
            with connections['auth'].cursor() as c:c.execute('SELECT 1');self.assertEqual(c.fetchone(),(1,))

    def test_real_termination_before_response_update(self):
        client,key=self.client_state('SA');real=SessionStore.save;hits=[];observed=[]
        def save(store,must_create=False):
            if not connections['auth'].in_atomic_block:
                with connections['auth'].cursor() as c:c.execute('SELECT pg_backend_pid()');pid=c.fetchone()[0]
                with admin() as observer:self.assertTrue(observer.execute('SELECT pg_terminate_backend(%s)',[pid]).fetchone()[0])
                hits.append(1)
            try:return real(store,must_create)
            except Exception as exc:observed.append(sqlstate(exc));raise
        try:
            with patch.object(SessionStore,'save',save):response=self.login(client)
            self.assertEqual(hits,[1]);self.assertEqual(len(observed),1)
            self.headers(response,C.OUTAGE if observed[0]=='57P01' else C.CONNECTION_UNAVAILABLE)
            self.assertIn(observed[0],('57P01',None))
        finally:connections['auth'].close()

    def test_tcp_relay_loss_without_sqlstate_is503_without_retry(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        stop=Event();ready=Event();errors=[]
        def relay():
            sockets=[]
            try:
                listener.settimeout(10);front,_=listener.accept();sockets.append(front)
                back=socket.create_connection((os.environ['PGHOST'],int(os.environ['PGPORT'])));sockets.append(back)
                ready.set()
                while not stop.is_set():
                    readable,_,_=select.select(sockets,[],[],.05)
                    for src in readable:
                        data=src.recv(65536)
                        if not data:return
                        (back if src is front else front).sendall(data)
            except Exception as exc:errors.append(type(exc).__name__)
            finally:
                for sock in sockets:sock.close()
        worker=Thread(target=relay,daemon=True);worker.start()
        conn=None
        try:
            params=connections['auth'].get_connection_params();params.update(host='127.0.0.1',port=listener.getsockname()[1])
            conn=psycopg.connect(**params,autocommit=True);self.assertTrue(ready.is_set())
            self.assertEqual(conn.execute('SELECT 1').fetchone(),(1,));stop.set();worker.join(5);self.assertFalse(worker.is_alive())
            def fault(*args):conn.execute('SELECT 1')
            with patch.object(views,'rate_limit',fault):response=self.login(Client(raise_request_exception=False))
            self.headers(response,C.CONNECTION_UNAVAILABLE);self.assertEqual(errors,[])
        finally:
            stop.set();listener.close()
            if conn:conn.close()
            worker.join(5)

    def test_rendering_zero_queries_and_no_identity_template_access(self):
        from accounts.failure_handlers import auth_server_error,web_server_error
        class ForbiddenRequest:
            def __getattr__(self,name):raise AssertionError('Request data accessed')
        with ExitStack() as stack:
            captures=[stack.enter_context(CaptureQueriesContext(connections[a])) for a in ('default','auth','runtime')]
            stack.enter_context(patch('django.template.loader.get_template',side_effect=AssertionError('template')))
            for category in C:fr.failure_response(category)
            auth_server_error(ForbiddenRequest());web_server_error(ForbiddenRequest())
        self.assertEqual([len(c) for c in captures],[0,0,0])

    def test_role_academic_and_registration_contracts_preserved(self):
        client=Client(raise_request_exception=False)
        with patch('accounts.middleware.require_auth_role',side_effect=__import__('django.db',fromlist=['ProgrammingError']).ProgrammingError()):
            response=self.login(client)
        self.assertEqual(response.status_code,503);self.assertNotIn('Retry-After',response)
        self.assertIn(b'not configured safely',response.content)
        self.login(client)
        with patch('academics.services.courses.list',side_effect=__import__('django.db',fromlist=['ProgrammingError']).ProgrammingError()):
            # API course retrieve is protected by academic_errors in both profiles.
            with patch('academics.services.courses.retrieve',side_effect=OperationalError()):
                from uuid import uuid4
                self.assertEqual(client.get(reverse('accounts:course',args=[uuid4()])).status_code,503)
        from django.db import IntegrityError
        with patch('accounts.tokens.Student.save',side_effect=IntegrityError()):
            response=client.post(reverse('accounts:register'),{'username':'synthetic-new','email':'new@example.invalid','password1':PASSWORD,'password2':PASSWORD})
        self.assertEqual(response.status_code,200)

    def test_response_middleware_and_classifier_failures_privacy(self):
        stream=StringIO();client=Client(raise_request_exception=False)
        with patch.object(logging.getLogger().handlers[0],'stream',stream):
            with patch('django.middleware.clickjacking.XFrameOptionsMiddleware.process_response',side_effect=unknown('42703')):
                self.headers(client.get(reverse('accounts:login')),C.DEFECT)
            with patch.object(fc,'classify_database_failure',side_effect=RuntimeError(S)):
                with patch.object(views,'rate_limit',side_effect=OperationalError(S)):
                    self.headers(self.login(client),C.DEFECT)
        self.assertNotIn(S,stream.getvalue())
        self.assertEqual(stream.getvalue().count('logger=accounts.failures '),1)

    def test_new_failure_routes_final_sink_bytes_and_separate_framework_records(self):
        stream=StringIO();client=Client(raise_request_exception=False,HTTP_COOKIE='sessionid='+S,
           HTTP_AUTHORIZATION=S,HTTP_USER_AGENT=S,REMOTE_ADDR='192.0.2.77')
        with patch.object(logging.getLogger().handlers[0],'stream',stream):
            for code in ('55P03','42501','42703','55ZZZ'):
                exc=unknown(code);exc.args=(S,)
                with patch.object(views,'rate_limit',side_effect=exc):
                    response=client.post(reverse('accounts:login')+'?'+S,{'username':S,'password':S})
                self.headers(response,C.OUTAGE if code=='55P03' else C.CONFIGURATION if code=='42501' else C.DEFECT)
        output=stream.getvalue();self.assertNotIn(S,output);self.assertNotIn('192.0.2.77',output)
        self.assertEqual(output.count('logger=accounts.failures '),2)
        self.assertEqual(output.count('logger=django.request '),4)

    def test_body_constancy_and_timing_observation_not_enumeration_proof(self):
        samples={}
        for name in ('alpha','synthetic-missing'):
            times=[];bodies=[];statuses=[]
            for _ in range(4):
                started=time.monotonic()
                with patch.object(views,'rate_limit',side_effect=unknown('55P03')):
                    response=self.login(Client(raise_request_exception=False),username=name)
                times.append(time.monotonic()-started);bodies.append(response.content);statuses.append(response.status_code)
            samples[name]=(bodies,statuses)
            print('B1C_SYNTHETIC_OUTAGE_TIMING account_kind=%s samples=4 min_seconds=%.6f max_seconds=%.6f'%('known' if name=='alpha' else 'unknown',min(times),max(times)))
        self.assertEqual(samples['alpha'],samples['synthetic-missing'])

    def test_renderer_and_preserved_handler_failures_reach_django500(self):
        # One-shot failure lets the actual Django handler500 recovery build its body.
        real=fr._plain_response;hits=[]
        def fail_once(*args):
            hits.append(1)
            if len(hits)==1:raise RuntimeError(S)
            return real(*args)
        client=Client(raise_request_exception=False)
        with patch('student_web.views.bad_request',side_effect=unknown('42703')):
            # In the web root, failure of the preserved 400 renderer reaches500.
            if settings.ROOT_URLCONF=='config.web_urls':
                with patch.object(views,'rate_limit',side_effect=BadRequest(S)):
                    self.headers(self.login(client),C.DEFECT)
        with patch.object(fr,'_build',side_effect=RuntimeError(S)),patch.object(fr,'_plain_response',fail_once):
            with patch.object(views,'rate_limit',side_effect=unknown('55P03')):
                response=self.login(client)
        self.assertEqual(response.status_code,500);self.no_new_cookie(response)
        self.assertNotIn(S.encode(),response.content)
        # The fallback exception is opaque, so Django delegates to the preserved
        # non-DB500 handler; minimal-response guarantees do not extend here.
        self.assertEqual(len(hits),1)
