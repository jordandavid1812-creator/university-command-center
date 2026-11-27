"""B1b pure sink/walker tests; bytes and positive output, not assertLogs."""
from dataclasses import FrozenInstanceError
from io import StringIO
import logging
from pathlib import Path
import ast
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from django.db import utils
from django.http import HttpRequest
from django.test import SimpleTestCase, override_settings
from accounts import exception_chain as chain
from accounts import logging as safe
from accounts import log_privacy
from accounts import checks

S = 'SYNTHETIC_PRIVATE_SENTINEL_7c91'


class SinkTests(SimpleTestCase):
    databases = {'default', 'runtime', 'auth'}

    def record(self, **extra):
        r = logging.LogRecord('django.request', logging.ERROR, S, 9, S + '%s', (S,),
                              (RuntimeError, RuntimeError(S), None))
        r.__dict__.update(extra)
        return r

    def output(self, record):
        stream = StringIO(); safe.SanitizingHandler(stream=stream).emit(record)
        result = stream.getvalue()
        self.assertTrue(result.startswith('ucc-log ')); self.assertTrue(result.endswith('\n'))
        self.assertEqual(result.count('\n'), 1); self.assertNotIn(S, result)
        return result

    def test_all_sensitive_record_fields_are_dropped_without_mutation(self):
        request = HttpRequest(); request.method = 'POST'; request.path = '/reset/' + S
        request.META = {'HTTP_COOKIE': S, 'HTTP_AUTHORIZATION': S, 'REMOTE_ADDR': S,
                        'QUERY_STRING': S, 'HTTP_USER_AGENT': S}
        request.COOKIES = {'sessionid': S}; request.resolver_match = SimpleNamespace(view_name='accounts:reset-confirm')
        r = self.record(request=request, exc_text=S, stack_info=S, ucc_probe=S)
        before = dict(r.__dict__); meta = dict(request.META)
        with patch.object(r, 'getMessage', side_effect=AssertionError('must not format')):
            line = self.output(r)
        self.assertIn('method=POST route=accounts:reset-confirm', line)
        self.assertEqual(r.__dict__, before); self.assertEqual(request.META, meta)
        self.assertTrue(r.request is request); self.assertEqual(request.path, '/reset/' + S)
        converted = safe.safe_record(r)
        for key in ('request', 'ucc_probe'):self.assertNotIn(key, converted.__dict__)
        self.assertIsNone(converted.exc_info); self.assertIsNone(converted.exc_text)
        self.assertIsNone(converted.stack_info); self.assertIsNone(converted.args)

    def test_malformed_labels_and_adversarial_names_emit_constants(self):
        class SentinelError(utils.OperationalError):pass
        for name in ('accounts.'+S, S, 'django.security.'+S):
            r = self.record(name=name, levelname=S, levelno=True, status_code=True,
                            exc_info=(SentinelError, SentinelError(S), None))
            line=self.output(r)
            self.assertIn('level=OTHER status=-',line);self.assertIn('exc=OTHER',line)
        request=HttpRequest();request.method=S;request.resolver_match=SimpleNamespace(view_name=S)
        self.assertIn('method=OTHER route=other',self.output(self.record(request=request)))
        for status in (0,600,200.0,S,None):self.assertIn('status=-',self.output(self.record(status_code=status)))

    def test_fixed_typed_events_and_malformed_types(self):
        event=safe.FailureEvent(safe.EventKind.FAILURE,safe.FailureCategory.UNCLASSIFIED,'55P03')
        line=self.output(self.record(ucc_event=event))
        self.assertIn('event=FAILURE category=UNCLASSIFIED sqlstate=55P03',line)
        with self.assertRaises(FrozenInstanceError):event.sqlstate=S
        class Derived(safe.FailureEvent):pass
        for wrong in (S, {'event':S}, Derived(event.event,event.category),
                      safe.FailureEvent(S,event.category),safe.FailureEvent(event.event,True)):
            self.assertIn('event=- category=- sqlstate=-',self.output(self.record(ucc_event=wrong)))
        for bad in (S,'ZZZZZ',False,12345):
            item=safe.FailureEvent(event.event,event.category,bad)
            self.assertIn('sqlstate=XXXXX',self.output(self.record(ucc_event=item)))

    def test_one_write_reentry_and_no_formatter_calls(self):
        writes=[];handler=safe.SanitizingHandler()
        class Reenter:
            def write(inner,line):
                writes.append(line);handler.emit(self.record())
        handler.stream=Reenter()
        with patch.object(handler,'format',side_effect=AssertionError('formatter forbidden')):
            handler.emit(self.record())
        self.assertEqual(len(writes),1);self.assertNotIn(S,writes[0])
        self.assertFalse(safe._LOCAL.active)

    def test_failure_fallback_and_stream_failure_have_no_raw_output(self):
        stream=StringIO();handler=safe.SanitizingHandler(stream=stream)
        with patch.object(safe,'safe_record',side_effect=RuntimeError(S)):
            handler.emit(self.record())
        self.assertEqual(stream.getvalue(),safe.FALLBACK)
        calls=[]
        class Broken:
            def write(inner,line):calls.append(line);raise OSError(S)
        with patch.object(logging.Handler,'handleError',side_effect=AssertionError('raw fallback')):
            safe.SanitizingHandler(stream=Broken()).emit(self.record())
        self.assertEqual(len(calls),1);self.assertNotIn(S,calls[0]);self.assertFalse(safe._LOCAL.active)
        class Short:
            def write(inner,line):calls.append(line);return 1
        safe.SanitizingHandler(stream=Short()).emit(self.record())
        self.assertEqual(len(calls),2)

    def test_normal_handler_process_controls_propagate_and_restore_guard(self):
        for exc in (KeyboardInterrupt,SystemExit,GeneratorExit):
            with patch.object(safe,'safe_record',side_effect=exc(S)),self.assertRaises(exc):
                safe.SanitizingHandler(stream=StringIO()).emit(self.record())
            self.assertFalse(safe._LOCAL.active)

    def test_child_propagation_and_last_resort_are_sanitized(self):
        stream=StringIO();root=logging.getLogger();handler=root.handlers[0]
        with patch.object(handler,'stream',stream):logging.getLogger('django.b1probe.child').error(S)
        self.assertIn('logger=django',stream.getvalue());self.assertNotIn(S,stream.getvalue())
        logger=logging.getLogger('accounts.b1probe.last');old=logger.propagate
        try:
            logger.propagate=False
            with patch.object(logging.lastResort,'stream',stream):logger.warning(S)
        finally:logger.propagate=old
        self.assertNotIn(S,stream.getvalue());self.assertEqual(stream.getvalue().count('\n'),2)

    def test_graph_admins_and_secure_checks(self):
        self.assertTrue(log_privacy.valid_graph())
        logger=logging.getLogger('django.security');raw=logging.StreamHandler(StringIO())
        logger.addHandler(raw)
        try:
            self.assertFalse(log_privacy.valid_graph())
            self.assertEqual([e.id for e in checks.logging_graph_check()],['accounts.E103'])
        finally:logger.removeHandler(raw)
        root=logging.getLogger();f=logging.Filter();root.addFilter(f)
        try:self.assertFalse(log_privacy.valid_graph())
        finally:root.removeFilter(f)
        raw=logging.Formatter(S+" %(message)s")
        with patch.object(root.handlers[0],'formatter',raw):self.assertFalse(log_privacy.valid_graph())
        with override_settings(ADMINS=[('synthetic','synthetic@example.invalid')]):
            self.assertEqual([e.id for e in checks.logging_admins_check()],['accounts.E102'])
        with override_settings(UCC_SECURE_PROFILE=True,DEBUG=True):
            self.assertEqual([e.id for e in checks.secure_debug_check()],['accounts.E104'])

    def test_route_allowlist_matches_both_roots(self):
        from django.urls import URLPattern, URLResolver, get_resolver
        def names(patterns,prefix=''):
            result=set()
            for item in patterns:
                if isinstance(item,URLResolver):result |= names(item.url_patterns,prefix+(item.namespace+':' if item.namespace else ''))
                elif isinstance(item,URLPattern) and item.name:result.add(prefix+item.name)
            return result
        actual=set()
        for root in ('config.auth_urls','config.web_urls'):actual |= names(get_resolver(root).url_patterns)
        self.assertEqual(actual,set(safe.ROUTES))

    def test_source_audit_no_runtime_logging_reconfiguration(self):
        root=Path(__file__).resolve().parents[1]
        allowed={root/'accounts/logging.py',root/'accounts/log_privacy.py'}
        banned={'addHandler','removeHandler','addFilter','removeFilter','setFormatter','setLevel',
                'dictConfig','fileConfig','basicConfig','captureWarnings','setLoggerClass',
                'setLogRecordFactory','disable'}
        for package in ('accounts','academics','student_web','config'):
            for path in (root/package).rglob('*.py'):
                if path in allowed:continue
                tree=ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                        self.assertNotIn(node.func.attr,banned,str(path))
                    if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
                        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                        for target in targets:
                            if isinstance(target,ast.Attribute):
                                self.assertNotIn(target.attr,{'handlers','filters','formatter','propagate','disabled','excepthook','unraisablehook'},str(path))


class WalkerTests(SimpleTestCase):
    databases = {'default','runtime','auth'}

    def test_cause_context_suppression_and_outer_label(self):
        outer=utils.OperationalError(S);cause=psycopg.errors.LockNotAvailable(S)
        outer.__context__=psycopg.errors.UndefinedColumn(S);outer.__cause__=cause
        self.assertEqual(chain.walk(outer).nodes,(outer,cause))
        self.assertEqual(chain.labels(outer),'django.OperationalError,psycopg.errors[55P03]')
        outer.__cause__=None;outer.__suppress_context__=True
        self.assertEqual(chain.walk(outer).nodes,(outer,))
        opaque=RuntimeError(S);opaque.__cause__=cause
        self.assertEqual(chain.labels(opaque),'OTHER');self.assertEqual(chain.walk(opaque).nodes,())
        outer.__cause__=opaque;self.assertEqual(chain.walk(outer).nodes,(outer,))

    def test_cycles_and_sixteen_node_limit(self):
        a=utils.DatabaseError(S);b=utils.DatabaseError(S);a.__cause__=b;b.__cause__=a
        self.assertTrue(chain.walk(a).truncated);self.assertEqual(len(chain.walk(a).nodes),2)
        nodes=[utils.DatabaseError(S) for _ in range(17)]
        for a,b in zip(nodes,nodes[1:]):a.__cause__=b
        self.assertEqual(len(chain.walk(nodes[0]).nodes),16);self.assertTrue(chain.walk(nodes[0]).truncated)
        self.assertIn('TRUNCATED',chain.labels(nodes[0]))
        nodes[15].__cause__=None;self.assertFalse(chain.walk(nodes[0]).truncated)

    def test_exception_groups_are_opaque_and_text_never_read(self):
        class Trap(utils.DatabaseError):
            def __str__(self):raise AssertionError('no str')
            def __repr__(self):raise AssertionError('no repr')
        self.assertEqual(chain.labels(Trap(S)),'OTHER')
        for group in (ExceptionGroup(S,[psycopg.errors.LockNotAvailable(S)]),
                      BaseExceptionGroup(S,[KeyboardInterrupt(S)])):
            self.assertEqual(chain.labels(group),'OTHER');self.assertEqual(chain.walk(group).nodes,())

    def test_class_sqlstate_precedes_instance_and_validates_lookup(self):
        exc=psycopg.errors.LockNotAvailable(S);exc.sqlstate=S
        self.assertEqual(chain.class_sqlstate(exc),'55P03')
        for code in (None,S,'ZZZZZ',True,'42703'):
            with patch.object(type(exc),'sqlstate',code):self.assertIsNone(chain.class_sqlstate(exc))
        with patch.object(chain.psycopg.errors,'lookup',side_effect=RuntimeError(S)):
            self.assertIsNone(chain.class_sqlstate(exc))
        class RaisingMeta(type):
            def __getattribute__(cls,name):
                if name=='sqlstate':raise RuntimeError(S)
                return super().__getattribute__(name)
        class Raising(psycopg.Error,metaclass=RaisingMeta):pass
        raising=Raising.__new__(Raising);BaseException.__init__(raising,S)
        with patch.object(chain,'DRIVER_CLASSES',frozenset([Raising])):
            self.assertIsNone(chain.class_sqlstate(raising))
        class Trap(psycopg.OperationalError):
            @property
            def diag(self):raise AssertionError('no diagnostic access')
            @property
            def sqlstate(self):raise AssertionError('no instance SQLSTATE')
        trap=Trap.__new__(Trap);BaseException.__init__(trap,S)
        self.assertIsNone(chain.class_sqlstate(trap))
