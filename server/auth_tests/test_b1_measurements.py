"""Evidence only: actual PBKDF2 work under Student locks; no timing SLA assertion.

Reported separately (L-6B):
* hash_calls_under_lock: PBKDF2 encode calls made while the Student row lock is held;
* lock_hold_seconds: lock acquisition (statement return) to real COMMIT return;
* observer_overhead_seconds: the part of that hold spent waiting for the NOWAIT
  observer handshake that proves the lock exists (test coordination, not app work);
* lock_hold_excluding_observer_seconds: the difference. It still includes thread
  scheduling and other non-hash work, so it is an upper bound on hashing time.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import platform
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from django.contrib.auth.hashers import PBKDF2PasswordHasher, make_password
from django.core import mail
from django.db import connections, transaction, DatabaseError
from django.test import Client, override_settings
from django.urls import reverse
from accounts import views
from accounts.models import Student
from .base import AuthenticationCase, PASSWORD, NEW_PASSWORD
from .test_b1_database import thread_call


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'])
class HashLockMeasurements(AuthenticationCase):
    def test_real_pbkdf2_lock_duration_login_change_reset(self):
        records=[]
        for flow in ('login_recheck','password_change','reset_confirm'):
            client=Client(REMOTE_ADDR='10.63.0.1')
            if flow=='password_change':self.assertEqual(self.login(client).status_code,302)
            if flow=='reset_confirm':
                self.client.post(reverse('accounts:reset'),{'email':'alpha@example.invalid'})
                path=urlsplit(mail.outbox[-1].body.splitlines()[0]).path
            ready=Event();observed=Event();state={'pid':None,'hashes':0}
            def worker():
                conn=connections['auth']
                with conn.cursor() as c:c.execute('SELECT pg_backend_pid()');state['pid']=c.fetchone()[0]
                real_hash=PBKDF2PasswordHasher.encode
                real_commit=conn._commit
                def encode(hasher,*args,**kwargs):
                    if state.get('locked_at') is not None:state['hashes']+=1
                    return real_hash(hasher,*args,**kwargs)
                def inspect(execute,sql,params,many,context):
                    if flow=='login_recheck' and 'FOR UPDATE' in sql and 'accounts_student' in sql:
                        # Fixture-only second connection commits a different salt for
                        # the same secret after verification, before the real lock.
                        Student.objects.using('default').filter(pk=self.a.pk).update(password=make_password(PASSWORD))
                    result=execute(sql,params,many,context)
                    if 'FOR UPDATE' in sql and 'accounts_student' in sql and state.get('locked_at') is None:
                        state['locked_at']=time.monotonic();ready.set()
                        if not observed.wait(10):raise AssertionError('Real row-lock observer did not run')
                        state['observer_seconds']=time.monotonic()-state['locked_at']
                    return result
                def commit():
                    result=real_commit()
                    if state.get('locked_at') is not None and 'seconds' not in state:
                        state['seconds']=time.monotonic()-state['locked_at']
                    return result
                with conn.execute_wrapper(inspect),patch.object(conn,'_commit',commit),patch.object(PBKDF2PasswordHasher,'encode',encode):
                    if flow=='login_recheck':return self.login(client).status_code
                    if flow=='password_change':return client.post(reverse('accounts:password-change'),{'old_password':PASSWORD,'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD}).status_code
                    return client.post(path,{'new_password1':PASSWORD,'new_password2':PASSWORD}).status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(thread_call(worker))
                self.assertTrue(ready.wait(20))
                from .test_b1_database import sqlstate
                with self.assertRaises(DatabaseError) as error:
                    with transaction.atomic(using='default'):
                        Student.objects.using('default').select_for_update(nowait=True).get(pk=self.a.pk)
                self.assertEqual(sqlstate(error.exception),'55P03')
                observed.set();status=future.result(timeout=60)
            self.assertEqual(status,200 if flow=='reset_confirm' else 302)
            self.assertIn('seconds',state);self.assertIn('observer_seconds',state)
            self.assertGreaterEqual(state['hashes'],1)
            self.assertLessEqual(state['observer_seconds'],state['seconds'])
            records.append({'flow':flow,'hash_calls_under_lock':state['hashes'],
                            'lock_hold_seconds':round(state['seconds'],6),
                            'observer_overhead_seconds':round(state['observer_seconds'],6),
                            'lock_hold_excluding_observer_seconds':round(state['seconds']-state['observer_seconds'],6),
                            'algorithm':'pbkdf2_sha256','iterations':PBKDF2PasswordHasher.iterations,
                            'python':platform.python_version(),'postgresql':connections['auth'].pg_version})
        print('B1A_PBKDF2_LOCK_MEASUREMENTS='+json.dumps(records,sort_keys=True))
