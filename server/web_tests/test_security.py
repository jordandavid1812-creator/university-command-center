from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import uuid
from django.db import connections, DatabaseError
from django.test import Client
from django.urls import reverse
from academics import queries, services
from .base import WebsiteCase


class WebsiteSecurityTests(WebsiteCase):
    def test_all_student_pages_reject_unauthenticated_sessions(self):
        for name in ('semester-list', 'course-list', 'assignment-list', 'overview', 'predictor', 'planner', 'settings',
                     'semester-create', 'course-create', 'assignment-create'):
            self.assertRedirects(self.client.get(reverse('student_web:' + name)), reverse('accounts:login'), fetch_redirect_response=False)
        # The main link shows the public welcome page instead, with no student data.
        self.assertContains(self.client.get(reverse('student_web:dashboard')), 'Create a free account')
        self.assertEqual(self.client.post(reverse('student_web:semester-create'), {'label': 'Forged', 'display_order': 0}).status_code, 302)

    def test_cross_account_edit_and_delete_have_same_not_found_message(self):
        self.seed()
        for kind, other in (('semester', self.sem_b), ('course', self.course_b), ('assignment', self.task_b)):
            for action in ('edit', 'delete'):
                known = self.client_a.get(reverse('student_web:' + kind + '-' + action, args=[other.pk]))
                absent = self.client_a.get(reverse('student_web:' + kind + '-' + action, args=[uuid.uuid4()]))
                self.assertEqual((known.status_code, absent.status_code), (404, 404))
                self.assertEqual(known.context['detail'], absent.context['detail'])
                response = self.client_a.post(reverse('student_web:' + kind + '-' + action, args=[other.pk]), {'version': 1, 'confirm': 'on'})
                self.assertEqual(response.status_code, 404)
        self.assertEqual(services.courses.retrieve(self.identity_b, self.course_b.pk).actual_grade, 'A')

    def test_parent_choices_and_filters_cannot_select_another_owner(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:course-create'), {'name': 'Foreign', 'original_code': 'NEW',
                                      'credit_units': 3, 'actual_grade': 'A', 'semester_id': self.sem_b.pk})
        self.assertEqual(response.status_code, 400)
        response = self.client_a.post(reverse('student_web:assignment-create'), {'title': 'Foreign',
                                      'due_date': '2026-11-11', 'course_id': self.course_b.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:course-list'), {'semester': self.sem_b.pk}).status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:dashboard'), {'semester': self.sem_b.pk}).status_code, 400)
        self.assertEqual(len(services.courses.list(self.identity_a)), 1)

    def test_client_owner_ids_and_server_fields_are_rejected(self):
        self.seed()
        for field in ('owner_id', 'owner', 'id', 'record_version', 'updated_at'):
            response = self.client_a.post(reverse('student_web:semester-create'),
                                          {'label': 'Attempted reassignment', 'display_order': 0, field: str(self.b.pk)})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(len(services.semesters.list(self.identity_a)), 1)

    def test_post_csrf_protection_covers_crud_status_and_planning(self):
        self.seed()
        client = Client(enforce_csrf_checks=True)
        client.cookies['sessionid'] = self.client_a.cookies['sessionid'].value
        paths = [reverse('student_web:' + name) for name in ('semester-create', 'course-create', 'assignment-create', 'predictor', 'planner')]
        paths += [reverse('student_web:course-edit', args=[self.course_a.pk]),
                  reverse('student_web:assignment-delete', args=[self.task_a.pk]),
                  reverse('student_web:assignment-status', args=[self.task_a.pk])]
        for path in paths:
            self.assertEqual(client.post(path, {'version': 1}).status_code, 403)
        self.assertEqual(services.assignments.retrieve(self.identity_a, self.task_a.pk).record_version, 1)

    def test_get_requests_do_not_mutate_or_delete(self):
        self.seed()
        self.assertEqual(self.client_a.get(reverse('student_web:assignment-status', args=[self.task_a.pk])).status_code, 405)
        for kind, record in (('semester', self.sem_a), ('course', self.course_a), ('assignment', self.task_a)):
            self.assertEqual(self.client_a.get(reverse('student_web:' + kind + '-delete', args=[record.pk])).status_code, 200)
        self.assertEqual(services.assignments.retrieve(self.identity_a, self.task_a.pk).record_version, 1)

    def test_xss_content_is_escaped_in_lists_selectors_and_confirmations(self):
        self.seed()
        payload = '<script>alert("synthetic")</script>'
        services.semesters.update(self.identity_a, self.sem_a.pk, version=1, label=payload)
        services.courses.update(self.identity_a, self.course_a.pk, version=1, name=payload)
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, title=payload)
        paths = [reverse('student_web:' + name) for name in ('semester-list', 'course-list', 'assignment-list', 'overview', 'predictor')]
        paths.append(reverse('student_web:assignment-delete', args=[self.task_a.pk]))
        for path in paths:
            response = self.client_a.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b'<script>', response.content)
            self.assertIn(b'&lt;script&gt;', response.content)

    def test_forms_expose_labels_helptext_and_focusable_error_summary(self):
        self.seed()
        response = self.client_a.get(reverse('student_web:course-create'))
        for name in ('name', 'original_code', 'credit_units', 'semester_id', 'actual_grade'):
            self.assertContains(response, f'for="id_{name}"')
            self.assertContains(response, f'id="id_{name}"')
        self.assertContains(response, 'aria-describedby="id_credit_units_helptext"')
        bad = self.client_a.post(reverse('student_web:course-create'), {})
        self.assertContains(bad, 'id="error-summary" tabindex="-1"', status_code=400)
        self.assertContains(bad, 'aria-invalid="true"', status_code=400)

    def test_two_simultaneous_student_sessions_remain_isolated(self):
        self.seed()
        def read(cookie):
            try:
                client = Client()
                client.cookies['sessionid'] = cookie
                return client.get(reverse('student_web:dashboard')).content.decode()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(read, [self.client_a.cookies['sessionid'].value, self.client_b.cookies['sessionid'].value]))
        self.assertIn('alpha', results[0])
        self.assertNotIn('Synthetic B task', results[0])
        self.assertIn('bravo', results[1])
        self.assertNotIn('Synthetic A task', results[1])
        with connections['runtime'].cursor() as cursor:
            cursor.execute('SELECT ucc_security.current_student()')
            self.assertEqual(cursor.fetchone(), (None,))

    def test_safe_database_errors_and_fixed_redirects(self):
        self.seed()
        with patch('student_web.views.queries.page', side_effect=DatabaseError('private SQL secret')):
            response = self.client_a.get(reverse('student_web:course-list'))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private SQL secret', response.content)
        response = self.client_a.post(reverse('student_web:semester-create') + '?next=https://evil.invalid/',
                                      {'label': 'Safe redirect', 'display_order': 0})
        self.assertRedirects(response, reverse('student_web:semester-list'), fetch_redirect_response=False)

    def test_oversize_requests_are_rejected_without_writes(self):
        self.seed()
        response = self.client_a.post(reverse('student_web:semester-create'), {'label': 'x' * 70000, 'display_order': 0})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(services.semesters.list(self.identity_a)), 1)

    def test_invalid_read_helper_arguments_fail_closed(self):
        self.seed()
        for operation in (lambda: queries.page(self.identity_a, 'student'),
                          lambda: queries.page(self.identity_a, 'course', number=10001),
                          lambda: queries.page(self.identity_a, 'assignment', status='forged'),
                          lambda: queries.options(self.identity_a, 'owner')):
            with self.assertRaises(services.InvalidRecord):
                operation()

    def test_permission_denied_handler_is_generic_and_returns_403(self):
        from django.core.exceptions import PermissionDenied
        self.seed()
        with patch('student_web.views.queries.page', side_effect=PermissionDenied('private permission details')):
            response = self.client_a.get(reverse('student_web:course-list'))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'private permission details', response.content)
        self.assertContains(response, 'Access unavailable', status_code=403)
        self.assertIn('no-store', response['Cache-Control'])
