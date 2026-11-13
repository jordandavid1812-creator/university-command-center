"""Fresh-process profile, uncaught-hook and R5-T2 boundary evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from accounts import checks, log_privacy

S='SYNTHETIC_HOOK_SECRET_fa09'
SERVER=Path(__file__).resolve().parents[1]
PROTECTED=('auth_development','auth_secure','auth_test','web_development','web_secure','web_test')
EXCLUDED=('auth_migration','development','runtime','test','security_test')


def process(code,profile='auth_test',extra_path=None,args=(),timeout=40,env_updates=None):
    paths=[str(SERVER.parent),str(SERVER)]
    if extra_path:paths.insert(0,extra_path)
    env=dict(os.environ,DJANGO_SETTINGS_MODULE='config.settings.'+profile,
             PYTHONPATH=os.pathsep.join(paths),PYTHONDONTWRITEBYTECODE='1')
    env.update(env_updates or {})
    return subprocess.run([sys.executable,'-c',code,*args],cwd=SERVER,env=env,
                          capture_output=True,text=True,timeout=timeout)


class ProfileTests(SimpleTestCase):
    databases={'default','runtime','auth'}

    def test_protected_and_excluded_graphs_and_hook_identities(self):
        code='''import sys,threading,json,logging,django
django.setup()
from django.conf import settings
from django.core.checks import run_checks
from accounts.log_privacy import valid_graph
print(json.dumps({'privacy':getattr(settings,'UCC_LOG_PRIVACY',None),
'secure':getattr(settings,'UCC_SECURE_PROFILE',False),
'graph':valid_graph(),'hooks_default':sys.excepthook is sys.__excepthook__ and threading.excepthook is threading.__excepthook__ and sys.unraisablehook is sys.__unraisablehook__,
'errors':[e.id for e in run_checks()],
'django_handlers':[type(h).__name__ for h in logging.getLogger('django').handlers]}))'''
        for profile in PROTECTED+EXCLUDED:
            with self.subTest(profile=profile):
                p=process(code,profile);self.assertEqual(p.returncode,0,p.stderr)
                data=json.loads(p.stdout)
                if profile in PROTECTED:
                    self.assertEqual(data['privacy'],'enforce');self.assertTrue(data['graph'])
                    self.assertFalse(data['hooks_default']);self.assertEqual(data['django_handlers'],[])
                    self.assertEqual(data['errors'],['accounts.E105'] if profile.endswith('secure') else [])
                else:
                    self.assertIsNone(data['privacy']);self.assertTrue(data['hooks_default'])
                    self.assertEqual(data['django_handlers'],['StreamHandler','AdminEmailHandler'])
                    self.assertFalse(any(e in data['errors'] for e in ('accounts.E102','accounts.E103','accounts.E104','accounts.E105')))

    def test_early_last_resort_and_hooks_before_configure_logging_and_ready(self):
        code='''import logging,sys,threading
from accounts.log_privacy import configure
from accounts.logging import SanitizingHandler,process_exception_hook,thread_exception_hook,unraisable_exception_hook
n={};configure(n);first=logging.lastResort;configure(n)
assert logging.lastResort is first
assert sys.excepthook is process_exception_hook and threading.excepthook is thread_exception_hook and sys.unraisablehook is unraisable_exception_hook
assert not logging.getLogger().handlers
logging.getLogger('accounts.early').error('SYNTHETIC_HOOK_SECRET_fa09')
print('EARLY_OK')'''
        p=process(code);self.assertEqual(p.returncode,0)
        self.assertEqual(p.stdout.strip(),'EARLY_OK');self.assertIn('ucc-log ',p.stderr);self.assertNotIn(S,p.stderr)

    def test_r5_t2_unsafe_objects_exist_at_guard_boundary_and_fail_startup(self):
        for kind in ('handler','filter','formatter','hook'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                if kind=='handler':
                    extra="LOGGING['handlers']['raw']={'class':'logging.StreamHandler'}\nLOGGING['loggers']['django.security']={'handlers':['raw'],'propagate':True}\n"
                    proof="assert any(type(h) is logging.StreamHandler for h in logging.getLogger('django.security').handlers)"
                elif kind=='filter':
                    extra="LOGGING['filters']={'raw':{'()':'logging.Filter'}}\nLOGGING['root']['filters']=['raw']\n"
                    proof='assert logging.getLogger().filters'
                elif kind=='formatter':
                    extra="LOGGING['formatters']={'raw':{'format':'%(message)s'}}\nLOGGING['handlers']['safe']['formatter']='raw'\n"
                    proof='assert logging.getLogger().handlers[0].formatter is not None'
                else:
                    extra=''
                    proof="sys.excepthook=sys.__excepthook__;assert sys.excepthook is sys.__excepthook__"
                Path(temp,'unsafe_profile.py').write_text('from config.settings.auth_test import *\n'+extra)
                code='''import os,sys,logging
os.environ['DJANGO_SETTINGS_MODULE']='unsafe_profile'
from accounts import log_privacy
real=log_privacy.enforce_startup
def boundary():
    PROOF
    print('UNSAFE_PRESENT',flush=True)
    real()
log_privacy.enforce_startup=boundary
import django
django.setup()
'''.replace('    PROOF','    '+proof)
                p=process(code,extra_path=temp)
                self.assertNotEqual(p.returncode,0);self.assertIn('UNSAFE_PRESENT',p.stdout)
                # A hook mutation deliberately tests its identity at startup; do not emit a secret here.

    def test_offline_commands_and_existing_provisioning_remain_usable(self):
        from django.db import connections
        code='import sys;from django.core.management import execute_from_command_line;execute_from_command_line(["manage.py"]+sys.argv[1:])'
        for profile in EXCLUDED:
            p=process(code,args=('check','--settings=config.settings.'+profile))
            self.assertEqual(p.returncode,0,p.stderr)
        env={'PGDATABASE':connections['default'].settings_dict['NAME']}
        for command in [('migrate','--plan'),('configure_runtime',),('configure_auth_role',)]:
            p=process(code,args=(*command,'--settings=config.settings.auth_migration'),env_updates=env)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertNotIn('accounts.E10',p.stderr)

    def test_e105_empty_allowlist_and_exact_identity_not_subclasses(self):
        from django.core.mail.backends.locmem import EmailBackend
        class Subclass(EmailBackend):pass
        with override_settings(UCC_SECURE_PROFILE=True):
            for backend in ('django.core.mail.backends.console.EmailBackend','django.core.mail.backends.filebased.EmailBackend',
                            'django.core.mail.backends.smtp.EmailBackend','django.core.mail.backends.locmem.EmailBackend',
                            'missing.invalid.Backend'):
                with override_settings(EMAIL_BACKEND=backend):self.assertEqual([e.id for e in checks.secure_email_check()],['accounts.E105'])
            with patch.object(log_privacy,'APPROVED_EMAIL_BACKENDS',(EmailBackend,)):
                with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
                    self.assertEqual(checks.secure_email_check(),[])
                with patch('django.utils.module_loading.import_string',return_value=Subclass):
                    self.assertEqual([e.id for e in checks.secure_email_check()],['accounts.E105'])
            from django.core.mail.backends.console import EmailBackend as Console
            from django.core.mail.backends.filebased import EmailBackend as File
            class ConsoleSubclass(Console):pass
            class FileSubclass(File):pass
            class Wrapper:
                def send_messages(self,messages):return Console().send_messages(messages)
            for backend in (ConsoleSubclass,FileSubclass,Wrapper,object()):
                with patch('django.utils.module_loading.import_string',return_value=backend):
                    self.assertEqual([e.id for e in checks.secure_email_check()],['accounts.E105'])
        with override_settings(UCC_SECURE_PROFILE=False):self.assertEqual(checks.secure_email_check(),[])

    def test_e104_e105_ordinary_and_deploy_checks_independent_of_privacy(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'insecure_flags.py').write_text('from config.settings.web_secure import *\nUCC_LOG_PRIVACY="off"\nDEBUG=True\n')
            for deploy in (False,True):
                for module in ('config.settings.web_secure','insecure_flags'):
                    args=['check','--settings='+module]+(['--deploy'] if deploy else [])
                    code='import sys;from django.core.management import execute_from_command_line;execute_from_command_line(["manage.py"]+sys.argv[1:])'
                    p=process(code,extra_path=temp,args=args)
                    self.assertNotEqual(p.returncode,0);self.assertIn('accounts.E105',p.stderr)
                    if module=='insecure_flags':self.assertIn('accounts.E104',p.stderr)


class HookTests(SimpleTestCase):
    databases={'default','runtime','auth'}

    def test_main_thread_unraisable_emission_failures_contain_all_baseexceptions(self):
        for path in ('main','thread','unraisable'):
            for failure in ('none','KeyboardInterrupt','SystemExit','GeneratorExit','Exception'):
                with self.subTest(path=path,failure=failure):
                    code='''import sys,threading,builtins,gc,weakref
from accounts.log_privacy import configure
configure({})
from accounts import logging as safe
FAILURE
if PATH=='main':raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
if PATH=='thread':
    def run():raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
    t=threading.Thread(target=run,name='SYNTHETIC_HOOK_SECRET_fa09');t.start();t.join();print('MAIN_CONTINUED')
if PATH=='unraisable':
    class Bad:
        def __repr__(self):raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
        def __del__(self):raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
    x=Bad();ref=weakref.ref(x);del x;gc.collect();assert ref() is None;print('MAIN_CONTINUED')
'''.replace('PATH',repr(path))
                    fault='' if failure=='none' else 'def broken(exc):raise builtins.'+failure+"('SYNTHETIC_HOOK_SECRET_fa09')\nsafe._hook_emit=broken"
                    code=code.replace('FAILURE',fault)
                    p=process(code);self.assertEqual(p.returncode,1 if path=='main' else 0)
                    for marker in (S,'Original exception was','Exception ignored','Error in sys.excepthook'):
                        self.assertNotIn(marker,p.stderr)
                    if path!='main':self.assertIn('MAIN_CONTINUED',p.stdout)
                    if failure=='none':self.assertIn('ucc-log ',p.stderr)

    def test_hook_stream_failures_and_guard_failures_are_contained(self):
        for failure in ('KeyboardInterrupt','SystemExit','GeneratorExit','Exception'):
            code='''import builtins,sys
from types import SimpleNamespace
from accounts.log_privacy import configure
configure({})
from accounts import logging as safe
class Broken:
    def write(self,line):raise builtins.FAIL('SYNTHETIC_HOOK_SECRET_fa09')
old=sys.stderr;sys.stderr=Broken()
e=RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
sys.excepthook(type(e),e,None)
import threading
threading.excepthook(SimpleNamespace(exc_type=type(e),exc_value=e))
sys.unraisablehook(SimpleNamespace(exc_value=e))
sys.stderr=old
print('HOOKS_RETURNED')
'''.replace('FAIL',failure)
            p=process(code);self.assertEqual(p.returncode,0);self.assertEqual(p.stdout.strip(),'HOOKS_RETURNED');self.assertEqual(p.stderr,'')
        code='''from types import SimpleNamespace
from accounts import logging as safe
class Broken:
    def __getattribute__(self,name):raise KeyboardInterrupt('SYNTHETIC_HOOK_SECRET_fa09')
safe._LOCAL=Broken()
e=RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')
safe.process_exception_hook(type(e),e,None)
safe.thread_exception_hook(SimpleNamespace(exc_type=type(e),exc_value=e))
safe.unraisable_exception_hook(SimpleNamespace(exc_value=e))
print('GUARD_RETURNED')'''
        p=process(code);self.assertEqual(p.returncode,0);self.assertEqual(p.stderr,'');self.assertIn('GUARD_RETURNED',p.stdout)
        cleanup=code.replace("def __getattribute__(self,name):raise KeyboardInterrupt('SYNTHETIC_HOOK_SECRET_fa09')",
            "def __getattribute__(self,name):return False\n    def __setattr__(self,name,value):\n        if value is False:raise GeneratorExit('SYNTHETIC_HOOK_SECRET_fa09')")
        p=process(cleanup);self.assertEqual(p.returncode,0);self.assertNotIn(S,p.stderr)
        self.assertNotIn('Original exception was',p.stderr);self.assertIn('GUARD_RETURNED',p.stdout)

    def test_original_process_controls_and_thread_only_exit(self):
        for error,status in [('SystemExit(7)',7),('KeyboardInterrupt()',(-2,130)),('GeneratorExit()',1)]:
            p=process('from accounts.log_privacy import configure;configure({});raise '+error)
            self.assertIn(p.returncode,status if isinstance(status,tuple) else (status,));self.assertNotIn('Traceback',p.stderr)
        p=process('''import threading
from accounts.log_privacy import configure
configure({})
def stop():raise SystemExit(9)
t=threading.Thread(target=stop);t.start();t.join();print('THREAD_ONLY')''')
        self.assertEqual(p.returncode,0);self.assertEqual(p.stderr,'');self.assertIn('THREAD_ONLY',p.stdout)

    def test_traceback_command_re_raise_reaches_hook_but_direct_output_does_not(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp,'probeapp/management/commands');folder.mkdir(parents=True)
            for p in [Path(temp,'probeapp/__init__.py'),folder.parent/'__init__.py',folder/'__init__.py']:p.write_text('')
            (folder/'probe.py').write_text('from django.core.management.base import BaseCommand,CommandError\nclass Command(BaseCommand):\n    def handle(self,*a,**kw):raise CommandError("SYNTHETIC_HOOK_SECRET_fa09")\n')
            Path(temp,'command_profile.py').write_text('from config.settings.auth_test import *\nINSTALLED_APPS=INSTALLED_APPS+["probeapp"]\n')
            code='import sys;from django.core.management import execute_from_command_line;execute_from_command_line(["manage.py","probe","--settings=command_profile"]+sys.argv[1:])'
            for args,raw in [((),True),(('--traceback',),False)]:
                p=process(code,extra_path=temp,args=args);self.assertEqual(p.returncode,1)
                self.assertEqual(S in p.stderr,raw)


    def test_documented_direct_output_boundaries_are_not_claimed_sanitized(self):
        snippets=(
            "import socketserver\ntry:raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')\nexcept Exception:socketserver.BaseServer.handle_error(None,None,('127.0.0.1',1))",
            "from wsgiref.handlers import SimpleHandler\nfrom io import StringIO\nimport sys\nh=SimpleHandler(StringIO(),StringIO(),sys.stderr,{})\ntry:raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')\nexcept Exception:h.log_exception(sys.exc_info())",
            "import unittest,sys\nclass Broken(unittest.TestCase):\n    def runTest(self):self.fail('SYNTHETIC_HOOK_SECRET_fa09')\nunittest.TextTestRunner(stream=sys.stderr).run(Broken())",
            "raise SystemExit('SYNTHETIC_HOOK_SECRET_fa09')",
        )
        for snippet in snippets:
            p=process('from accounts.log_privacy import configure;configure({})\n'+snippet)
            self.assertIn(S,p.stderr)  # Known raw bypass, synthetic data only; not a sink test.
        p=process("raise RuntimeError('SYNTHETIC_HOOK_SECRET_fa09')")
        self.assertEqual(p.returncode,1);self.assertIn(S,p.stderr)  # Before settings/hooks.
