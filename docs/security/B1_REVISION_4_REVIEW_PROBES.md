# B1 Revision 4 independent observation appendix

Companion to [the review](B1_REVISION_4_INDEPENDENT_REVIEW.md). These are observation probes of existing Django/PR #29 behavior, **not B1 implementations**. Synthetic students only; PostgreSQL 17.11, Django 5.2.19, psycopg 3.3.8, Python 3.12.14. No SQLite. No credentials or actual session keys are printed or included.

## Reproduction environment

Use an isolated local checkout/worktree of `bec0a44` with its hashed Django dependencies and Docker available. That checkout's accounts/config/auth_tests files match integrated PR #29 head `42910ed`. The paths below describe the review workspace; substitute your own checkout paths. Use the existing authentication runner: it migrates the disposable test database and provisions separate auth/runtime roles. Never run these against student or staging data.

Save the following setup script as `work/setup_b1r4review.py` in an ignored local working directory. It creates a **localhost-only disposable** PostgreSQL container on port 55441 and random local credentials in mode-600 ignored files. `postgres:17` resolved to 17.11 for this run; verify `SHOW server_version` and record the resolved image version before comparing results. This image is not a deployment recommendation. The Docker socket argument is specific to this review environment.

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
subprocess.run(['docker','--host=unix:///var/run/docker.sock','run','-d','--name','ucc-b1r4review-postgres',
                '-p','127.0.0.1:55441:5432','-e','POSTGRES_PASSWORD','-e','POSTGRES_USER','-e','POSTGRES_DB','postgres:17'],env=env,check=True)
admin = dict(host='127.0.0.1', port=55441, user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], dbname=env['POSTGRES_DB'])
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
values = dict(PGHOST='127.0.0.1', PGPORT='55441', PGUSER='ucc_migrator',
              PGPASSWORD=migration_password, PGDATABASE='ucc_migration_scratch', PGTESTDATABASE='test_ucc_security',
              UCC_AUTH_ROLE='ucc_auth', UCC_AUTH_PASSWORD=auth_password, UCC_RUNTIME_ROLE='ucc_runtime', UCC_RUNTIME_PASSWORD=runtime_password,
              UCC_CONTEXT_SIGNING_KEY=secrets.token_hex(32), DJANGO_SECRET_KEY=secrets.token_urlsafe(64))
path=Path('work/b1r4review-security.env'); path.touch(mode=0o600)
path.write_text(''.join(f'export {k}={v}\n' for k,v in values.items()))
values.update(PGUSER=admin['user'], PGPASSWORD=admin['password'], PGDATABASE=admin['dbname'], PGTESTDATABASE='test_ucc_foundation')
path=Path('work/b1r4review-foundation.env'); path.touch(mode=0o600)
path.write_text(''.join(f'export {k}={v}\n' for k,v in values.items()))
```

Run setup to completion, then save the observation module below as `work/b1r4_review_probes.py` (outside tracked application paths):

```sh
.venv/bin/python work/setup_b1r4review.py
set -e
source work/b1r4review-security.env
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/workspace/university-command-center/work \
PGTESTDATABASE=test_b1r4_review \
.venv/bin/python /workspace/university-command-center-pr29/server/manage.py \
  test b1r4_review_probes --settings=config.settings.auth_test -v 1
```

## Observation module

The cycle/login patches delegate to actual Django functions. They only count calls and inspect real database rows. The response-save patch injects a Django OperationalError **before** saving; it does not simulate a real PostgreSQL timeout or COMMIT acknowledgement loss. The autocommit test executes a real INSERT and checks persistence from the independent migration connection; its `_commit` spy delegates unchanged.

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

## Captured results

```text
Creating test database for alias 'default'...
...
----------------------------------------------------------------------
Ran 3 tests in 0.614s

OK
Destroying test database for alias 'default'...
Found 3 test(s).
Runtime grants and private signing key configured; no secret values printed.
Separate authentication role configured; academic runtime privileges unchanged.
System check identified no issues (0 silenced).
R4_EVIDENCE={"autocommit": true, "explicit_commit_calls": 0, "persisted": true}
R4_EVIDENCE={"cycle_calls": 1, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": false, "state": "N"}
R4_EVIDENCE={"cycle_calls": 1, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": false, "state": "AN"}
R4_EVIDENCE={"cycle_calls": 0, "key_is_none": false, "rows_inside_finalizer": 1, "same_key": true, "state": "SA"}
R4_EVIDENCE={"cycle_calls": 0, "key_is_none": true, "rows_inside_finalizer": 0, "same_key": false, "state": "DA"}
R4_EVIDENCE={"new_cookie": false, "old_row_exists": true, "phase": "response save not applied", "rows": 1, "state": "SA", "status": 500}
R4_EVIDENCE={"new_cookie": false, "old_row_exists": false, "phase": "response save not applied", "rows": 0, "state": "DA", "status": 500}
```

Three test methods passed. Seven scenario observations: four successful login entry states, two pre-response-save failures and one implicit autocommit. Do not describe these as seven separately discovered test methods or full authentication-suite coverage.

## Offline logging and label observations

Fresh subprocess, with the privately generated synthetic environment sourced as above:

```sh
PYTHONPATH=/workspace/university-command-center-pr29/server \
DJANGO_SETTINGS_MODULE=config.settings.auth_migration \
.venv/bin/python - <<'PYCODE'
import django, logging, re, json
from django.apps import apps
from django.conf import settings
django.setup()
from django.db.utils import Error
marker = 'SYNTHETIC_SESSION_SENTINEL'
record = logging.LogRecord('accounts.' + marker, logging.ERROR, '', 0, 'discard', (), None)
exception = type(marker, (Error,), {})()
print(json.dumps({
    'accounts_installed': apps.is_installed('accounts'),
    'LOGGING_empty': not bool(settings.LOGGING),
    'django_handlers': [type(h).__name__ for h in logging.getLogger('django').handlers],
    'sentinel_logger_name_passes': bool(re.fullmatch(r'[A-Za-z0-9_.]{1,100}', record.name)),
    'sentinel_exception_name_passes': bool(re.fullmatch(r'[A-Za-z0-9_.]{1,64}', type(exception).__qualname__)),
}, sort_keys=True))
PYCODE
```

Observed: accounts_installed=true, LOGGING_empty=true, django_handlers=[StreamHandler, AdminEmailHandler]; both sentinel-name checks=true. No proposed guard or sanitizer was implemented. The guard incompatibility follows directly from applying the plan's stated rejection predicate to this actual graph. The regex observation shows syntax does not establish label provenance; it does not show that students control these names in current code.

## Limits and cleanup

No new COMMIT-duration experiment was necessary: the original PG17.11 native deferred-trigger COMMIT experiment remains in PR #37. No proposed classifier, renderer or sanitizer exists to execute. Their algorithm and fallback rules were reviewed against installed framework sources; implementation CI must test them. Do not treat these observations as hosted B1 regression tests.

After the run, the runner destroyed its test database. Remove this disposable container and associated anonymous volume, then the two private environment files; do not remove shared infrastructure or print file contents:

```sh
docker --host=unix:///var/run/docker.sock rm -fv ucc-b1r4review-postgres
rm work/b1r4review-security.env work/b1r4review-foundation.env
```
