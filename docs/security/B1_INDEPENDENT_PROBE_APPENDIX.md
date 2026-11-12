# Independent B1 review probe appendix

Review target: PR36 document `7f438b16f6ed92f5e1714a87396044af76afb20b`. These are executed observation probes, **not B1 implementation or proposed production changes**. They use synthetic identities and disposable PostgreSQL 17 only. Copy each Python block to a private temporary directory under the stated filename; do not add them to application discovery without review.

The first module was executed through the existing post-PR29 read-only source checkout and AuthenticationTestRunner with generated PG*, UCC_AUTH_ROLE/PASSWORD, UCC_RUNTIME_ROLE/PASSWORD, UCC_CONTEXT_SIGNING_KEY and DJANGO_SECRET_KEY test inputs. No credentials are embedded here. The runner requires offline test provisioning and real separate auth/runtime LOGIN roles. Never target a persistent/student database.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/probe/directory PGTESTDATABASE=test_b1_design python server/manage.py test b1_review_probes --settings=config.settings.auth_test -v 2
```

Observer handler500 returns a fixed 500 to expose routing/state without implementing the planned classifier. Method patches inject failures and scheduling only; real PostgreSQL is still used. Tests deliberately assert counterexamples to the plan, so passing does not mean B1 is safe or implemented. Emitted evidence contains booleans/classes/states only, never session keys, actual token URLs, passwords, connection strings or table rows.

## `b1_review_probes.py` — 14 tests

```python
"""Independent B1 design probes: observe existing code, never install a B1 fix."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import sys, time, types
from unittest.mock import patch
from urllib.parse import urlsplit

import psycopg
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core import mail
from django.db import connections, OperationalError, transaction
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import include, path, reverse
from django.utils import timezone
from accounts.models import Student
from accounts.principals import session_student
from auth_tests.base import AuthenticationCase, PASSWORD, NEW_PASSWORD

observed = []
urlconf = types.ModuleType('b1_review_error_urls')
urlconf.urlpatterns = [path('',include('config.auth_urls'))]
def observer500(request):
    observed.append(sys.exc_info()[1])
    return HttpResponse('synthetic safe error',status=500)
urlconf.handler500=observer500
sys.modules[urlconf.__name__]=urlconf

def classes(exc):
    seen=set();out=[]
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc));out.append((type(exc).__name__,getattr(exc,'sqlstate',None)))
        exc=exc.__cause__ if exc.__cause__ is not None else exc.__context__
    return out

def emit(name,**values):
    import json
    print('B1_EVIDENCE='+json.dumps(dict(name=name,**values),sort_keys=True))

@override_settings(ROOT_URLCONF='b1_review_error_urls')
class DesignProbes(AuthenticationCase):
    def setUp(self):
        super().setUp();observed.clear()

    def test_real_session_update_lock_timeout_becomes_400_not_handler500(self):
        client=Client(raise_request_exception=False)
        self.assertEqual(self.login(client).status_code,302)
        key=client.cookies['sessionid'].value
        def worker():
            try:
                with connections['auth'].cursor() as c:c.execute("SET lock_timeout='100ms'")
                with self.assertLogs('django.request',level='WARNING') as captured:
                    result=self.login(client)
                exc=next(r.exc_info[1] for r in captured.records if r.exc_info)
                return result.status_code,classes(exc)
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic(using='default'):
                Session.objects.using('default').select_for_update().get(session_key=key)
                status,chain=executor.submit(worker).result(timeout=15)
        self.assertEqual(status,400)
        self.assertEqual(chain[0][0],'SessionInterrupted')
        self.assertIn(('LockNotAvailable','55P03'),chain)
        self.assertEqual(observed,[])
        emit('session_update_lock_timeout',status=status,chain=chain,handler500_calls=len(observed))

    def test_password_change_before_flush_retains_previous_authenticated_cookie(self):
        client=Client(raise_request_exception=False)
        self.login(client);key=client.cookies['sessionid'].value
        def fail(execute,sql,params,many,context):
            if 'FOR UPDATE' in sql and 'accounts_student' in sql:
                raise OperationalError('synthetic pre-flush lock failure')
            return execute(sql,params,many,context)
        with connections['auth'].execute_wrapper(fail):
            result=client.post(reverse('accounts:password-change'),{'old_password':PASSWORD,
                  'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        self.assertEqual(result.status_code,500)
        self.assertNotIn('sessionid',result.cookies)
        self.assertIsNotNone(session_student(key))
        self.assertEqual(client.get(reverse('accounts:password-change')).status_code,200)
        emit('password_change_pre_flush',status=result.status_code,old_session_valid=True,cookie_deleted=False)

    def test_flush_delete_failure_leaves_key_nonempty_and_old_session_valid(self):
        client=Client(raise_request_exception=False);self.login(client)
        key=client.cookies['sessionid'].value
        def fail(execute,sql,params,many,context):
            if sql.lstrip().startswith('DELETE') and 'django_session' in sql:
                raise OperationalError('synthetic flush delete failure')
            return execute(sql,params,many,context)
        with connections['auth'].execute_wrapper(fail):
            result=client.post(reverse('accounts:password-change'),{'old_password':PASSWORD,
                  'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        self.assertEqual(result.status_code,500)
        self.assertNotIn('sessionid',result.cookies)
        self.assertIsNotNone(session_student(key))
        emit('flush_delete_failure',status=result.status_code,old_session_valid=True,cookie_deleted=False)

    def test_session_update_ack_lost_can_extend_known_existing_session(self):
        client=Client(raise_request_exception=False);self.login(client)
        key=client.cookies['sessionid'].value
        before=timezone.now()+timedelta(seconds=60)
        Session.objects.using('default').filter(session_key=key).update(expire_date=before)
        real=SessionStore.save
        def committed_then_lost(store,must_create=False):
            real(store,must_create=must_create)
            if not must_create and store.get(SESSION_KEY):
                raise OperationalError('synthetic lost acknowledgement after session commit')
        with patch.object(SessionStore,'save',committed_then_lost):result=self.login(client)
        self.assertEqual(result.status_code,500)
        self.assertNotIn('sessionid',result.cookies)
        after=Session.objects.using('auth').get(session_key=key).expire_date
        self.assertGreater(after,before)
        self.assertIsNotNone(session_student(key))
        self.assertEqual(client.get(reverse('accounts:password-change')).status_code,200)
        emit('known_session_ack_lost',status=result.status_code,session_valid=True,expiry_extended=True)

    def test_new_session_auth_payload_can_commit_before_ack_failure(self):
        client=Client(raise_request_exception=False)
        real=SessionStore.save
        def committed_then_lost(store,must_create=False):
            real(store,must_create=must_create)
            if not must_create and store.get(SESSION_KEY):
                raise OperationalError('synthetic ack lost')
        with patch.object(SessionStore,'save',committed_then_lost):result=self.login(client)
        self.assertEqual(result.status_code,500)
        valid=[s.session_key for s in Session.objects.using('auth').all()
               if s.get_decoded().get(SESSION_KEY) and session_student(s.session_key)]
        self.assertEqual(len(valid),1)
        self.assertNotIn('sessionid',result.cookies)
        self.assertNotIn('sessionid',client.cookies)
        emit('new_session_ack_lost',status=result.status_code,valid_auth_rows=1,cookie_delivered=False)

    def test_handler500_sees_sync_view_exception_with_nested_sqlstate(self):
        def fail(execute,sql,params,many,context):
            if 'accounts_auththrottle' in sql:
                try:raise psycopg.errors.LockNotAvailable('synthetic db error')
                except psycopg.Error as e:raise OperationalError('synthetic wrapped') from e
            return execute(sql,params,many,context)
        client=Client(raise_request_exception=False)
        with connections['auth'].execute_wrapper(fail):result=self.login(client)
        self.assertEqual(result.status_code,500)
        self.assertIsInstance(observed[-1],OperationalError)
        self.assertIn(('LockNotAvailable','55P03'),classes(observed[-1]))
        emit('sync_handler500',chain=classes(observed[-1]))

    def test_real_idle_timeout_sqlstate_class(self):
        try:
            with transaction.atomic(using='auth'):
                with connections['auth'].cursor() as c:c.execute("SET LOCAL idle_in_transaction_session_timeout='100ms'")
                time.sleep(.25)
                with connections['auth'].cursor() as c:c.execute('SELECT 1')
        except Exception as exc:
            chain=classes(exc)
        else:self.fail('idle timeout did not fire')
        self.assertIn(('IdleInTransactionSessionTimeout','25P03'),chain)
        emit('idle_timeout',chain=chain)
        connections['auth'].close()

    def test_error_log_record_contains_sensitive_path_and_database_exception(self):
        def fail(execute,sql,params,many,context):
            if 'accounts_auththrottle' in sql:raise OperationalError('SYNTHETIC_PRIVATE_SQL_DETAIL')
            return execute(sql,params,many,context)
        selector='11111111-1111-4111-8111-111111111111';secret='x'*43
        with self.assertLogs('django.request',level='ERROR') as captured:
            with connections['auth'].execute_wrapper(fail):
                Client(raise_request_exception=False).post(reverse('accounts:reset-confirm',args=[selector,secret]))
        self.assertTrue(any(secret in r.getMessage() for r in captured.records))
        self.assertTrue(any(r.exc_info and 'SYNTHETIC_PRIVATE_SQL_DETAIL' in str(r.exc_info[1]) for r in captured.records))
        emit('error_log_record',contains_reset_secret=True,contains_exception_detail=True)

    def test_verify_rollback_does_not_invalidate_existing_recovery_token(self):
        student=self.make_student('charlie',verified=False)
        self.client.post(reverse('accounts:resend'),{'email':'charlie@example.invalid'})
        link=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        from accounts.models import AccountToken
        token=AccountToken.objects.using('auth').get(student_id=student.pk,purpose='verify')
        def fail(execute,sql,params,many,context):
            if sql.lstrip().startswith('UPDATE') and 'email_verified_at' in sql:
                raise OperationalError('synthetic verify update failure')
            return execute(sql,params,many,context)
        with connections['auth'].execute_wrapper(fail):
            result=Client(raise_request_exception=False).post(link)
        student.refresh_from_db(using='auth');token.refresh_from_db(using='auth')
        self.assertEqual(result.status_code,500)
        self.assertIsNone(student.email_verified_at);self.assertIsNone(token.consumed_at)
        emit('verify_rollback',status=result.status_code,verified=False,token_consumed=False)

    def test_existing_web_error_template_is_unavailable_in_auth_profile(self):
        from django.template import TemplateDoesNotExist
        from student_web.views import server_error
        with self.assertRaises(TemplateDoesNotExist):server_error(RequestFactory().get('/accounts/login/'))
        emit('auth_profile_shared_error_template',template_missing=True)

    def test_handler500_preserves_exception_through_async_adapter(self):
        from asgiref.sync import async_to_sync
        from django.core.handlers.exception import convert_exception_to_response
        marker=OperationalError('synthetic async error')
        async def failing(request):raise marker
        wrapped=convert_exception_to_response(failing)
        response=async_to_sync(wrapped)(RequestFactory().get('/accounts/login/'))
        self.assertEqual(response.status_code,500)
        self.assertIs(observed[-1],marker)
        emit('async_handler500',original_exception_preserved=True)

    def test_real_reset_commit_then_ack_failure_preserves_atomic_pair(self):
        self.client.post(reverse('accounts:reset'),{'email':'alpha@example.invalid'})
        link=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        from accounts.models import AccountToken
        token=AccountToken.objects.using('auth').get(student_id=self.a.pk,purpose='reset')
        connection=connections['auth'];real=connection._commit;done=[]
        def committed_then_lost():
            real()
            if not done:
                done.append(True)
                raise OperationalError('synthetic commit acknowledgement lost')
        with patch.object(connection,'_commit',committed_then_lost):
            result=Client(raise_request_exception=False).post(link,{'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        token.refresh_from_db(using='auth');self.a.refresh_from_db(using='auth')
        from django.contrib.auth.hashers import check_password
        self.assertEqual(result.status_code,500)
        self.assertTrue(check_password(NEW_PASSWORD,self.a.password))
        self.assertFalse(check_password(PASSWORD,self.a.password))
        self.assertIsNotNone(token.consumed_at)
        emit('reset_commit_ack_lost',status=result.status_code,new_password_valid=True,token_consumed=True)

    def test_real_token_issue_commit_ack_failure_skips_on_commit_email(self):
        from accounts.models import AccountToken
        connection=connections['auth'];real=connection._commit;done=[]
        def committed_then_lost():
            real()
            if not done:
                done.append(True)
                raise OperationalError('synthetic issue commit acknowledgement lost')
        with patch.object(connection,'_commit',committed_then_lost):
            result=Client(raise_request_exception=False).post(reverse('accounts:reset'),{'email':'alpha@example.invalid'})
        self.assertEqual(result.status_code,500)
        self.assertEqual(AccountToken.objects.using('auth').filter(student_id=self.a.pk,purpose='reset').count(),1)
        self.assertEqual(len(mail.outbox),0)
        emit('email_issue_ack_lost',status=result.status_code,token_committed=True,email_sent=False)

    def test_reset_can_legitimately_reuse_same_plaintext_secret(self):
        self.client.post(reverse('accounts:reset'),{'email':'alpha@example.invalid'})
        link=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        from accounts.models import AccountToken
        token=AccountToken.objects.using('auth').get(student_id=self.a.pk,purpose='reset')
        response=self.client.post(link,{'new_password1':PASSWORD,'new_password2':PASSWORD})
        token.refresh_from_db(using='auth');self.a.refresh_from_db(using='auth')
        from django.contrib.auth.hashers import check_password
        self.assertEqual(response.status_code,200)
        self.assertIsNotNone(token.consumed_at)
        self.assertTrue(check_password(PASSWORD,self.a.password))
        emit('same_password_reset',status=response.status_code,old_and_new_secret_equal=True,token_consumed=True)
```

## `b1_commit_timeout_probe.py` — native psycopg experiment

Use an isolated empty synthetic scratch database and offline test login that can create temporary objects. Supply PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE privately, then `python /private/probe/directory/b1_commit_timeout_probe.py`. Objects are session-temporary; no production schema is changed. The experiment installs no application timeout helper and proves only the observed PostgreSQL/driver behavior.

```python
"""Standalone synthetic PG17 COMMIT timeout probe; no B1 implementation."""
import os,time,psycopg
kwargs=dict(host=os.environ['PGHOST'],port=os.environ['PGPORT'],user=os.environ['PGUSER'],
            password=os.environ['PGPASSWORD'],dbname=os.environ['PGDATABASE'],
            options='-c statement_timeout=100ms')
with psycopg.connect(**kwargs,autocommit=True) as c:
    print('Server:',c.execute('SHOW server_version').fetchone()[0])
    print('Configured statement_timeout:',c.execute('SHOW statement_timeout').fetchone()[0])
    start=time.monotonic()
    try:c.execute('SELECT pg_sleep(0.35)')
    except psycopg.Error as exc:
        assert exc.sqlstate=='57014'
        print('Control SELECT:',exc.sqlstate,'elapsed_ms',round((time.monotonic()-start)*1000))
    else:raise AssertionError('Control did not time out')
    c.execute('CREATE TEMP TABLE b1_commit_delay(id int)')
    c.execute('''CREATE FUNCTION pg_temp.b1_delay() RETURNS trigger LANGUAGE plpgsql AS $$
                 BEGIN PERFORM pg_sleep(0.35); RETURN NEW; END $$''')
    c.execute('CREATE CONSTRAINT TRIGGER delayed AFTER INSERT ON b1_commit_delay '
              'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION pg_temp.b1_delay()')
    c.autocommit=False
    c.execute('INSERT INTO b1_commit_delay VALUES(1)')
    start=time.monotonic();c.commit();elapsed=time.monotonic()-start
    count=c.execute('SELECT count(*) FROM b1_commit_delay').fetchone()[0]
    assert elapsed>.25 and count==1
    print('Native psycopg COMMIT succeeded; elapsed_ms:',round(elapsed*1000),'rows:',count)
```
