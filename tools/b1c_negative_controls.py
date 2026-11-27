"""Production-path B1c mutants: baseline, exercised assertion failure, no errors/skips."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from django.test import TransactionTestCase
from accounts import exception_chain, failure_classification as fc, failure_response as fr
from accounts import failure_handlers as fh, logging as safe, middleware
from auth_tests import test_b1c_classification as pure, test_b1c_database as db


def run(case, method):
    result=unittest.TestResult();case(method)(result)
    return {'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped)}


class B1cNegativeControls(TransactionTestCase):
    databases={'default','runtime','auth'}

    def control(self,name,case,method,mutation):
        baseline=run(case,method);hits=[]
        with mutation(hits):changed=run(case,method)
        detected=(baseline=={'run':1,'failures':0,'errors':0,'skips':0} and bool(hits)
                  and changed['run']==1 and changed['failures']>0 and not changed['errors'] and not changed['skips'])
        print(('B1C_MUTATION_DETECTED=' if detected else 'B1C_MUTATION_UNDETECTED=')+name)
        self.assertTrue(detected,str((name,baseline,changed,bool(hits))))

    def test_classification_mutations(self):
        @contextmanager
        def class_only(hits):
            def read(node):hits.append(1);return getattr(type(node),'sqlstate',None)
            with patch.object(fc,'driver_sqlstate',read):yield
        self.control('instance_read_removed_routing',db.FailureRouteTests,'test_unknown_operational_defects_route_500_and_sink_masks_codes',class_only)

        @contextmanager
        def reverse_passes(hits):
            real=fc.driver_sqlstate
            def read(node):
                hits.append(1)
                return None if type(node) is __import__('psycopg').OperationalError else real(node)
            # Remove the valid inner state to mimic first-driver fallback taking priority.
            real_classify=fc.classify_database_failure
            def classify(exc):
                chain=fc.walk(exc)
                if any(type(n) is __import__('psycopg').OperationalError and n.sqlstate is None for n in chain.nodes):
                    hits.append(1);return fc.Classification(safe.FailureCategory.CONNECTION_UNAVAILABLE,'database',None,False)
                return real_classify(exc)
            with patch.object(fc,'classify_database_failure',classify):yield
        self.control('no_state_pass_before_sqlstate',pure.ClassificationTests,'test_whole_walk_precedence_and_instance_visible_code',reverse_passes)

        for name,attr,value,method in (
            ('missing_outage_codes','_OUTAGES',frozenset(),'test_sqlstate_sets_and_unknown_operational_families'),
            ('missing_configuration_codes','_CONFIGURATIONS',frozenset(),'test_sqlstate_sets_and_unknown_operational_families'),
        ):
            @contextmanager
            def mutation(hits,attr=attr,value=value):
                real=fc.driver_sqlstate
                def read(node):hits.append(1);return real(node)
                with patch.object(fc,attr,value),patch.object(fc,'driver_sqlstate',read):yield
            self.control(name,pure.ClassificationTests,method,mutation)

        @contextmanager
        def shallow_bound(hits):
            real=fc.walk
            def walk(exc):hits.append(1);return real(exc)
            with patch.object(exception_chain,'LIMIT',2),patch.object(fc,'walk',walk):yield
        self.control('wrong_walk_depth',pure.ClassificationTests,'test_cycle_depth_suppression_and_cause_precedence',shallow_bound)

        @contextmanager
        def unwrap_opaque(hits):
            real=fc.walk
            def walk(exc):
                hits.append(1)
                if not isinstance(exc,exception_chain.WRAPPERS) and exc.__cause__ is not None:return real(exc.__cause__)
                return real(exc)
            with patch.object(fc,'walk',walk):yield
        self.control('opaque_outer_bypassed',pure.ClassificationTests,'test_outer_gate_opaque_groups_and_inner_stops',unwrap_opaque)

    def test_renderer_and_configuration_mutations(self):
        for name,header in [('missing_no_store','Cache-Control'),('missing_charset','Content-Type')]:
            @contextmanager
            def strip(hits,header=header):
                real=fr._plain_response
                def response(*args):
                    hits.append(1);r=real(*args);del r[header];return r
                with patch.object(fr,'_plain_response',response):yield
            self.control(name,pure.ResponseTests,'test_renderer_and_fallback_preserve_every_header_without_templates',strip)

        @contextmanager
        def all_retry(hits):
            real=fr._plain_response
            def response(*args):hits.append(1);r=real(*args);r['Retry-After']='5';return r
            with patch.object(fr,'_plain_response',response):yield
        self.control('retry_after_on_defects',pure.ResponseTests,'test_renderer_and_fallback_preserve_every_header_without_templates',all_retry)

        @contextmanager
        def template(hits):
            real=fr._build
            def build(*args):
                from django.template import loader
                hits.append(1)
                try:loader.get_template('synthetic')
                except Exception:pass
                return real(*args)
            # The target asserts the loader was never called, in addition to positive output.
            with patch.object(fr,'_build',build):yield
        self.control('renderer_uses_template',pure.ResponseTests,'test_renderer_never_attempts_template_or_reverse',template)

        @contextmanager
        def coerce(hits):
            def validate(value):
                hits.append(1)
                try:return int(value)
                except (ValueError,TypeError):return 5
            with patch.object(fr,'validate_retry_after',validate):yield
        self.control('retry_validation_coercion',pure.ResponseTests,'test_retry_after_strict_validation',coerce)
        self.control('runtime_invalid_retry_header_coerced',pure.ResponseTests,
                     'test_runtime_invalid_retry_after_retains_safe_outage_response',coerce)

        @contextmanager
        def swallow(hits):
            real=fr.failure_response
            def response(*args):
                hits.append(1)
                try:return real(*args)
                except BaseException:return __import__('django.http',fromlist=['HttpResponse']).HttpResponse(status=500)
            with patch.object(fr,'failure_response',response):yield
        self.control('renderer_swallows_process_control',pure.ResponseTests,'test_renderer_propagates_process_control',swallow)

    def test_adapter_and_sink_mutations(self):
        @contextmanager
        def defects400(hits):
            real=fh._bad_request
            def bad(request,exc,original):
                hits.append(1)
                if fc.classify_database_failure(exc).category is safe.FailureCategory.DEFECT:
                    return __import__('django.http',fromlist=['HttpResponse']).HttpResponse(status=400)
                return real(request,exc,original)
            with patch.object(fh,'_bad_request',bad):yield
        self.control('handler400_defect_kept400',pure.ResponseTests,'test_both_roots_status_delegation_and_no_active_exception',defects400)

        @contextmanager
        def all503(hits):
            real=fh.classify_database_failure
            def classify(exc):
                hits.append(1);r=real(exc)
                return fc.Classification(safe.FailureCategory.OUTAGE,r.origin,r.sqlstate,r.truncated)
            with patch.object(fh,'classify_database_failure',classify):yield
        self.control('unproven_as_outage',pure.ResponseTests,'test_both_roots_status_delegation_and_no_active_exception',all503)

        for name,times in [('typed_event_omitted',0),('typed_event_duplicate',2)]:
            @contextmanager
            def repeat(hits,times=times):
                import logging
                logger=logging.getLogger('accounts.failures');real=logger.error
                def error(*args,**kwargs):
                    hits.append(1)
                    for _ in range(times):real(*args,**kwargs)
                with patch.object(logger,'error',error):yield
            self.control(name,pure.ResponseTests,'test_typed_event_scope_categories_and_unknown_masking',repeat)

        @contextmanager
        def wrong_category(hits):
            real=safe.safe_record
            def record(raw):hits.append(1);r=real(raw);r.fields['category']='UNCLASSIFIED';return r
            with patch.object(safe,'safe_record',record):yield
        self.control('typed_category_not_serialized',pure.ResponseTests,'test_exact_typed_category_mapping',wrong_category)

        @contextmanager
        def leak_code(hits):
            real=safe.safe_record
            def record(raw):
                hits.append(1);r=real(raw)
                if getattr(raw,'ucc_event',None):r.fields['sqlstate']=raw.ucc_event.sqlstate or '-'
                return r
            with patch.object(safe,'safe_record',record):yield
        self.control('unknown_sqlstate_log_leak',pure.ResponseTests,'test_exact_typed_category_mapping',leak_code)

    def test_runner_rejects_noop_unexercised_errors_and_skips(self):
        from contextlib import redirect_stdout
        from io import StringIO
        good={'run':1,'failures':0,'errors':0,'skips':0}
        failures={'run':1,'failures':1,'errors':0,'skips':0}
        @contextmanager
        def exercised(hits):hits.append(1);yield
        @contextmanager
        def unexercised(hits):yield
        scenarios=[(good,good,exercised),(good,failures,unexercised),
                   (good,dict(failures,errors=1),exercised),
                   (good,dict(failures,skips=1),exercised),
                   (dict(good,run=0),failures,exercised),
                   (dict(good,failures=1),failures,exercised)]
        for baseline,changed,mutation in scenarios:
            with patch(__name__+'.run',side_effect=[baseline,changed]),redirect_stdout(StringIO()):
                with self.assertRaises(AssertionError):self.control('expected_guard_rejection',object,'unused',mutation)
