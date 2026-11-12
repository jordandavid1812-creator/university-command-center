"""B1a settings/registration contracts; no privileged requests or logging changes."""
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from accounts.checks import database_safety_check
from accounts.dbsafety import apply_db_safety, validate_values, DEFAULTS


class SafetyConfigurationTests(SimpleTestCase):
    databases = {"default", "runtime", "auth"}
    def namespace(self):
        db = {'ENGINE':'django.db.backends.postgresql', 'OPTIONS':{
            'sslmode':'verify-full', 'sslrootcert':'synthetic-ca.pem', 'application_name':'synthetic'}}
        return {'DATABASES':{'default':deepcopy(db), 'auth':deepcopy(db), 'runtime':deepcopy(db)},
                'STUDENT_DB_ALIAS':'runtime', 'UCC_DB_SAFETY_VALUES':dict(DEFAULTS)}

    def test_fixed_options_tls_idempotence_and_migrator_exclusion(self):
        n = self.namespace(); original = deepcopy(n['DATABASES'])
        apply_db_safety(n); first = deepcopy(n)
        apply_db_safety(n)
        self.assertEqual(n, first)
        self.assertEqual(n['DATABASES']['default'], original['default'])
        self.assertEqual(original['auth']['OPTIONS'].get('options'), None)
        for alias, statement in [('auth',5000),('runtime',10000)]:
            actual = n['DATABASES'][alias]['OPTIONS']
            self.assertEqual(actual['options'],f'-c lock_timeout=3000 -c statement_timeout={statement} -c idle_in_transaction_session_timeout=15000')
            self.assertEqual(actual['connect_timeout'],5)
            for key in ('sslmode','sslrootcert','application_name'):
                self.assertEqual(actual[key],original[alias]['OPTIONS'][key])
        self.assertTrue(n['UCC_DB_SAFETY_CONFIGURED'])
        self.assertEqual(apps.get_app_config('accounts').name, 'accounts')
        self.assertEqual(apps.get_app_config('accounts').label, 'accounts')

    def test_bad_types_ranges_and_cross_alias_relationships_are_rejected(self):
        for bad in [True,False,2.0,Decimal('5'), '5.0',' 5','+5','5s','1e3',0,-1,'',None]:
            for key in DEFAULTS:
                with self.subTest(key=key,bad_type=type(bad).__name__):
                    with self.assertRaises(ImproperlyConfigured):
                        validate_values(dict(DEFAULTS, **{key:bad}))
        for key, bad in [('connect_seconds',1),('connect_seconds',31),('lock_ms',999),
                         ('auth_statement_ms',3000),('runtime_statement_ms',3000),
                         ('auth_statement_ms',60001),('runtime_statement_ms',60001),
                         ('idle_ms',4999),('idle_ms',300001)]:
            with self.subTest(key=key,bad=bad), self.assertRaises(ImproperlyConfigured):
                validate_values(dict(DEFAULTS, **{key:bad}))
        for key, value in [('connect_seconds',2),('connect_seconds',30),('lock_ms',1000),
                           ('auth_statement_ms',60000),('runtime_statement_ms',60000),
                           ('idle_ms',5000),('idle_ms',300000)]:
            self.assertEqual(validate_values(dict(DEFAULTS, **{key:value}))[key], value)
        self.assertEqual(validate_values({k:str(v).zfill(8) for k,v in DEFAULTS.items()}),DEFAULTS)

    def test_conflicting_options_connect_timeout_and_pgoptions_fail_before_mutation(self):
        for bad in [None,False,[], '-c lock_timeout=1', '-c search_path=public',
                    '-c lock_timeout=3000 -c lock_timeout=3000']:
            n=self.namespace(); n['DATABASES']['auth']['OPTIONS']['options']=bad; before=deepcopy(n)
            with self.subTest(option_type=type(bad).__name__), self.assertRaises(ImproperlyConfigured):
                apply_db_safety(n)
            self.assertEqual(n,before)
        for bad in [True,2,'5s']:
            n=self.namespace();n['DATABASES']['auth']['OPTIONS']['connect_timeout']=bad
            with self.assertRaises(ImproperlyConfigured):apply_db_safety(n)
        for value in ['', '-c statement_timeout=0']:
            with patch.dict(os.environ,PGOPTIONS=value), self.assertRaises(ImproperlyConfigured):
                apply_db_safety(self.namespace())

    def test_e101_is_specific_flag_gated_and_detects_missing_options(self):
        dbs=deepcopy(settings.DATABASES); dbs['auth']['OPTIONS'].pop('options')
        with override_settings(DATABASES=dbs,UCC_DB_SAFETY_CONFIGURED=True):
            self.assertEqual([e.id for e in database_safety_check()],['accounts.E101'])
        with override_settings(DATABASES=dbs,UCC_DB_SAFETY_CONFIGURED=False):
            self.assertEqual(database_safety_check(),[])

    def test_profiles_and_real_web_secure_check_command(self):
        root=Path(__file__).resolve().parents[1]
        protected=['auth_development','auth_secure','auth_test','web_development','web_secure','web_test']
        excluded=['auth_migration','test','security_test','development','runtime']
        code='''import django,json;django.setup()
from django.conf import settings
from django.apps import apps
from django.core.checks import run_checks
print(json.dumps({'flag':getattr(settings,'UCC_DB_SAFETY_CONFIGURED',False),
'configured':[k for k,v in settings.DATABASES.items() if 'options' in v.get('OPTIONS',{})],
'identity':[apps.get_app_config('accounts').name,apps.get_app_config('accounts').label],
'errors':[e.id for e in run_checks() if e.id=='accounts.E101']}))'''
        for profile in protected+excluded:
            env=dict(os.environ,DJANGO_SETTINGS_MODULE='config.settings.'+profile,PYTHONPATH=str(root.parent))
            result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,profile)
            data=json.loads(result.stdout)
            self.assertEqual(data['identity'],['accounts','accounts'])
            self.assertEqual(data['errors'],[])
            self.assertEqual(data['flag'],profile in protected)
            expected=(['auth','runtime'] if profile in ('auth_test','web_test') else ['default','auth']) if profile in protected else []
            self.assertEqual(sorted(data['configured']),sorted(expected))
            if profile in excluded:
                command=subprocess.run([sys.executable,'manage.py','check','--settings=config.settings.'+profile],cwd=root,env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(command.returncode,0,profile)
                self.assertNotIn('accounts.E101',command.stdout+command.stderr)
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'b1_bad_profile.py').write_text('from config.settings.web_secure import *\nDATABASES["auth"]["OPTIONS"].pop("options")\n')
            env=dict(os.environ,PYTHONPATH=temp+os.pathsep+str(root.parent))
            p=subprocess.run([sys.executable,'manage.py','check','--deploy','--settings=b1_bad_profile'],cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('accounts.E101',p.stdout+p.stderr)  # unrelated warnings are allowed
