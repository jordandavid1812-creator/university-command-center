from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
import uuid
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.models import Session
from django.db import connections, DatabaseError, transaction
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from accounts.backends import StudentBackend
from accounts.models import Student
from accounts.principals import principal_for_request, VerifiedSessionPrincipal
from academics.ownership import (OwnershipRequired, TrustedStudent, identity_for_verified_student,
                                 require_identity, signature)
from academics.services import assignments, courses
from .base import AuthenticationCase


class AuthenticationIsolationTests(AuthenticationCase):
    def test_unauthenticated_requests_are_denied(self):
        for name, args in (('academic', []), ('course', [uuid.uuid4()]), ('delete-assignment', [uuid.uuid4()])):
            request = self.client.get if name != 'delete-assignment' else self.client.post
            response = request(reverse('accounts:' + name, args=args), {'version': 1})
            self.assertRedirects(response, reverse('accounts:login'), fetch_redirect_response=False)

    def test_persisted_or_forged_model_instance_cannot_mint_capabilities(self):
        for student in (self.a, Student(id=self.a.pk), StudentBackend().get_user(self.a.pk)):
            with self.assertRaises(OwnershipRequired):
                identity_for_verified_student(student)
        forged = Student(id=self.b.pk, is_active=True)
        forged._state.adding = False
        forged._state.db = 'auth'
        with self.assertRaises(OwnershipRequired):
            identity_for_verified_student(forged)

    def test_constructed_request_user_cannot_override_session_owner(self):
        self.login()
        request = RequestFactory().get('/')
        request.session = self.client_a.session
        request.user = self.b
        with self.assertRaises(OwnershipRequired):
            principal_for_request(request)

    def test_forged_principal_and_direct_service_invocation_are_rejected(self):
        self.seed()
        principal = VerifiedSessionPrincipal(self.b.pk, self.client_a.session.session_key,
                                              self.a.get_session_auth_hash(), self.identity_a.expires_at, '0' * 64)
        with self.assertRaises(OwnershipRequired):
            identity_for_verified_student(principal)
        for value in (self.a, self.a.pk, None, str(self.a.pk),
                      replace(self.identity_a, student_id=self.b.pk),
                      replace(self.identity_a, session_key=self.client_b.session.session_key),
                      replace(self.identity_a, auth_hash='é' * 64)):
            with self.assertRaises(OwnershipRequired):
                courses.list(value)
        old_style = TrustedStudent(self.a.pk, self.identity_a.expires_at,
                                   signature(f'identity|{self.a.pk}|{self.identity_a.expires_at}'))
        with self.assertRaises(OwnershipRequired):
            courses.list(old_style)

    def test_cross_student_read_grade_update_and_assignment_delete_are_denied(self):
        self.seed()
        foreign = reverse('accounts:course', args=[self.course_b.pk])
        missing = reverse('accounts:course', args=[uuid.uuid4()])
        self.assertEqual(self.client_a.get(foreign).json(), self.client_a.get(missing).json())
        self.assertEqual(self.client_a.get(foreign).status_code, 404)
        self.assertEqual(self.client_a.post(foreign, {'version': 1, 'actual_grade': 'F'}).status_code, 404)
        response = self.client_a.post(reverse('accounts:delete-assignment', args=[self.task_b.pk]), {'version': 1})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(courses.retrieve(self.identity_b, self.course_b.pk).actual_grade, 'A')
        self.assertEqual(assignments.retrieve(self.identity_b, self.task_b.pk).title, 'Synthetic B task')

    def test_request_owner_fields_are_never_accepted(self):
        self.seed()
        path = reverse('accounts:course', args=[self.course_a.pk])
        response = self.client_a.post(path, {'version': 1, 'actual_grade': 'F', 'owner_id': str(self.b.pk)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_a.get(path + '?owner_id=' + str(self.b.pk)).json()['name'], 'Synthetic A course')
        self.assertEqual(courses.retrieve(self.identity_a, self.course_a.pk).actual_grade, 'B')

    def test_own_records_use_existing_version_checked_services(self):
        self.seed()
        path = reverse('accounts:course', args=[self.course_a.pk])
        response = self.client_a.post(path, {'version': 1, 'actual_grade': 'F'})
        self.assertEqual((response.status_code, response.json()['record_version']), (200, 2))
        self.assertEqual(self.client_a.post(path, {'version': 1, 'actual_grade': 'A'}).status_code, 409)
        self.assertEqual(self.client_a.post(reverse('accounts:delete-assignment', args=[self.task_a.pk]), {'version': 1}).status_code, 204)

    def test_modified_session_user_id_cannot_become_another_student(self):
        self.seed()
        session = self.client_a.session
        session[SESSION_KEY] = str(self.b.pk)
        session.save()  # Even a correctly encoded server row with mismatched password hash is invalid.
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        with self.assertRaises(OwnershipRequired):
            courses.list(self.identity_a)

    def test_wrong_session_backend_and_hash_are_rejected(self):
        self.login()
        session = self.client_a.session
        session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
        session.save()
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        self.login()
        session = self.client_a.session
        session[HASH_SESSION_KEY] = 'forged'
        session.save()
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)

    def test_tampered_session_data_and_random_cookie_fail_closed(self):
        self.login()
        key = self.client_a.session.session_key
        Session.objects.using('default').filter(session_key=key).update(session_data='unsigned-attacker-data')
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        self.client_a.cookies['sessionid'] = 'x' * 32
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)

    def test_deactivated_or_unverified_account_loses_access_and_capability(self):
        self.seed()
        key = self.client_a.session.session_key
        Student.objects.using('default').filter(pk=self.a.pk).update(is_active=False)
        self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        self.assertFalse(Session.objects.using('auth').filter(session_key=key).exists())
        with self.assertRaises(OwnershipRequired):
            courses.list(self.identity_a)
        Student.objects.using('default').filter(pk=self.b.pk).update(email_verified_at=None)
        self.assertEqual(self.client_b.get(reverse('accounts:academic')).status_code, 302)
        with self.assertRaises(OwnershipRequired):
            courses.list(self.identity_b)

    def test_logout_revokes_already_minted_capability(self):
        self.seed()
        self.client_a.post(reverse('accounts:logout'))
        with self.assertRaises(OwnershipRequired):
            courses.list(self.identity_a)

    def test_web_operations_never_query_migration_connection(self):
        self.seed()
        with CaptureQueriesContext(connections['default']) as captured:
            self.client_a.get(reverse('accounts:academic'))
            self.client_a.post(reverse('accounts:course', args=[self.course_a.pk]), {'version': 1, 'actual_grade': 'A'})
            self.client_a.post(reverse('accounts:reset'), {'email': 'alpha@example.invalid'})
        self.assertEqual(len(captured), 0)

    def test_academic_context_does_not_leak_across_requests(self):
        self.seed()
        for client, own_name, foreign_name in ((self.client_a, 'Synthetic A course', 'Synthetic B course'),
                                                (self.client_b, 'Synthetic B course', 'Synthetic A course')) * 2:
            response = client.get(reverse('accounts:academic'))
            self.assertContains(response, own_name)
            self.assertNotContains(response, foreign_name)
            with connections['runtime'].cursor() as cursor:
                cursor.execute('SELECT ucc_security.current_student()')
                self.assertEqual(cursor.fetchone(), (None,))
                cursor.execute('SELECT id FROM academics_course')
                self.assertEqual(cursor.fetchall(), [])

    def test_concurrent_student_sessions_keep_their_own_records(self):
        self.seed()
        cookies = (self.client_a.cookies['sessionid'].value, self.client_b.cookies['sessionid'].value)
        def retrieve(cookie):
            try:
                client = Client()
                client.cookies['sessionid'] = cookie
                response = client.get(reverse('accounts:academic'))
                return response.status_code, response.content.decode()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(retrieve, cookies))
        for index, (status, text) in enumerate(results):
            self.assertEqual(status, 200)
            self.assertIn('Synthetic ' + ('A' if index == 0 else 'B') + ' course', text)
            self.assertNotIn('Synthetic ' + ('B' if index == 0 else 'A') + ' course', text)

    def test_csrf_is_required_for_academic_changes(self):
        self.seed()
        client = Client(enforce_csrf_checks=True)
        client.cookies['sessionid'] = self.client_a.cookies['sessionid'].value
        self.assertEqual(client.post(reverse('accounts:course', args=[self.course_a.pk]),
                                     {'version': 1, 'actual_grade': 'F'}).status_code, 403)
        self.assertEqual(client.post(reverse('accounts:delete-assignment', args=[self.task_a.pk]),
                                     {'version': 1}).status_code, 403)

    def test_fixture_or_migration_settings_cannot_serve_web_requests(self):
        with override_settings(ALLOW_INTERNAL_TEST_PRINCIPALS=True):
            self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 503)
        with override_settings(STUDENT_DB_ALIAS='default'):
            self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 503)
        with patch('accounts.middleware.connections', {'runtime': connections['auth']}):
            self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 503)
        with patch('accounts.boundary.connections', {'auth': connections['default']}):
            self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 503)

    def test_database_error_responses_do_not_expose_secrets_or_sql(self):
        self.seed()
        with patch('accounts.views.courses.retrieve', side_effect=DatabaseError('private SQL and signing key')):
            response = self.client_a.get(reverse('accounts:course', args=[self.course_a.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private SQL', response.content)

    def test_runtime_and_auth_database_privileges_stay_separate(self):
        for alias, statements in (
            ('runtime', ['SELECT password FROM accounts_student', 'SELECT * FROM django_session',
                         'SELECT digest FROM accounts_accounttoken', 'SELECT secret FROM ucc_security.context_key']),
            ('auth', ['SELECT * FROM academics_course', 'SELECT secret FROM ucc_security.context_key',
                      'SELECT ucc_security.current_student()', 'SELECT * FROM django_migrations',
                      'ALTER TABLE accounts_student ADD COLUMN forbidden integer',
                      'TRUNCATE accounts_student CASCADE', "UPDATE accounts_student SET is_active=true",
                      "UPDATE accounts_student SET username='changed'", 'DELETE FROM accounts_student']),
        ):
            for statement in statements:
                with self.subTest(alias=alias, statement=statement):
                    with self.assertRaises(DatabaseError), transaction.atomic(using=alias):
                        with connections[alias].cursor() as cursor:
                            cursor.execute(statement)
        for alias in ('runtime', 'auth'):
            with connections[alias].cursor() as cursor:
                cursor.execute('SELECT current_user, session_user')
                self.assertEqual(cursor.fetchone(), (connections[alias].settings_dict['USER'],) * 2)

    def test_stored_academic_text_is_escaped_in_html(self):
        self.seed()
        courses.update(self.identity_a, self.course_a.pk, version=1, name='<script>alert("synthetic")</script>')
        response = self.client_a.get(reverse('accounts:academic'))
        self.assertNotIn(b'<script>', response.content)
        self.assertIn(b'&lt;script&gt;', response.content)

    def test_malformed_server_session_identifiers_fail_without_server_errors(self):
        for value in ('not-a-uuid', ['forged'], {'id': str(self.b.pk)}):
            self.login()
            session = self.client_a.session
            session[SESSION_KEY] = value
            session.save()
            self.assertEqual(self.client_a.get(reverse('accounts:academic')).status_code, 302)
        request = RequestFactory().get('/')
        request.user = self.a
        with self.assertRaises(OwnershipRequired):
            principal_for_request(request)
