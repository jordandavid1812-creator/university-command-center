# Revision 5 independent observation evidence

Companion to [the review](B1_REVISION_5_INDEPENDENT_REVIEW.md). These probes observe existing PR #29/Django behavior; they implement no B1 functionality. Synthetic students and disposable localhost PostgreSQL only. Python 3.12.14, Django 5.2.19, psycopg 3.3.8, PostgreSQL **17.11 (Debian 17.11-1.pgdg13+2)**. No SQLite.

## Setup and command

Use the hashed Django environment in an isolated worktree of `bec0a44` (accounts/config/auth_tests match integrated `42910ed`). The paths below are the actual review paths; substitute your own checkouts. Save the setup and both modules below in an ignored local `work/` directory. Do not add them to application discovery or run against real student data. The setup generates private local credentials rather than embedding any. The Docker socket is environment-specific; postgres:17 resolved to 17.11 for this run, so verify the actual server version before comparing.

```python
"""Disposable local-only verification setup, never a production bootstrap."""
import os
from pathlib import Path
import secrets
import subprocess
import time
import psycopg
from psycopg import sql

env = os.environ.copy()
for name in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
    env.pop(name, None)
env['POSTGRES_PASSWORD'] = secrets.token_urlsafe(32)
env['POSTGRES_USER'] = 'ucc_admin'
env['POSTGRES_DB'] = 'ucc_admin_scratch'
subprocess.run(['docker','--host=unix:///var/run/docker.sock','run','-d','--name','ucc-b1r5review-postgres',
                '-p','127.0.0.1:55443:5432','-e','POSTGRES_PASSWORD','-e','POSTGRES_USER','-e','POSTGRES_DB','postgres:17'],env=env,check=True)
admin = dict(host='127.0.0.1', port=55443, user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], dbname=env['POSTGRES_DB'])
for attempt in range(30):
    try:
        conn = psycopg.connect(**admin, autocommit=True)
        break
    except psycopg.OperationalError:
        time.sleep(1)
else:
    raise RuntimeError('PostgreSQL did not become ready')
runtime_password = secrets.token_urlsafe(32)
auth_password = secrets.token_urlsafe(32)
migration_password = secrets.token_urlsafe(32)
with conn:
    conn.execute(sql.SQL('CREATE ROLE ucc_migrator LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS CREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(migration_password)))
    conn.execute(sql.SQL('CREATE ROLE ucc_runtime LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(runtime_password)))
    conn.execute(sql.SQL('CREATE ROLE ucc_auth LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(auth_password)))
    conn.execute('CREATE DATABASE ucc_migration_scratch OWNER ucc_migrator')
values = dict(PGHOST='127.0.0.1', PGPORT='55443', PGUSER='ucc_migrator',
              PGPASSWORD=migration_password, PGDATABASE='ucc_migration_scratch', PGTESTDATABASE='test_ucc_security',
              UCC_AUTH_ROLE='ucc_auth', UCC_AUTH_PASSWORD=auth_password, UCC_RUNTIME_ROLE='ucc_runtime', UCC_RUNTIME_PASSWORD=runtime_password,
              UCC_CONTEXT_SIGNING_KEY=secrets.token_hex(32), DJANGO_SECRET_KEY=secrets.token_urlsafe(64))
path=Path('work/b1r5review-security.env'); path.touch(mode=0o600)
path.write_text(''.join(f'export {k}={v}\n' for k,v in values.items()))
values.update(PGUSER=admin['user'], PGPASSWORD=admin['password'], PGDATABASE=admin['dbname'], PGTESTDATABASE='test_ucc_foundation')
path=Path('work/b1r5review-foundation.env'); path.touch(mode=0o600)
path.write_text(''.join(f'export {k}={v}\n' for k,v in values.items()))
```

```sh
.venv/bin/python work/setup_b1r5review.py
set -e
source work/b1r5review-security.env
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/workspace/university-command-center/work \
PGTESTDATABASE=test_b1r5_review \
.venv/bin/python /workspace/university-command-center-pr29/server/manage.py \
  test b1r5_review_probes --settings=config.settings.auth_test -v 1
```

The existing runner creates/migrates its disposable database and configures separate migration, auth and runtime LOGINs. It destroys the test database afterwards. No credentials, actual hashes or session keys are printed.

## Inherited module: work/b1r4_review_probes.py

Unchanged from the Revision 4 independent evidence. Three methods: four successful login states, two response-save failures and autocommit persistence. The before-save fault is synthetic, not a real timeout/COMMIT interruption.

```python
"""Observation only, no proposed B1 code."""
import json
from unittest.mock import patch
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.contrib.auth import SESSION_KEY
from django.db import connections, OperationalError
from django.test import Client, override_settings
from auth_tests.base import AuthenticationCase
from accounts.principals import session_student
import accounts.views as views

def emit(**kw): print('R4_EVIDENCE='+json.dumps(kw,sort_keys=True))

class Revision4Probes(AuthenticationCase):
    def test_four_login_paths(self):
        for state in ('N','AN','SA','DA'):
            Session.objects.using('default').all().delete()
            c=Client(raise_request_exception=False)
            if state in ('SA','DA'): self.login(c)
            if state=='AN':
                s=c.session;s['synthetic']=True;s.save();c.cookies['sessionid']=s.session_key
            before=c.cookies['sessionid'].value if 'sessionid' in c.cookies else None
            cycles=[]; observation={}; real_cycle=SessionStore.cycle_key; real_login=views.auth_login
            def cycle(store):cycles.append(True);return real_cycle(store)
            def login(request,user,*a,**kw):
                result=real_login(request,user,*a,**kw)
                observation.update(key_is_none=request.session.session_key is None,
                    rows_inside_finalizer=Session.objects.using('auth').count())
                return result
            with patch.object(SessionStore,'cycle_key',cycle),patch.object(views,'auth_login',login):
                response=self.login(c,'bravo' if state=='DA' else 'alpha')
            self.assertEqual(response.status_code,302)
            self.assertEqual(len(cycles),1 if state in ('N','AN') else 0)
            self.assertEqual(observation['rows_inside_finalizer'],0 if state=='DA' else 1)
            emit(state=state,cycle_calls=len(cycles),same_key=before==c.cookies['sessionid'].value,**observation)

    def test_response_save_not_applied(self):
        for state in ('SA','DA'):
            Session.objects.using('default').all().delete()
            c=Client(raise_request_exception=False);self.login(c)
            old=c.cookies['sessionid'].value
            real=SessionStore.save
            def fail(store,must_create=False):
                if not must_create and store.get(SESSION_KEY):raise OperationalError('synthetic before response save')
                return real(store,must_create=must_create)
            with patch.object(SessionStore,'save',fail):r=self.login(c,'bravo' if state=='DA' else 'alpha')
            rows=list(Session.objects.using('default').all())
            self.assertEqual(r.status_code,500)
            self.assertEqual(len(rows),1 if state=='SA' else 0)
            if state=='SA':self.assertEqual(session_student(old).pk,self.a.pk)
            self.assertNotIn('sessionid',r.cookies)
            emit(state=state,phase='response save not applied',status=r.status_code,rows=len(rows),old_row_exists=any(s.pk==old for s in rows),new_cookie=False)

    def test_autocommit_without_explicit_commit(self):
        c=connections['auth']; self.assertTrue(c.get_autocommit())
        with patch.object(c,'_commit',wraps=c._commit) as commit:
            with c.cursor() as cursor:
                cursor.execute('INSERT INTO django_session (session_key,session_data,expire_date) VALUES (%s,%s,now()+interval \'1 hour\')',['synthetic-autocommit','synthetic'])
            persisted=Session.objects.using('default').filter(pk='synthetic-autocommit').exists()
            self.assertTrue(persisted);self.assertEqual(commit.call_count,0)
            emit(autocommit=True,explicit_commit_calls=commit.call_count,persisted=persisted)
```

## New module: work/b1r5_review_probes.py

Three additional methods: actual stale-hash login lifecycle, real throttle/CAS persistence despite a synthetic finalizer rollback, and real statement persistence versus rollback under identical post-execute fault injection. The last probe is **not** a COMMIT acknowledgement-loss experiment. Spies delegate to the real functions except at the expressly injected failure points.

```python
"""Observation-only Revision 5 probes; no B1 implementation."""
from unittest.mock import patch
import json
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.contrib.auth.hashers import make_password, check_password
from django.db import connections, transaction, OperationalError
from django.test import Client, override_settings
from django.utils import timezone
from accounts.models import Student, AuthThrottle
from accounts.principals import session_student
from auth_tests.base import PASSWORD
import accounts.views as views
import b1r4_review_probes as prior


def emit(**data): print('R5_EVIDENCE='+json.dumps(data,sort_keys=True))


class Revision5Probes(prior.Revision4Probes):
    def test_stale_same_account_hash_uses_response_insert(self):
        c=Client(raise_request_exception=False);self.login(c)
        old=c.cookies['sessionid'].value
        self.a.set_password(PASSWORD);self.a.save(using='default',update_fields=['password'])
        cycles=[];observed={};writes=[];phase=['before']
        realcycle=SessionStore.cycle_key;real_login=views.auth_login
        def cycle(store): cycles.append(True);return realcycle(store)
        def login(request,user,*a,**kw):
            phase[0]='finalizer';result=real_login(request,user,*a,**kw)
            observed.update(key_none=request.session.session_key is None,
                rows_inside_finalizer=Session.objects.using('auth').count())
            phase[0]='response';return result
        def trace(execute,sql,params,many,context):
            if 'django_session' in sql and sql.lstrip().startswith(('INSERT','UPDATE')):
                writes.append([sql.lstrip().split()[0],phase[0]])
            return execute(sql,params,many,context)
        with patch.object(SessionStore,'cycle_key',cycle),patch.object(views,'auth_login',login),connections['auth'].execute_wrapper(trace):
            response=self.login(c)
        self.assertEqual(response.status_code,302);self.assertEqual(cycles,[])
        self.assertEqual(observed,dict(key_none=True,rows_inside_finalizer=0))
        self.assertEqual(writes,[['INSERT','response']])
        self.assertNotEqual(c.cookies['sessionid'].value,old)
        self.assertEqual(session_student(c.cookies['sessionid'].value).pk,self.a.pk)
        emit(state='SX',cycle_calls=0,writes=writes,**observed)

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher',
                                       'django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_real_throttle_and_cas_survive_finalizer_rollback(self):
        before=make_password(PASSWORD,hasher='pbkdf2_sha256')
        Student.objects.using('default').filter(pk=self.a.pk).update(password=before)
        c=Client(raise_request_exception=False)
        with patch.object(connections['auth'],'_commit',side_effect=OperationalError('synthetic before COMMIT')):
            response=self.login(c)
        after=Student.objects.using('default').get(pk=self.a.pk).password
        self.assertEqual(response.status_code,500);self.assertNotEqual(after,before)
        self.assertTrue(check_password(PASSWORD,after))
        self.assertEqual(AuthThrottle.objects.using('default').get().attempts,1)
        self.assertEqual(Session.objects.using('default').count(),0)
        emit(throttle_persisted=True,CAS_persisted=True,finalizer_rolled_back=True)

    def test_post_execute_fault_is_not_uncertain_commit_in_atomic(self):
        connection=connections['auth']; value1=timezone.now()
        def after_update(execute,sql,params,many,context):
            result=execute(sql,params,many,context)
            if sql.lstrip().startswith('UPDATE') and 'accounts_student' in sql:
                raise OperationalError('synthetic after real execute')
            return result
        with self.assertRaises(OperationalError),connection.execute_wrapper(after_update):
            Student.objects.using('auth').filter(pk=self.a.pk).update(last_login=value1)
        self.assertEqual(Student.objects.using('default').get(pk=self.a.pk).last_login,value1)
        with self.assertRaises(OperationalError),connection.execute_wrapper(after_update):
            with transaction.atomic(using='auth'):
                Student.objects.using('auth').filter(pk=self.a.pk).update(last_login=timezone.now())
        self.assertEqual(Student.objects.using('default').get(pk=self.a.pk).last_login,value1)
        emit(post_execute_autocommit_persisted=True,post_execute_inside_atomic_rolled_back=True)
```

## Captured output

```text
Creating test database for alias 'default'...
......
----------------------------------------------------------------------
Ran 6 tests in 4.392s

OK
Destroying test database for alias 'default'...
Found 6 test(s).
Runtime grants and private signing key configured; no secret values printed.
Separate authentication role configured; academic runtime privileges unchanged.
System check identified no issues (0 silenced).
R4_EVIDENCE={"autocommit": true, "explicit_commit_calls": 0, "persisted": true}
R4_EVIDENCE={"cycle_calls": 1, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": false, "state": "N"}
R4_EVIDENCE={"cycle_calls": 1, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": false, "state": "AN"}
R4_EVIDENCE={"cycle_calls": 0, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": true, "state": "SA"}
R4_EVIDENCE={"cycle_calls": 0, "key_is_none": true, "rows_inside_finalizer": 0, "same_key": false, "state": "DA"}
R5_EVIDENCE={"post_execute_autocommit_persisted": true, "post_execute_inside_atomic_rolled_back": true}
R5_EVIDENCE={"CAS_persisted": true, "finalizer_rolled_back": true, "throttle_persisted": true}
R4_EVIDENCE={"new_cookie": false, "old_row_exists": true, "phase": "response save not applied", "rows": 1, "state": "SA", "status": 500}
R4_EVIDENCE={"new_cookie": false, "old_row_exists": false, "phase": "response save not applied", "rows": 0, "state": "DA", "status": 500}
R5_EVIDENCE={"cycle_calls": 0, "key_none": true, "rows_inside_finalizer": 0, "state": "SX", "writes": [["INSERT", "response"]]}
```

Six methods passed, not a rerun of the full authentication suite. The repeated R4_EVIDENCE labels are deliberately retained from the unchanged inherited module.

## Fresh-process offline/configuration observation

Run in a fresh process with the synthetic environment sourced. The NullHandler below is a **standard-library stand-in** to inspect dictConfig's graph handling; it is not a prototype B1 sanitizer or policy implementation.

```sh
PYTHONPATH=/workspace/university-command-center-pr29/server \
DJANGO_SETTINGS_MODULE=config.settings.auth_migration \
.venv/bin/python - <<'PYCODE'
import django, logging, logging.config, json
from django.conf import settings
django.setup()
print(json.dumps({
    'policy_absent': not hasattr(settings, 'UCC_LOG_PRIVACY'),
    'LOGGING_empty': not bool(settings.LOGGING),
    'django_handlers': [type(h).__name__ for h in logging.getLogger('django').handlers],
}))
raw = logging.StreamHandler()
logging.getLogger('django.security').addHandler(raw)
logging.config.dictConfig({
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'sink': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['sink'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': [], 'propagate': True},
        'django.server': {'handlers': [], 'propagate': True},
    },
})
print(json.dumps({'raw_added_before_dictConfig_survived':
                  raw in logging.getLogger('django.security').handlers}))
PYCODE
```

Observed: policy_absent=true; LOGGING_empty=true; django_handlers=[StreamHandler, AdminEmailHandler]; raw_added_before_dictConfig_survived=false. This demonstrates why a startup guard fixture must place its unsafe handler in the effective LOGGING dictionary or inject it after configuration, not assume a pre-configuration addHandler survives.

## Limits and cleanup

The proposed B1 modules do not exist. Their profile gating, classification and sink safety remain implementation acceptance requirements; documentation CI cannot demonstrate them. No new native COMMIT-duration experiment was needed; earlier PG17.11 deferred-trigger evidence is unchanged. In particular, the atomic post-execute probe above proves **rollback before COMMIT**, and must never be relabelled as an uncertain-COMMIT observation.

After the runner destroys the test database, remove only this disposable container/volume and the generated private local environment files:

```sh
docker --host=unix:///var/run/docker.sock rm -fv ucc-b1r5review-postgres
rm work/b1r5review-security.env work/b1r5review-foundation.env
```
