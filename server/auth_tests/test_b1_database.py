"""Real PostgreSQL B1a timers, per-unit persistence and cleanup; synthetic only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
import os
import socket
from threading import Event, Thread
import time
from unittest.mock import patch
import psycopg
from django.conf import settings
from django.core.management import call_command
from django.db import connections, transaction, DatabaseError, OperationalError
from django.test import Client, override_settings
from django.utils import timezone
from accounts.models import Student, AuthThrottle
from accounts.boundary import require_auth_role
from academics.ownership import require_runtime_role
from .base import AuthenticationCase, PASSWORD
from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password


def sqlstate(exc):
    seen=set()
    while exc and id(exc) not in seen:
        seen.add(id(exc))
        if getattr(exc,'sqlstate',None):return exc.sqlstate
        exc=exc.__cause__ or exc.__context__
    return None


def thread_call(function):
    def run():
        try:return function()
        finally:connections.close_all()
    return run


class DatabaseTimerTests(AuthenticationCase):
    def observe(self, query, params=()):
        # Real fresh auth LOGIN; never use migrator to assert request authority.
        with psycopg.connect(**connections['auth'].get_connection_params(), autocommit=True) as conn:
            return conn.execute(query,params).fetchall()

    def weak_hash(self):
        h=PBKDF2PasswordHasher()
        encoded=h.encode(PASSWORD,h.salt(),iterations=1000)
        Student.objects.using('default').filter(pk=self.a.pk).update(password=encoded)
        return encoded

    def test_show_on_fresh_reused_direct_connections_and_excluded_migrator(self):
        for alias, statement in [('auth','5s'),('runtime','10s')]:
            connections[alias].close()
            for _ in range(2):
                with connections[alias].cursor() as c:
                    c.execute('SHOW lock_timeout');self.assertEqual(c.fetchone()[0],'3s')
                    c.execute('SHOW statement_timeout');self.assertEqual(c.fetchone()[0],statement)
                    c.execute('SHOW idle_in_transaction_session_timeout');self.assertEqual(c.fetchone()[0],'15s')
            with psycopg.connect(**connections[alias].get_connection_params()) as conn:
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0],statement)
        self.assertNotIn('options',settings.DATABASES['default']['OPTIONS'])
        with connections['default'].cursor() as c:
            c.execute('SHOW statement_timeout');self.assertEqual(c.fetchone()[0],'0')

    def test_statement_timeout_on_both_actual_restricted_roles(self):
        for alias, seconds in [('auth',6),('runtime',11)]:
            with self.subTest(alias=alias), self.assertRaises(DatabaseError) as error:
                with connections[alias].cursor() as c:c.execute('SELECT pg_sleep(%s)',[seconds])
            self.assertEqual(sqlstate(error.exception),'57014')
            with connections[alias].cursor() as c:c.execute('SELECT 1');self.assertEqual(c.fetchone(),(1,))

    def test_idle_transaction_timeout_terminates_then_reconnects(self):
        conn=connections['auth']
        try:
            with conn.cursor() as c:c.execute('BEGIN');c.execute('SELECT 1')
            time.sleep(15.3)  # Deliberately create an idle gap, not a retry/delay workaround.
            with self.assertRaises(DatabaseError) as error:
                with conn.cursor() as c:c.execute('SELECT 1')
            self.assertEqual(sqlstate(error.exception),'25P03')
        finally:conn.close()
        with conn.cursor() as c:c.execute('SELECT 1');self.assertEqual(c.fetchone(),(1,))

    def test_connect_timeout_with_a_single_stalled_handshake(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        stop=Event();accepted=Event()
        def stall():
            client=None
            try:
                listener.settimeout(10);client,_=listener.accept();accepted.set();stop.wait(10)
            finally:
                if client:client.close()
        worker=Thread(target=stall,daemon=True);worker.start();start=time.monotonic()
        try:
            with self.assertRaises(psycopg.OperationalError):
                psycopg.connect(host='127.0.0.1',port=listener.getsockname()[1],
                                user='synthetic',dbname='synthetic',connect_timeout=5,sslmode='disable')
            self.assertTrue(accepted.is_set())
            self.assertGreaterEqual(time.monotonic()-start,4)
            self.assertLess(time.monotonic()-start,20)
        finally:stop.set();listener.close();worker.join(12)

    def test_cleanup_timeout_rolls_back_delete_call_and_reports_failure(self):
        now=timezone.now()
        AuthThrottle.objects.using('auth').create(bucket='a'*64,attempts=1,expires_at=now-timedelta(days=1))
        before=self.observe('SELECT bucket,attempts,expires_at FROM accounts_auththrottle')
        ready=Event(); backend=[]
        def cleanup():
            with connections["auth"].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()");backend.append(cursor.fetchone()[0]);ready.set()
            out=StringIO()
            try:
                call_command('clear_auth_artifacts',stdout=out)
                return None,out.getvalue()
            except DatabaseError as exc:return sqlstate(exc),out.getvalue()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                AuthThrottle.objects.using('default').select_for_update().get(bucket='a'*64)
                future=pool.submit(thread_call(cleanup))
                self.assertTrue(ready.wait(5))
                deadline=time.monotonic()+2
                blocked=False
                while time.monotonic()<deadline:
                    with connections['default'].cursor() as cursor:
                        cursor.execute('SELECT cardinality(pg_blocking_pids(%s)) > 0',[backend[0]])
                        blocked=cursor.fetchone()[0]
                    if blocked:break
                    time.sleep(.01)
                self.assertTrue(blocked,'Actual cleanup backend was not observed blocked')
                code,output=future.result(timeout=15)
        self.assertEqual(code,'55P03');self.assertNotIn('Expired authentication artifacts removed',output)
        self.assertEqual(self.observe('SELECT bucket,attempts,expires_at FROM accounts_auththrottle'),before)
        require_auth_role();require_runtime_role(connections['runtime'])
        out=StringIO();call_command('clear_auth_artifacts',stdout=out)
        self.assertIn('Expired authentication artifacts removed',out.getvalue())
        self.assertEqual(self.observe('SELECT count(*) FROM accounts_auththrottle'),[(0,)])

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher',
                                        'django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_autocommit_throttle_and_cas_survive_finalizer_lock_timeout(self):
        weak=self.weak_hash();cas_done=Event();locked=Event()
        client=Client(raise_request_exception=False,REMOTE_ADDR='10.61.0.1')
        def login():
            conn=connections['auth']
            def pause(execute,sql,params,many,context):
                result=execute(sql,params,many,context)
                if sql.startswith('UPDATE "accounts_student"') and '"password"' in sql:
                    cas_done.set()
                    if not locked.wait(10):raise AssertionError('Finalizer blocker was not scheduled')
                return result
            with conn.execute_wrapper(pause), patch.object(conn,'_commit',wraps=conn._commit) as commit:
                status=self.login(client).status_code
                return status,commit.call_count
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(thread_call(login))
            self.assertTrue(cas_done.wait(10),'Login did not execute the actual old-hash CAS')
            with transaction.atomic(using='default'):
                Student.objects.using('default').select_for_update().get(pk=self.a.pk)
                locked.set()
                status,commits=future.result(timeout=15)
        self.assertEqual(status,500);self.assertEqual(commits,0)
        saved=self.observe('SELECT password FROM accounts_student WHERE id=%s',[self.a.pk])[0][0]
        self.assertNotEqual(saved,weak);self.assertTrue(check_password(PASSWORD,saved))
        self.assertEqual(self.observe('SELECT attempts FROM accounts_auththrottle'),[(1,)])
        self.assertNotIn('sessionid',client.cookies)

    def test_timed_out_throttle_does_not_increment_or_retry(self):
        client=Client(raise_request_exception=False,REMOTE_ADDR='10.61.0.2')
        self.assertEqual(self.login(client,password='synthetic-wrong').status_code,200)
        row=AuthThrottle.objects.using('default').get()
        def login():
            sent=[]
            def inspect(execute,sql,params,many,context):
                if 'INSERT INTO accounts_auththrottle' in sql:sent.append(1)
                return execute(sql,params,many,context)
            with connections['auth'].execute_wrapper(inspect):status=self.login(client).status_code
            return status,len(sent)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic(using='default'):
                AuthThrottle.objects.using('default').select_for_update().get(pk=row.pk)
                self.assertEqual(pool.submit(thread_call(login)).result(timeout=15),(500,1))
        self.assertEqual(self.observe('SELECT attempts FROM accounts_auththrottle WHERE bucket=%s',[row.pk]),[(1,)])

    def test_explicit_rollback_and_real_commit_then_lost_ack_are_distinct(self):
        conn=connections['auth']; original=self.a.last_login
        def before():raise OperationalError('synthetic pre-commit')
        with patch.object(conn,'_commit',before),self.assertRaises(OperationalError):
            with transaction.atomic(using='auth'):
                Student.objects.using('auth').filter(pk=self.a.pk).update(last_login=timezone.now())
        self.assertEqual(self.observe('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk]),[(original,)])
        committed=timezone.now();real=conn._commit
        def after():real();raise OperationalError('synthetic post-commit acknowledgement loss')
        with patch.object(conn,'_commit',after),self.assertRaises(OperationalError):
            with transaction.atomic(using='auth'):
                Student.objects.using('auth').filter(pk=self.a.pk).update(last_login=committed)
        self.assertEqual(self.observe('SELECT last_login FROM accounts_student WHERE id=%s',[self.a.pk]),[(committed,)])

    def test_autocommit_post_execute_error_does_not_undo_throttle(self):
        sent=[]
        def fault(execute,sql,params,many,context):
            result=execute(sql,params,many,context)
            if 'INSERT INTO accounts_auththrottle' in sql:
                sent.append(1);raise OperationalError('synthetic post-execute acknowledgement loss')
            return result
        client=Client(raise_request_exception=False,REMOTE_ADDR='10.61.0.3')
        with connections['auth'].execute_wrapper(fault):self.assertEqual(self.login(client).status_code,500)
        self.assertEqual(len(sent),1)
        self.assertEqual(self.observe('SELECT attempts FROM accounts_auththrottle'),[(1,)])

    def test_statement_timeout_does_not_bound_deferred_commit_work(self):
        # Temporary test schema/trigger created only by fixture migrator; real auth
        # INSERT/COMMIT executes under its existing configured connection limits.
        with connections['default'].cursor() as c:
            c.execute('CREATE TABLE b1_commit_probe (id integer)')
            c.execute("CREATE FUNCTION b1_commit_sleep() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(0.2); RETURN NEW; END $$")
            c.execute('CREATE CONSTRAINT TRIGGER b1_deferred AFTER INSERT ON b1_commit_probe DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b1_commit_sleep()')
            from psycopg import sql
            c.execute(sql.SQL('GRANT INSERT ON b1_commit_probe TO {}').format(sql.Identifier(os.environ['UCC_AUTH_ROLE'])))
        try:
            with connections['auth'].cursor() as c:c.execute("SET statement_timeout='100ms'")
            with transaction.atomic(using='auth'):
                with connections['auth'].cursor() as c:c.execute('INSERT INTO b1_commit_probe VALUES (1)')
            with connections['default'].cursor() as c:c.execute('SELECT count(*) FROM b1_commit_probe');self.assertEqual(c.fetchone(),(1,))
        finally:
            connections['auth'].close()
            with connections['default'].cursor() as c:
                c.execute('DROP TABLE b1_commit_probe');c.execute('DROP FUNCTION b1_commit_sleep()')
