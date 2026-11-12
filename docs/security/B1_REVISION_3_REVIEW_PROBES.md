# Revision 3 independent observation probes

Seven tests supporting [the review](B1_REVISION_3_INDEPENDENT_REVIEW.md), executed on Django 5.2.19, psycopg 3.3.8 and PostgreSQL 17.11 using the existing post-PR29 code and AuthenticationTestRunner. The code observes current behavior; it is **not B1 implementation** and passing does not establish compliance with the proposed plan.

Copy the Python block to a private temporary directory as `b1r3_review_probes.py`. Supply the repository's generated ephemeral PostgreSQL test credentials and separate auth/runtime LOGINs, UCC_CONTEXT_SIGNING_KEY and DJANGO_SECRET_KEY. Use separate disposable scratch/test databases, never a real-data or persistent student database. From the approved PR29 source checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/probe/directory PGTESTDATABASE=test_b1r3_review python server/manage.py test b1r3_review_probes --settings=config.settings.auth_test -v 2
```

Handler observers deliberately return fixed 400/500 statuses; no proposed B1 classifier is installed. Transaction faults and a synthetic wrapped driver error demonstrate the surrounding framework's actual state and routing; the Student/session database operations use real PostgreSQL. The filter marker tests Python propagation, not a redaction implementation. Emitted evidence contains classes/SQLSTATEs/booleans only. The CSRF secret and request metadata sentinels are invented; no cookie values or records are printed.

```python
"""Observation-only Revision 3 review probes; no B1 implementation."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json,logging,sys,types
import psycopg
from django.contrib.sessions.models import Session
from django.db import connections,transaction,OperationalError,ProgrammingError
from django.http import HttpResponse
from django.test import Client,RequestFactory,override_settings
from django.urls import include,path,reverse
from django.utils.log import log_response
from accounts.principals import session_student
from auth_tests.base import AuthenticationCase,PASSWORD,NEW_PASSWORD

seen=[]
mod=types.ModuleType('b1r3_review_urls')
mod.urlpatterns=[path('',include('config.auth_urls'))]
def h400(request,exception):
    seen.append(exception)
    return HttpResponse('synthetic 400',status=400)
def h500(request):return HttpResponse('synthetic 500',status=500)
mod.handler400=h400;mod.handler500=h500;sys.modules[mod.__name__]=mod

def emit(name,**values):print('B1R3_EVIDENCE='+json.dumps(dict(name=name,**values),sort_keys=True))
def chain(exc):
    out=[];ids=set()
    while exc is not None and id(exc) not in ids:
        ids.add(id(exc));out.append((type(exc).__name__,getattr(exc,'sqlstate',None)))
        exc=exc.__cause__ if exc.__cause__ is not None else exc.__context__
    return out

@override_settings(ROOT_URLCONF='b1r3_review_urls')
class Revision3ReviewProbes(AuthenticationCase):
    def setUp(self):super().setUp();seen.clear()

    def test_different_account_lock_timeout_preserves_original_account(self):
        client=Client(raise_request_exception=False)
        self.assertEqual(self.login(client).status_code,302)
        original=client.cookies['sessionid'].value
        def worker():
            try:
                with connections['auth'].cursor() as c:c.execute("SET lock_timeout='100ms'")
                return self.login(client,'bravo')
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as ex:
            with transaction.atomic(using='default'):
                from accounts.models import Student
                Student.objects.using('default').select_for_update().get(pk=self.b.pk)
                response=ex.submit(worker).result(timeout=15)
        self.assertEqual(response.status_code,500)
        self.assertEqual(session_student(original).pk,self.a.pk)
        self.assertNotIn('sessionid',response.cookies)
        self.assertEqual(client.get(reverse('accounts:password-change')).status_code,200)
        emit('DA_before_flush',status=response.status_code,original_A_valid=True)

    def test_different_account_rollback_restores_original_account(self):
        client=Client(raise_request_exception=False);self.login(client)
        original=client.cookies['sessionid'].value
        connection=connections['auth']
        with patch.object(connection,'_commit',side_effect=OperationalError('synthetic before COMMIT')):
            response=self.login(client,'bravo')
        self.assertEqual(response.status_code,500)
        self.assertEqual(session_student(original).pk,self.a.pk)
        self.assertEqual(Session.objects.using('auth').count(),1)
        self.assertEqual(client.get(reverse('accounts:password-change')).status_code,200)
        emit('DA_flush_rolled_back',status=response.status_code,original_A_valid=True,valid_B_rows=0)

    def test_password_change_rollback_after_flush_sends_cookie_deletion(self):
        client=Client(raise_request_exception=False);self.login(client)
        original=client.cookies['sessionid'].value
        with patch.object(connections['auth'],'_commit',side_effect=OperationalError('synthetic before COMMIT')):
            response=client.post(reverse('accounts:password-change'),{'old_password':PASSWORD,
                  'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        self.assertEqual(response.status_code,500)
        self.assertIn('sessionid',response.cookies)
        self.assertEqual(response.cookies['sessionid'].value,'')
        self.assertEqual(response.cookies['sessionid']['max-age'],0)
        self.assertEqual(session_student(original).pk,self.a.pk)
        emit('change_after_flush_rollback',status=response.status_code,deletion_Set_Cookie=True,old_server_session_valid=True)

    def test_session_save_driver_defect_reaches_handler400(self):
        client=Client(raise_request_exception=False);self.login(client)
        def fault(execute,sql,params,many,context):
            if sql.lstrip().startswith('UPDATE') and 'django_session' in sql:
                try:raise psycopg.errors.UndefinedColumn('synthetic column defect')
                except psycopg.Error as e:raise ProgrammingError('synthetic wrapper') from e
            return execute(sql,params,many,context)
        with connections['auth'].execute_wrapper(fault):response=self.login(client)
        self.assertEqual(response.status_code,400)
        self.assertIn(('UndefinedColumn','42703'),chain(seen[-1]))
        emit('session_save_defect',status=response.status_code,chain=chain(seen[-1]))

    def test_django_log_record_retains_live_request_metadata(self):
        request=RequestFactory().get('/accounts/reset/11111111-1111-4111-8111-111111111111/'+'x'*43+'/?q=SYNTHETIC_QUERY',
                  HTTP_COOKIE='sessionid=SYNTHETIC_SESSION',HTTP_AUTHORIZATION='SYNTHETIC_AUTH',REMOTE_ADDR='192.0.2.11')
        records=[]
        class Capture(logging.Handler):
            def emit(self,record):records.append(record)
        logger=logging.getLogger('b1r3.private_log_probe');old=(logger.handlers,logger.propagate,logger.level)
        try:
            logger.handlers=[Capture()];logger.propagate=False;logger.setLevel(logging.ERROR)
            log_response('Failure: %s',request.path,response=HttpResponse(status=500),request=request,logger=logger)
        finally:logger.handlers,logger.propagate,logger.level=old
        record=records[0]
        self.assertIs(record.request,request)
        self.assertIn('SYNTHETIC_SESSION',record.request.META['HTTP_COOKIE'])
        self.assertEqual(record.request.META['HTTP_AUTHORIZATION'],'SYNTHETIC_AUTH')
        self.assertIn('SYNTHETIC_QUERY',record.request.META['QUERY_STRING'])
        emit('log_request_metadata',live_request_reference=True,cookie_and_authorization_reachable=True,query_and_IP_reachable=True)

    def test_ancestor_logger_filters_do_not_filter_propagated_child(self):
        parent=logging.getLogger('b1r3.parent_probe');child=logging.getLogger('b1r3.parent_probe.child')
        oldparent=(parent.handlers,parent.filters,parent.propagate,parent.level)
        oldchild=(child.handlers,child.filters,child.propagate,child.level)
        records=[]
        class Capture(logging.Handler):
            def emit(self,record):records.append(record)
        class Marker(logging.Filter):
            def filter(self,record):record.marker_applied=True;return True
        try:
            parent.handlers=[Capture()];parent.filters=[Marker()];parent.propagate=False;parent.setLevel(logging.ERROR)
            child.handlers=[];child.filters=[];child.propagate=True;child.setLevel(logging.ERROR)
            child.error('synthetic child');parent.error('synthetic direct')
            self.assertFalse(getattr(records[0],'marker_applied',False))
            self.assertTrue(records[1].marker_applied)
        finally:
            parent.handlers,parent.filters,parent.propagate,parent.level=oldparent
            child.handlers,child.filters,child.propagate,child.level=oldchild
        emit('logging_filter_propagation',child_bypasses_ancestor_filter=True,direct_parent_is_filtered=True)

    def test_csrf_failure_uses_security_logger_outside_proposed_filter_list(self):
        secret='y'*43
        url=reverse('accounts:reset-confirm',args=['11111111-1111-4111-8111-111111111111',secret])
        with self.assertLogs('django.security.csrf',level='WARNING') as capture:
            response=Client(enforce_csrf_checks=True).post(url)
        self.assertEqual(response.status_code,403)
        self.assertTrue(any(secret in record.getMessage() for record in capture.records))
        self.assertTrue(any(record.name=='django.security.csrf' for record in capture.records))
        emit('csrf_log_namespace',status=response.status_code,reset_secret_in_security_logger=True,
             covered_by_request_or_server_logger_filter=False)
```
