"""B1c pure classification, rendering, adapters and fixed-byte sink contracts."""
from io import StringIO
from contextlib import nullcontext
import logging
from types import SimpleNamespace
from unittest.mock import patch
import psycopg
from psycopg.pq import DiagnosticField
from django.core.exceptions import BadRequest, ImproperlyConfigured
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.db import utils
from django.test import SimpleTestCase, RequestFactory, override_settings
from accounts import failure_classification as fc, failure_response as fr, failure_handlers as fh
from accounts.logging import FailureCategory as C, FailureEvent, EventKind, SanitizingHandler
from accounts.middleware import AuthFailureMiddleware


def chain(*nodes):
    for outer, inner in zip(nodes, nodes[1:]):
        outer.__cause__ = inner
    return nodes[0]


def unknown(code):
    return psycopg.errors._class_for_state(code)(info={DiagnosticField.SQLSTATE: code.encode()})


class ClassificationTests(SimpleTestCase):
    def test_sqlstate_sets_and_unknown_operational_families(self):
        for code in ('08000','08ZZZ','53300','53ZZZ','57P01','57P02','57P03',
                     '57014','55P03','40001','40P01','25P03'):
            self.assertEqual(fc.classify_database_failure(unknown(code)).category,C.OUTAGE)
        for code in ('42501','28000','28ZZZ','3D000','57P04'):
            self.assertEqual(fc.classify_database_failure(unknown(code)).category,C.CONFIGURATION)
        for code in ('42703','42P01','23505','22003','27ZZZ','2FZZZ','38ZZZ',
                     '39ZZZ','3BZZZ','40ZZZ','54ZZZ','55ZZZ','57ZZZ','58ZZZ','F0ZZZ','HVZZZ','XX999','ZZ999'):
            with self.subTest(code=code):
                result=fc.classify_database_failure(unknown(code))
                self.assertEqual((result.category,result.sqlstate,result.origin),(C.DEFECT,code,'database'))

    def test_whole_walk_precedence_and_instance_visible_code(self):
        exc=chain(utils.OperationalError(),psycopg.OperationalError(),unknown('42703'))
        self.assertEqual(fc.classify_database_failure(exc).category,C.DEFECT)
        exc=chain(unknown('55P03'),unknown('42703'))
        self.assertEqual(fc.classify_database_failure(exc).category,C.OUTAGE)
        exc=psycopg.errors.UndefinedColumn();exc.sqlstate='55ZZZ'
        self.assertEqual(fc.classify_database_failure(exc).sqlstate,'55ZZZ')

    def test_no_state_fallback_and_django_only_errors(self):
        for cls in (psycopg.OperationalError,psycopg.InterfaceError):
            self.assertEqual(fc.classify_database_failure(cls()).category,C.CONNECTION_UNAVAILABLE)
        self.assertEqual(fc.classify_database_failure(psycopg.ProgrammingError()).category,C.DEFECT)
        for cls in (utils.InterfaceError,utils.OperationalError,utils.ProgrammingError,UpdateError):
            self.assertEqual(fc.classify_database_failure(cls()).category,C.DATABASE_UNPROVEN)

    def test_outer_gate_opaque_groups_and_inner_stops(self):
        for exc in (chain(RuntimeError(),unknown('55P03')),BadRequest(),
                    ExceptionGroup('synthetic',[unknown('55P03')])):
            self.assertEqual(fc.classify_database_failure(exc).category,C.NOT_DATABASE)
        self.assertEqual(fc.classify_database_failure(chain(UpdateError(),KeyError(),unknown('55P03'))).category,C.DATABASE_UNPROVEN)

    def test_cycle_depth_suppression_and_cause_precedence(self):
        a,b=utils.DatabaseError(),UpdateError();a.__context__=b;b.__context__=a
        self.assertTrue(fc.classify_database_failure(a).truncated)
        exc=chain(*([utils.DatabaseError() for _ in range(16)]+[unknown('55P03')]))
        self.assertEqual(fc.classify_database_failure(exc).category,C.DATABASE_UNPROVEN)
        self.assertTrue(fc.classify_database_failure(exc).truncated)
        exc=chain(*([utils.DatabaseError() for _ in range(15)]+[unknown('55P03'),UpdateError()]))
        self.assertEqual(fc.classify_database_failure(exc).category,C.OUTAGE)
        a=UpdateError();a.__context__=unknown('55P03');a.__suppress_context__=True
        self.assertEqual(fc.classify_database_failure(a).category,C.DATABASE_UNPROVEN)
        a.__cause__=unknown('42703')
        self.assertEqual(fc.classify_database_failure(a).category,C.DEFECT)

    def test_malformed_and_hostile_attributes_no_text_access(self):
        class Hostile(psycopg.DatabaseError):
            def __init__(self):pass
            @property
            def sqlstate(self):raise ValueError('SECRET')
            def __str__(self):raise AssertionError('must not read text')
            def __repr__(self):raise AssertionError('must not read repr')
        self.assertEqual(fc.classify_database_failure(Hostile()).category,C.DEFECT)
        for value in (None,True,55,'55p03','55P03\n','５５P03','SECRET'):
            exc=psycopg.ProgrammingError();exc.sqlstate=value
            self.assertEqual(fc.classify_database_failure(exc).category,C.DEFECT)
        exc=psycopg.ProgrammingError();exc.sqlstate='55P03'
        self.assertEqual(fc.classify_database_failure(exc).category,C.OUTAGE)

    def test_walker_failure_is_not_fabricated_into_a_category(self):
        with patch.object(fc,'walk',side_effect=RuntimeError('SECRET')):
            with self.assertRaises(RuntimeError):fc.classify_database_failure(UpdateError())


class ResponseTests(SimpleTestCase):
    def test_retry_after_strict_validation(self):
        for value in (1,5,300,'1','005','300'):
            self.assertEqual(fr.validate_retry_after(value),int(value))
        for value in (True,False,1.0,0,-1,301,'0','301',' 5','5 ','+5','-5','5s','５','١','0005','',None):
            with self.subTest(value=value),self.assertRaises(ImproperlyConfigured):fr.validate_retry_after(value)
        class Int(int):pass
        class Str(str):pass
        for value in (Int(5),Str('5')):
            with self.assertRaises(ImproperlyConfigured):fr.validate_retry_after(value)

    def assert_headers(self,response,category):
        self.assertEqual(response.status_code,503 if category in (C.OUTAGE,C.CONFIGURATION,C.CONNECTION_UNAVAILABLE) else 500)
        self.assertEqual(response.get('Cache-Control'),'no-store')
        self.assertEqual(response.get('Content-Type'),'text/plain; charset=utf-8')
        self.assertEqual(response.get('Retry-After'),'5' if category is C.OUTAGE else None)

    def test_renderer_and_fallback_preserve_every_header_without_templates(self):
        with (patch('django.template.loader.get_template',side_effect=AssertionError('template used')),
              patch('django.urls.reverse',side_effect=AssertionError('reverse used'))):
            for category in C:
                self.assert_headers(fr.failure_response(category),category)
                with patch.object(fr,'_build',side_effect=RuntimeError('SECRET')):
                    result=fr.failure_response(category)
                self.assert_headers(result,category);self.assertNotIn(b'SECRET',result.content)

    def test_recursive_failure_and_process_controls_propagate(self):
        with patch.object(fr,'_build',side_effect=RuntimeError()),patch.object(fr,'_plain_response',side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):fr.failure_response(C.OUTAGE)
        for cls in (KeyboardInterrupt,SystemExit,GeneratorExit):
            with patch.object(fr,'_build',side_effect=cls):
                with self.assertRaises(cls):fr.failure_response(C.OUTAGE)

    def test_both_roots_status_delegation_and_no_active_exception(self):
        request=RequestFactory().get('/accounts/login/')
        for root in ('auth','web'):
            bad=getattr(fh,root+'_bad_request');server=getattr(fh,root+'_server_error')
            self.assert_headers(server(request),C.DEFECT)
            for code,cat in [('55P03',C.OUTAGE),('42703',C.DEFECT),('42501',C.CONFIGURATION)]:
                self.assert_headers(bad(request,chain(SessionInterrupted(),UpdateError(),unknown(code))),cat)
                try:raise unknown(code)
                except psycopg.Error:self.assert_headers(server(request),cat)
            with patch('student_web.views.bad_request',return_value=__import__('django.http',fromlist=['HttpResponse']).HttpResponse(status=400)) as original:
                self.assertEqual(bad(request,chain(SessionInterrupted(),UpdateError(),utils.DatabaseError())).status_code,400)
                self.assertEqual(bad(request,BadRequest()).status_code,400)
                if root=='web':self.assertEqual(original.call_count,2)
            with patch.object(fh,'classify_database_failure',side_effect=RuntimeError('SECRET')):
                self.assert_headers(bad(request,BadRequest()),C.DEFECT)
            try:raise RuntimeError('SECRET')
            except RuntimeError:
                with patch.object(fh,'classify_database_failure',side_effect=RuntimeError('SECRET')):
                    self.assert_headers(server(request),C.DEFECT)

    def test_typed_event_scope_categories_and_unknown_masking(self):
        request=RequestFactory().get('/accounts/reset/SECRET/?SECRET',HTTP_COOKIE='SECRET',HTTP_AUTHORIZATION='SECRET')
        request.resolver_match=SimpleNamespace(view_name='accounts:reset')
        logger=logging.getLogger();stream=StringIO();middleware=AuthFailureMiddleware(lambda r:None)
        with patch.object(logger.handlers[0],'stream',stream):
            for code,category in [('55P03',C.OUTAGE),('42501',C.CONFIGURATION),('53ZZZ',C.OUTAGE)]:
                response=middleware.process_exception(request,unknown(code));self.assert_headers(response,category)
            self.assertIsNone(middleware.process_exception(request,unknown('55ZZZ')))
            with patch.object(fc,'classify_database_failure',side_effect=RuntimeError('SECRET')):
                self.assert_headers(middleware.process_exception(request,UpdateError()),C.DEFECT)
        lines=[x for x in stream.getvalue().splitlines() if 'logger=accounts.failures ' in x]
        self.assertEqual(len(lines),4);self.assertIn('category=OUTAGE',lines[0]);self.assertIn('category=CONFIGURATION',lines[1])
        self.assertIn('sqlstate=XXXXX',lines[2]);self.assertIn('category=DEFECT',lines[3])
        self.assertNotIn('SECRET',stream.getvalue())

    def test_exact_typed_category_mapping(self):
        for category in C:
            stream=StringIO();handler=SanitizingHandler(stream=stream)
            record=logging.LogRecord('accounts.failures',40,'',0,'SECRET',None,None)
            record.ucc_event=FailureEvent(EventKind.FAILURE,category,'55ZZZ')
            handler.emit(record)
            self.assertIn('category='+category.value,stream.getvalue())
            self.assertIn('sqlstate=XXXXX',stream.getvalue());self.assertNotIn('SECRET',stream.getvalue())

    def test_renderer_never_attempts_template_or_reverse(self):
        with patch('django.template.loader.get_template') as template,patch('django.urls.reverse') as reverse:
            for category in C:fr.failure_response(category)
        template.assert_not_called();reverse.assert_not_called()

    def test_debug_flags_documented_behavior(self):
        from django.core.handlers.exception import response_for_exception
        request=RequestFactory().get('/accounts/login/')
        with override_settings(DEBUG=True),patch('django.views.debug.technical_500_response',return_value=__import__('django.http',fromlist=['HttpResponse']).HttpResponse(status=400)) as debug:
            response_for_exception(request,BadRequest())
            self.assertEqual(debug.call_count,1)
            self.assert_headers(AuthFailureMiddleware(lambda r:None).process_exception(request,unknown('55P03')),C.OUTAGE)
        with override_settings(DEBUG_PROPAGATE_EXCEPTIONS=True):
            try:raise RuntimeError('synthetic')
            except RuntimeError as exc:
                with self.assertRaises(RuntimeError):response_for_exception(request,exc)

    def test_renderer_propagates_process_control(self):
        for cls in (KeyboardInterrupt,SystemExit,GeneratorExit):
            with patch.object(fr,'_build',side_effect=cls):
                with self.assertRaises(cls):fr.failure_response(C.OUTAGE)

    def test_exact_middleware_placement_and_hostile_traversal_fail500(self):
        from django.conf import settings
        names=settings.MIDDLEWARE
        self.assertEqual(names.index('accounts.middleware.AuthFailureMiddleware'),
                         names.index('django.contrib.auth.middleware.AuthenticationMiddleware')+1)
        class Hostile(UpdateError):
            def __getattribute__(self,name):
                if name=='__cause__':raise ValueError('SECRET')
                return super().__getattribute__(name)
        request=RequestFactory().get('/accounts/login/')
        self.assert_headers(AuthFailureMiddleware(lambda r:None).process_exception(request,Hostile()),C.DEFECT)
        self.assert_headers(fh.auth_bad_request(request,Hostile()),C.DEFECT)
        self.assert_headers(fh.web_bad_request(request,Hostile()),C.DEFECT)

    def test_runtime_invalid_retry_after_retains_safe_outage_response(self):
        request=RequestFactory().get('/accounts/login/')
        for value in (True,0,301,'5s','SECRET'):
            with override_settings(UCC_FAILURE_RETRY_AFTER=value),patch('django.template.loader.get_template') as templates:
                for broken_builder in (False,True):
                    with patch.object(fr,'_build',side_effect=RuntimeError('SECRET')) if broken_builder else nullcontext():
                        response=fr.failure_response(C.OUTAGE)
                    self.assertEqual(response.status_code,503)
                    self.assertEqual(response.get('Cache-Control'),'no-store')
                    self.assertEqual(response.get('Content-Type'),'text/plain; charset=utf-8')
                    self.assertNotIn('Retry-After',response)
                    self.assertNotIn(b'SECRET',response.content)
                for handler in (fh.auth_bad_request,fh.web_bad_request):
                    response=handler(request,unknown('55P03'))
                    self.assertEqual(response.status_code,503);self.assertNotIn('Retry-After',response)
                templates.assert_not_called()
        # Normal-path process-control semantics apply to the optional header too.
        for control in (KeyboardInterrupt,SystemExit,GeneratorExit):
            with patch.object(fr,'validate_retry_after',side_effect=control):
                with self.assertRaises(control):fr.failure_response(C.OUTAGE)
