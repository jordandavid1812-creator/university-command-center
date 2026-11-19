from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch
from django.conf import settings
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from academics import queries, services
from student_web import data
from .base import WebsiteCase


class WebsitePageTests(WebsiteCase):
    def test_empty_dashboard_is_helpful_and_does_not_invent_grades(self):
        self.login()
        response = self.client_a.get(reverse('student_web:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome back, alpha')
        self.assertContains(response, 'Not graded')
        self.assertContains(response, 'No upcoming deadlines')
        self.assertEqual(response.context['summary']['units'], 0)
        self.assertIsNone(response.context['summary']['gpa'])
        self.assertEqual(response.context['totals']['pending'], 0)

    def test_populated_dashboard_uses_real_counts_and_explicit_current_semester(self):
        self.seed()
        today = timezone.localdate()
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, due_date=today, completed=True)
        services.assignments.create(self.identity_a, course_id=self.course_a.pk, title='Overdue own task', due_date=today - timedelta(days=1))
        services.assignments.create(self.identity_a, course_id=self.course_a.pk, title='Upcoming own task', due_date=today + timedelta(days=1))
        response = self.client_a.get(reverse('student_web:dashboard'))
        self.assertEqual(response.context['totals'], {'total': 3, 'completed': 1, 'pending': 2, 'overdue': 1})
        self.assertIsNone(response.context['current'])
        selected = self.client_a.get(reverse('student_web:dashboard'), {'semester': self.sem_a.pk})
        self.assertEqual(selected.context['current']['gpa'], Decimal(4))
        self.assertContains(selected, 'Upcoming own task')
        self.assertNotContains(selected, 'Synthetic B course')

    def test_all_primary_pages_have_authenticated_navigation(self):
        self.seed()
        for name in ('dashboard', 'semester-list', 'course-list', 'assignment-list', 'overview', 'predictor', 'planner', 'settings'):
            response = self.client_a.get(reverse('student_web:' + name))
            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, 'Skip to main content')
            self.assertContains(response, 'aria-label="Primary navigation"')
            self.assertContains(response, 'aria-label="Mobile navigation"')
            self.assertContains(response, 'aria-current="page"')
            self.assertContains(response, '<main id="main-content"')
            self.assertIn('no-store', response['Cache-Control'])

    def test_website_login_uses_dashboard_and_legacy_entry_redirects(self):
        self.assertRedirects(self.login(), reverse('student_web:dashboard'), fetch_redirect_response=False)
        self.assertRedirects(self.client_a.get(reverse('accounts:academic')), reverse('student_web:dashboard'), fetch_redirect_response=False)

    def test_account_settings_show_verified_identity_without_edit_controls(self):
        self.login()
        response = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(response, 'alpha@example.invalid')
        self.assertContains(response, 'Email verified')
        self.assertContains(response, reverse('accounts:password-change'))
        self.assertNotContains(response, 'name="email"')
        # Owner-approved change (launch step F): Settings offers account deletion only as a link to the
        # separate confirmation page (password + DELETE), never as a control on this page.
        self.assertContains(response, f'href="{reverse("student_web:account-delete")}"')
        self.assertNotContains(response, 'name="confirm"')

    def test_empty_semesters_courses_assignments_and_prediction_states(self):
        self.login()
        for name, message in (('semester-list', 'first semester'), ('course-list', 'No courses'),
                              ('assignment-list', 'No assignments'), ('predictor', 'No courses to predict')):
            self.assertContains(self.client_a.get(reverse('student_web:' + name)), message)

    def test_parent_empty_forms_explain_the_next_step(self):
        self.login()
        course = self.client_a.get(reverse('student_web:course-create'))
        assignment = self.client_a.get(reverse('student_web:assignment-create'))
        self.assertContains(course, 'Create a semester before adding a course')
        self.assertContains(assignment, 'Create a course before adding an assignment')
        self.assertContains(course, ' disabled')

    def test_course_pagination_is_bounded_and_preserves_semester_filter(self):
        self.seed()
        for index in range(26):
            services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code=f'PAGE{index:02}',
                                     name='Synthetic paged course', credit_units=1)
        response = self.client_a.get(reverse('student_web:course-list'), {'semester': self.sem_a.pk})
        self.assertEqual(len(response.context['page'].items), 25)
        self.assertEqual(response.context['page'].total, 27)
        self.assertTrue(response.context['page'].has_next)
        self.assertIn('semester=', response.context['next_url'])
        second = self.client_a.get(reverse('student_web:course-list'), {'semester': self.sem_a.pk, 'page': 2})
        self.assertEqual(len(second.context['page'].items), 2)
        self.assertEqual(self.client_a.get(reverse('student_web:course-list'), {'page': 10001}).status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:course-list'), {'page': 9999}).status_code, 404)

    def test_assignments_filters_sort_and_overdue_keep_records(self):
        self.seed()
        today = timezone.localdate()
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, due_date=today - timedelta(days=1))
        future = services.assignments.create(self.identity_a, course_id=self.course_a.pk, title='Future pending', due_date=today + timedelta(days=1))
        services.assignments.create(self.identity_a, course_id=self.course_a.pk, title='Done task', due_date=today, completed=True)
        for status, expected in (('pending', 2), ('completed', 1), ('upcoming', 1), ('overdue', 1)):
            response = self.client_a.get(reverse('student_web:assignment-list'), {'status': status})
            self.assertEqual(response.context['page'].total, expected, status)
        response = self.client_a.get(reverse('student_web:assignment-list'))
        self.assertContains(response, 'Overdue')
        latest = self.client_a.get(reverse('student_web:assignment-list'), {'sort': 'latest'})
        self.assertEqual(latest.context['page'].items[0].pk, future.pk)
        self.assertEqual(len(services.assignments.list(self.identity_a)), 3)

    def test_timezone_and_due_today_boundary(self):
        self.seed()
        self.assertEqual(settings.TIME_ZONE, 'Africa/Lagos')
        moment = datetime(2026, 11, 11, 23, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(timezone.localdate(moment), date(2026, 11, 12))
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, due_date=date(2026, 11, 12))
        with patch('student_web.views.timezone.localdate', return_value=date(2026, 11, 12)):
            response = self.client_a.get(reverse('student_web:assignment-list'))
            self.assertContains(response, 'Due today')
            self.assertNotContains(response, '<span class="badge overdue">')

    def test_calculation_limits_never_display_partial_gpa(self):
        self.seed()
        with patch('academics.queries.MAX_COURSES', 0):
            response = self.client_a.get(reverse('student_web:overview'))
        self.assertEqual(response.status_code, 413)
        self.assertContains(response, 'No partial GPA', status_code=413)

    def test_predictor_large_form_requires_filter_instead_of_silent_truncation(self):
        self.seed()
        with patch('student_web.forms.MAX_PREDICTION_COURSES', 0):
            response = self.client_a.get(reverse('student_web:predictor'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose a semester')
        self.assertNotContains(response, 'name="grade_')

    def test_static_css_is_local_and_contains_mobile_and_focus_rules(self):
        response = self.client.get('/static/student_web/site.css')
        self.assertEqual(response.status_code, 200)
        content = b''.join(response.streaming_content).decode()
        self.assertIn('@media', content)
        self.assertIn('focus-visible', content)
        self.assertIn('prefers-reduced-motion', content)
        self.assertIn('min-width:640px', content)
        self.assertNotIn('@import', content)

    def test_read_pages_do_not_query_migration_connection_or_load_unbounded_assignments(self):
        self.seed()
        with CaptureQueriesContext(connections['default']) as default_queries:
            with CaptureQueriesContext(connections['runtime']) as runtime_queries:
                response = self.client_a.get(reverse('student_web:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(default_queries), 0)
        assignment_reads = [q['sql'] for q in runtime_queries if 'academics_assignment' in q['sql'] and q['sql'].lstrip().upper().startswith('SELECT')]
        self.assertTrue(any('LIMIT 5' in sql for sql in assignment_reads))
        self.assertTrue(any('COUNT(' in sql for sql in assignment_reads))
