"""Launch step F: ucc_security.delete_my_account() removes exactly the signed student's account and
every row of theirs, in one transaction, and nothing of anyone else's. Synthetic data, real PostgreSQL."""
import hashlib
import uuid
from datetime import date, time, timedelta
from django.db import DatabaseError, connections, transaction
from django.utils import timezone
from academics import services
from academics.ownership import OwnershipRequired
from academics.services import (ai, class_sessions, delete_account, materials, profiles, search_texts, study_plans)
from accounts.models import Student
from .base import StudentSecurityCase

# Every table that refers to accounts_student, and its column. The test below checks this list
# against the database's own foreign keys, so a new table cannot be forgotten.
OWNED = {
    'academics_semester': 'owner_id', 'academics_course': 'owner_id', 'academics_assignment': 'owner_id',
    'academics_studymaterial': 'owner_id', 'academics_materialfile': 'owner_id', 'academics_materialtext': 'owner_id',
    'academics_studentprofile': 'owner_id', 'academics_studyairequest': 'owner_id',
    'academics_studyairesult': 'owner_id', 'academics_classsession': 'owner_id', 'academics_studyplan': 'owner_id',
    'academics_studytopic': 'owner_id', 'accounts_accounttoken': 'student_id', 'accounts_trusteddevice': 'student_id',
    'accounts_devicegeneration': 'student_id', 'accounts_signupcode': 'student_id',
}


def hexdigest(label):
    return hashlib.sha256(label.encode()).hexdigest()


class AccountDeletionTests(StudentSecurityCase):
    def setUp(self):
        super().setUp()
        for who, identity, course in (('a', self.a, self.course_a), ('b', self.b, self.course_b)):
            material = materials.create_with_file(identity, title=f'{who} notes', course_id=course.pk,
                                                  original_filename='notes.txt', file_type='txt',
                                                  content=f'Synthetic {who} notes'.encode())
            search_texts.save(identity, material.pk, text=f'Synthetic {who} notes')
            profiles.create(identity, display_name=f'Synthetic {who.upper()}')
            class_sessions.create(identity, course_id=course.pk, weekday=0, start_time=time(8), end_time=time(10),
                                  kind='lecture', venue='LT1')
            study_plans.create_with_topics(identity, course_id=course.pk, exam_date=date(2026, 12, 20), review_days=0,
                                           topics=[('Synthetic topic', date(2026, 12, 1))])
            request, _ = ai.reserve(identity, tool='summary', provider='gemini', model='synthetic-model-1',
                                    characters_sent=20, truncated=False, consent_token_hash=hexdigest(who))
            ai.succeed(identity, request.pk, material_id=material.pk, result={'points': ['Synthetic point']})
            self.account_rows(getattr(self, f'student_{who}').pk, who)

    def account_rows(self, student_id, label):
        now = timezone.now()
        with connections['default'].cursor() as cursor:
            cursor.execute("""INSERT INTO accounts_accounttoken (id, purpose, digest, credential_stamp, email_at_issue,
                              created_at, expires_at, student_id) VALUES (%s, 'reset', %s, 'stamp', %s, %s, %s, %s)""",
                           [uuid.uuid4(), hexdigest('token' + label), f'{label}@example.invalid', now,
                            now + timedelta(hours=1), student_id])
            cursor.execute("""INSERT INTO accounts_trusteddevice (id, current_digest, created_at, last_used_at,
                              expires_at, student_id) VALUES (%s, %s, %s, %s, %s, %s)""",
                           [uuid.uuid4(), hexdigest('device' + label), now, now, now + timedelta(days=1), student_id])
            cursor.execute('INSERT INTO accounts_devicegeneration (student_id, generation) VALUES (%s, 1)', [student_id])
            cursor.execute("""INSERT INTO accounts_signupcode (id, digest, created_at, expires_at, attempts, student_id)
                              VALUES (%s, %s, %s, %s, 0, %s)""",
                           [uuid.uuid4(), hexdigest('code' + label), now, now + timedelta(minutes=1), student_id])

    def counts(self, student_id):
        """Real rows per table for one student. Row-level security is forced even on the table owner,
        so the migration login lifts the forcing inside a transaction that is always rolled back."""
        result = {}
        with transaction.atomic(using='default'):
            with connections['default'].cursor() as cursor:
                for table, column in OWNED.items():
                    if table.startswith('academics_'):
                        cursor.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')  # nosec B608
                    cursor.execute(f'SELECT count(*) FROM {table} WHERE {column} = %s', [student_id])  # nosec B608
                    result[table] = cursor.fetchone()[0]
                cursor.execute('SELECT count(*) FROM accounts_student WHERE id = %s', [student_id])
                result['accounts_student'] = cursor.fetchone()[0]
            transaction.set_rollback(True, using='default')
        return result

    def test_every_table_that_refers_to_a_student_is_handled(self):
        with connections['default'].cursor() as cursor:
            cursor.execute("""SELECT c.conrelid::regclass::text, a.attname
                FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                WHERE c.contype = 'f' AND c.confrelid = 'public.accounts_student'::regclass""")
            found = {table.split('.')[-1].strip('"'): column for table, column in cursor.fetchall()}
            cursor.execute("""SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                              WHERE n.nspname = 'ucc_security' AND p.proname = 'delete_my_account'""")
            source = cursor.fetchone()[0]
        self.assertEqual(found, OWNED)
        for table, column in OWNED.items():
            self.assertIn(f'DELETE FROM public.{table} WHERE {column} = me;', source)

    def test_deleting_removes_everything_of_the_student_and_nothing_else(self):
        a_before, b_before = self.counts(self.student_a.pk), self.counts(self.student_b.pk)
        self.assertTrue(all(count >= 1 for count in a_before.values()), a_before)
        self.assertTrue(delete_account(self.a))
        after = self.counts(self.student_a.pk)
        self.assertEqual(set(after.values()), {0}, after)
        self.assertEqual(self.counts(self.student_b.pk), b_before)
        self.assertFalse(Student.objects.filter(pk=self.student_a.pk).exists())

    def test_the_deleted_identity_can_do_nothing_afterwards(self):
        delete_account(self.a)
        with self.assertRaises(OwnershipRequired):
            services.semesters.list(self.a)  # its signed context no longer names a student
        with self.assertRaises(OwnershipRequired):
            delete_account(self.a)

    def test_the_function_refuses_without_a_signed_student(self):
        with self.assertRaises(DatabaseError), connections['runtime'].cursor() as cursor:
            cursor.execute('SELECT ucc_security.delete_my_account()')
        self.assertEqual(self.counts(self.student_a.pk)['accounts_student'], 1)

    def test_only_the_website_login_may_call_it_and_it_runs_with_a_fixed_search_path(self):
        runtime = connections['runtime'].settings_dict['USER']
        with connections['default'].cursor() as cursor:
            cursor.execute("""SELECT p.prosecdef, p.proconfig, p.pronargs,
                    has_function_privilege(%s, p.oid, 'EXECUTE'),
                    EXISTS (SELECT 1 FROM aclexplode(p.proacl) WHERE grantee = 0 AND privilege_type = 'EXECUTE')
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'ucc_security' AND p.proname = 'delete_my_account'""", [runtime])
            definer, config, arguments, runtime_may, public_may = cursor.fetchone()
        self.assertTrue(definer)
        self.assertIn('search_path=pg_catalog', config)
        self.assertEqual(arguments, 0)  # it cannot be told which student to delete
        self.assertTrue(runtime_may)
        self.assertFalse(public_may)

    def test_the_ledger_still_cannot_be_deleted_directly(self):
        with self.assertRaises(DatabaseError), connections['runtime'].cursor() as cursor:
            cursor.execute('DELETE FROM academics_studyairequest')
