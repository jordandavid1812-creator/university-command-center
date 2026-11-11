"""Stage S0 read-only probes (evidence for docs/security). Synthetic identities only.

Not part of the project suites. Run per docs/security/SECURITY_TEST_MATRIX.md.
"""
import uuid
from django.core import mail
from django.db import connections, DatabaseError
from django.test import Client
from django.urls import reverse
from academics import services
from web_tests.base import WebsiteCase
from auth_tests.base import PASSWORD

MARK = '<script>ucc_s0_marker()</script>"\'><img src=x onerror=1>'


def report(name, value):
    print(f'\nPROBE {name}: {value}')


class Probes(WebsiteCase):
    def test_p01_username_enumeration_via_registration(self):
        url = reverse('accounts:register')
        data = {'email': 'fresh1@example.invalid', 'password1': 'Unrelated-Synth!77x', 'password2': 'Unrelated-Synth!77x'}
        r1 = Client(REMOTE_ADDR='10.1.0.1').post(url, {**data, 'username': 'alpha'})
        taken = len(mail.outbox); mail.outbox = []
        r2 = Client(REMOTE_ADDR='10.1.0.2').post(url, {**data, 'username': 'newname', 'email': 'fresh2@example.invalid'})
        free = len(mail.outbox)
        report('P01 register existing username -> emails', taken)
        report('P01 register new username -> emails', free)
        report('P01 same response body', r1.content == r2.content)

    def test_p02_shared_ip_lockout(self):
        attacker = Client(REMOTE_ADDR='192.0.2.10')
        for _ in range(10):
            attacker.post(reverse('accounts:login'), {'username': 'alpha', 'password': 'wrong-password-x'})
        victim = Client(REMOTE_ADDR='192.0.2.10')  # same egress/proxy address
        r = victim.post(reverse('accounts:login'), {'username': 'bravo', 'password': PASSWORD})
        report('P02 legit user B behind same IP after 10 failures by attacker', r.status_code)

    def test_p03_per_account_limit_absent(self):
        codes = set()
        for i in range(40):
            r = Client(REMOTE_ADDR=f'198.51.100.{i+1}').post(reverse('accounts:login'), {'username': 'alpha', 'password': f'wrong-{i}-xxxx'})
            codes.add(r.status_code)
        ok = Client(REMOTE_ADDR='198.51.100.250').post(reverse('accounts:login'), {'username': 'alpha', 'password': PASSWORD})
        report('P03 statuses for 40 wrong passwords from 40 IPs', sorted(codes))
        report('P03 correct password afterwards', ok.status_code)

    def test_p04_unbounded_academic_writes(self):
        self.login()
        codes = set()
        for i in range(60):
            codes.add(self.client_a.post(reverse('student_web:semester-create'), {'label': f'Synthetic {i}', 'display_order': i}).status_code)
        self.identity_a = self.identity(self.client_a)
        report('P04 60 rapid semester creations statuses', sorted(codes))
        report('P04 stored semesters', len(services.semesters.list(self.identity_a)))

    def test_p05_legacy_json_endpoint_cross_account_and_partial_update(self):
        self.seed()
        g = self.client_a.get(reverse('accounts:course', args=[self.course_b.pk]))
        p = self.client_a.post(reverse('accounts:course', args=[self.course_b.pk]), {'version': 1, 'actual_grade': 'F'})
        d = self.client_a.post(reverse('accounts:delete-assignment', args=[self.task_b.pk]), {'version': 1})
        report('P05 legacy GET/POST/DELETE foreign', (g.status_code, p.status_code, d.status_code))
        report('P05 B grade unchanged', services.courses.retrieve(self.identity_b, self.course_b.pk).actual_grade)
        own = self.client_a.post(reverse('accounts:course', args=[self.course_a.pk]), {'version': 1})
        report('P05 own POST without actual_grade -> status, grade now', (own.status_code, services.courses.retrieve(self.identity_a, self.course_a.pk).actual_grade))

    def test_p06_headers(self):
        self.seed()
        for name in ('login',):
            r = Client().get(reverse('accounts:' + name))
            report('P06 anon login headers', {k: r.headers.get(k) for k in ('X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy', 'Cross-Origin-Opener-Policy', 'Content-Security-Policy', 'Strict-Transport-Security', 'Cache-Control')})
        r = self.client_a.get(reverse('student_web:dashboard'))
        report('P06 dashboard headers', {k: r.headers.get(k) for k in ('X-Frame-Options', 'X-Content-Type-Options', 'Referrer-Policy', 'Content-Security-Policy', 'Strict-Transport-Security', 'Cache-Control')})
        report('P06 session cookie attrs', {k: v for k, v in self.client_a.cookies['sessionid'].items() if v})
        s = self.client_a.get('/static/student_web/site.css')
        report('P06 static status/nosniff', (s.status_code, s.headers.get('X-Content-Type-Options')))

    def test_p07_stored_xss_markers_escaped(self):
        self.seed()
        sem = services.semesters.create(self.identity_a, label=MARK)
        services.courses.create(self.identity_a, semester_id=sem.pk, original_code='XSS1', name=MARK, credit_units=2, actual_grade='C')
        c = services.courses.list(self.identity_a)[-1]
        services.assignments.create(self.identity_a, course_id=c.pk, title=MARK, due_date='2026-11-20')
        raw = 0
        pages = ['dashboard', 'semester-list', 'course-list', 'assignment-list', 'overview', 'predictor', 'planner']
        for name in pages:
            body = self.client_a.get(reverse('student_web:' + name)).content.decode()
            raw += body.count('<script>ucc_s0_marker') + body.count('<img src=x')
        body = self.client_a.post(reverse('student_web:predictor'), {'grade_' + c.pk.hex: 'A'}).content.decode()
        raw += body.count('<script>ucc_s0_marker')
        report('P07 unescaped marker occurrences across pages', raw)
        p = self.client_a.get(reverse('student_web:course-list'), {'page': '1', 'x': '"><script>q</script>'})
        report('P07 reflected param status / raw', (p.status_code, '<script>q' in p.content.decode()))

    def test_p08_open_redirect_and_host(self):
        r = self.login(Client(REMOTE_ADDR='10.9.9.9'))
        c = Client(REMOTE_ADDR='10.9.9.8')
        r2 = c.post(reverse('accounts:login') + '?next=https://evil.example/', {'username': 'alpha', 'password': PASSWORD})
        report('P08 login redirect target with next=', r2.headers.get('Location'))
        h = Client(HTTP_HOST='evil.example').get(reverse('accounts:login'))
        report('P08 foreign Host header status', h.status_code)

    def test_p09_db_privileges_as_real_logins(self):
        out = {}
        with connections['runtime'].cursor() as cur:
            for label, sql in {
                'runtime select accounts_student': 'SELECT count(*) FROM accounts_student',
                'runtime select django_session': 'SELECT count(*) FROM django_session',
                'runtime read context_key': 'SELECT count(*) FROM ucc_security.context_key',
                'runtime call ucc_crypto.hmac': "SELECT ucc_crypto.hmac('a'::bytea,'b'::bytea,'sha256')",
                'runtime update owner_id': 'UPDATE academics_semester SET owner_id = owner_id',
                'runtime create temp table': 'CREATE TEMP TABLE s0x(i int)',
                'runtime create table public': 'CREATE TABLE public.s0x(i int)',
                'runtime set role migrator': 'SET ROLE ucc_migrator_ci',
                'runtime create large object': 'SELECT lo_from_bytea(0, \'x\'::bytea)',
            }.items():
                try:
                    with connections['runtime'].cursor() as c2:
                        c2.execute(sql)
                        out[label] = 'ALLOWED'
                except DatabaseError as e:
                    out[label] = 'denied:' + type(e.__cause__).__name__
            cur.execute("SELECT set_config('ucc.student_id', %s, false)", [str(self.a.pk)])
            cur.execute('SELECT count(*) FROM academics_semester')
            out['runtime forged unsigned GUC visible rows'] = cur.fetchone()[0]
            cur.execute("SELECT has_database_privilege(current_user,'postgres','CONNECT'), has_database_privilege(current_user,'postgres','TEMP')")
            out['runtime CONNECT/TEMP on postgres db'] = cur.fetchone()
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname=current_user")
        with connections['auth'].cursor() as cur:
            for label, sql in {
                'auth select academics_course': 'SELECT count(*) FROM academics_course',
                'auth update is_active': 'UPDATE accounts_student SET is_active = is_active',
                'auth update email': 'UPDATE accounts_student SET email = email',
                'auth exec current_student': 'SELECT ucc_security.current_student()',
            }.items():
                try:
                    cur.execute(sql); out[label] = 'ALLOWED'
                except DatabaseError as e:
                    out[label] = 'denied:' + type(e.__cause__).__name__
            cur.execute("SELECT has_column_privilege(current_user,'accounts_student','is_active','INSERT'), has_column_privilege(current_user,'accounts_student','email_verified_at','INSERT')")
            out['auth INSERT is_active/email_verified_at columns'] = cur.fetchone()
        with connections['default'].cursor() as cur:
            cur.execute("SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, (SELECT count(*) FROM pg_policies p WHERE p.tablename=c.relname) FROM pg_class c WHERE relname IN ('academics_semester','academics_course','academics_assignment') ORDER BY 1")
            out['RLS (table, enabled, forced, policies)'] = cur.fetchall()
            cur.execute("SELECT tablename, policyname, permissive, roles::text, cmd FROM pg_policies ORDER BY 1")
            out['all policies'] = cur.fetchall()
            cur.execute("SELECT p.proname, p.prosecdef, p.proconfig, pg_get_userbyid(p.proowner)=current_user, p.proacl::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='ucc_security'")
            out['ucc_security functions'] = cur.fetchall()
            cur.execute("SELECT r.rolname, r.rolsuper, r.rolbypassrls, r.rolinherit, r.rolcreatedb, r.rolcreaterole FROM pg_roles r WHERE r.rolname LIKE 'ucc_%' ORDER BY 1")
            out['ucc roles (name,super,bypassrls,inherit,createdb,createrole)'] = cur.fetchall()
            cur.execute("SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants WHERE grantee='PUBLIC' AND table_schema IN ('public','ucc_security')")
            out['PUBLIC table grants'] = cur.fetchall()
        for k, v in out.items():
            report('P09 ' + k, v)
