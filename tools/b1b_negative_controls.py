"""Isolated production mutations; baselines/exercise/assertions/errors checked by B1a runner."""
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from django.test import TransactionTestCase
from unittest.mock import patch
from accounts import logging as safe, checks, log_privacy
from auth_tests import test_b1b_logging as sink_tests, test_b1b_profiles as profiles
from b1a_negative_controls import run_in_process, run_in_checkout, Counter


class PrivacyNegativeControls(TransactionTestCase):
    databases={'default','runtime','auth'}

    def judge(self,name,baseline,mutated,exercised):
        okay=(baseline['run']==1 and not baseline['failures'] and not baseline['errors']
              and baseline.get('inside_checkout',True) and exercised
              and mutated['run']==1 and mutated['failures']>0 and not mutated['errors']
              and mutated.get('inside_checkout',True))
        print(('B1B_MUTATION_DETECTED=' if okay else 'B1B_MUTATION_UNDETECTED=')+name)
        self.assertTrue(okay,name+' failed baseline/exercise/assertion/error guard')

    def memory(self,name,case,method,mutation):
        baseline=run_in_process(case,method);counter=Counter()
        with mutation(counter):mutated=run_in_process(case,method)
        self.judge(name,baseline,mutated,counter.hits>0)

    def checkout(self,name,replacements,method):
        target='auth_tests.test_b1b_profiles.ProfileTests.'+method
        if method.startswith(('test_main_thread','test_hook_')):target='auth_tests.test_b1b_profiles.HookTests.'+method
        baseline=run_in_checkout([], [target]);mutated=run_in_checkout(replacements,[target])
        self.judge(name,baseline,mutated,mutated.get('inside_checkout',False))

    def test_sink_event_email_and_reentry_mutations(self):
        @contextmanager
        def copy_message(counter):
            real=safe.safe_record
            def mutant(record):
                counter.hits+=1;result=real(record);result.fields['logger']=record.msg;return result
            with patch.object(safe,'safe_record',mutant):yield
        @contextmanager
        def copy_request(counter):
            real=safe.safe_record
            def mutant(record):
                counter.hits+=1;result=real(record);result.request=record.request;return result
            with patch.object(safe,'safe_record',mutant):yield
        @contextmanager
        def loose_event(counter):
            real=safe.safe_record
            def mutant(record):
                counter.hits+=1;result=real(record)
                if 'ucc_event' in record.__dict__:result.fields['event']='FAILURE'
                return result
            with patch.object(safe,'safe_record',mutant):yield
        @contextmanager
        def approve_any_email(counter):
            def mutant(*args,**kwargs):counter.hits+=1;return []
            with patch.object(checks,'secure_email_check',mutant):yield
        @contextmanager
        def call_formatter(counter):
            def mutant(handler,record):counter.hits+=1;handler.format(record)
            with patch.object(safe.SanitizingHandler,'emit',mutant):yield
        @contextmanager
        def no_reentry(counter):
            class Inert:
                @property
                def active(self):counter.hits+=1;return False
                @active.setter
                def active(self,value):pass
            with patch.object(safe,'_LOCAL',Inert()):yield
        for name,case,method,mutation in (
            ('raw_message',sink_tests.SinkTests,'test_all_sensitive_record_fields_are_dropped_without_mutation',copy_message),
            ('raw_request_retained',sink_tests.SinkTests,'test_all_sensitive_record_fields_are_dropped_without_mutation',copy_request),
            ('loose_event_type',sink_tests.SinkTests,'test_fixed_typed_events_and_malformed_types',loose_event),
            ('unapproved_email_allowed',profiles.ProfileTests,'test_e105_empty_allowlist_and_exact_identity_not_subclasses',approve_any_email),
            ('arbitrary_formatter',sink_tests.SinkTests,'test_one_write_reentry_and_no_formatter_calls',call_formatter),
            ('missing_reentry_guard',sink_tests.SinkTests,'test_one_write_reentry_and_no_formatter_calls',no_reentry),
        ):self.memory(name,case,method,mutation)

    def test_startup_guard_and_r5_t2_mutation(self):
        self.checkout('startup_guard_removed_r5_t2',[
            ('accounts/log_privacy.py','    if not valid_graph():\n','    if False:  # mutant\n')],
            'test_r5_t2_unsafe_objects_exist_at_guard_boundary_and_fail_startup')

        self.checkout('logging_helper_removed',[
            ('config/settings/auth_common.py','    configure_privacy(namespace)\n','    pass  # mutant\n')],
            'test_protected_and_excluded_graphs_and_hook_identities')
        for name in ('secure_debug_check','secure_email_check'):
            self.checkout(name+'_deploy_only',[
                ('accounts/checks.py','@register()\ndef '+name+'(', '@register(deploy=True)\ndef '+name+'(')],
                'test_e104_e105_ordinary_and_deploy_checks_independent_of_privacy')

    def test_early_last_resort_deferred_to_ready_mutation(self):
        self.checkout('last_resort_deferred_until_ready',[
            ('accounts/log_privacy.py','        logging.lastResort = SanitizingHandler(logging.WARNING)\n','        pass  # mutant: deferred\n'),
            ('accounts/apps.py','            enforce_startup()\n',
             '            import logging\n            from .logging import SanitizingHandler\n            logging.lastResort = SanitizingHandler(logging.WARNING)\n            enforce_startup()\n')],
            'test_early_last_resort_and_hooks_before_configure_logging_and_ready')

    def test_hook_baseexception_propagation_mutations(self):
        blocks=(
            ('main','def process_exception_hook(exc_type, exc, traceback):\n    try:\n        _hook_emit(exc)\n    except BaseException:\n        return\n'),
            ('thread','def thread_exception_hook(args):\n    try:\n        if args.exc_type is not SystemExit:\n            _hook_emit(args.exc_value)\n    except BaseException:\n        return\n'),
            ('unraisable','def unraisable_exception_hook(args):\n    try:\n        _hook_emit(args.exc_value)\n    except BaseException:\n        return\n'),
        )
        for name,old in blocks:
            self.checkout('unsafe_'+name+'_hook_propagation',[
                ('accounts/logging.py',old,old.replace('except BaseException:','except Exception:'))],
                ('test_main_thread_unraisable_emission_failures_contain_all_baseexceptions' if name=='main'
                 else 'test_hook_stream_failures_and_guard_failures_are_contained'))

    def test_runner_rejects_noop_unexercised_and_error_controls(self):
        # Exercise the actual judge, without accepting its expected assertion as evidence.
        baseline={'run':1,'failures':0,'errors':[]};failed={'run':1,'failures':1,'errors':[]}
        for mutant,hit in ((baseline,True),(failed,False),(dict(failed,errors=['synthetic']),True)):
            with redirect_stdout(StringIO()) as captured, self.assertRaises(AssertionError):
                self.judge('expected_guard_rejection',baseline,mutant,hit)
            self.assertIn('B1B_MUTATION_UNDETECTED=',captured.getvalue())
        print('B1B_RUNNER_GUARDS=PASS')
