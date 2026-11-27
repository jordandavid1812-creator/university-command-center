"""4B regressions: literal bounded search, feedback and validated read queries."""
from datetime import date
from unittest.mock import patch
from django.db import connections
from django.test.utils import CaptureQueriesContext
from academics import queries, services
from academics.ownership import OwnershipRequired
from .base import WebsiteCase


class WebsitePolishTests(WebsiteCase):
    def test_first_time_dashboard_gives_ordered_next_steps(self):
        self.login()
        response = self.client_a.get('/')
        self.assertContains(response, 'Start with one semester')
        self.assertContains(response, 'Create your first semester')
        self.assertContains(response, 'never counted as F')
        self.assertNotContains(response, 'class="hero"')
        self.assertLess(response.content.index(b'Actual CGPA'), response.content.index(b'Selected semester'))

    def test_existing_workspace_does_not_repeat_first_time_onboarding(self):
        self.seed()
        response = self.client_a.get('/')
        self.assertNotContains(response, 'Start with one semester')
        self.assertContains(response, '?status=overdue')
        # The seeded assignment is due 11 Nov 2026; pin the request's local date so
        # this test does not start failing once that fixture date is in the past.
        with patch('student_web.views.timezone.localdate', return_value=date(2026, 11, 11)):
            response = self.client_a.get('/')
        self.assertNotContains(response, 'Review 0 overdue assignments')
        self.assertEqual(response.context['totals']['overdue'], 0)
        with patch('student_web.views.timezone.localdate', return_value=date(2026, 11, 12)):
            overdue = self.client_a.get('/')
        self.assertContains(overdue, 'Review 1 overdue assignment')

    def test_course_search_matches_code_and_name_case_insensitively(self):
        self.seed()
        for term in ('one', 'a COURSE'):
            response = self.client_a.get('/courses/', {'q': term})
            self.assertEqual(response.context['page'].total, 1)
            self.assertContains(response, 'Synthetic A course')
            self.assertNotContains(response, 'Synthetic B course')

    def test_course_search_combines_semester_and_preserves_filter_pagination(self):
        self.seed()
        other = services.semesters.create(self.identity_a, label='Another semester')
        services.courses.create(self.identity_a, semester_id=other.pk, original_code='OTHER',name='Match course',credit_units=1)
        for i in range(26):
            services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code=f'LOOK{i}',name='Match course',credit_units=1)
        response = self.client_a.get('/courses/', {'q': 'Match', 'semester': self.sem_a.pk})
        self.assertEqual(response.context['page'].total, 26)
        self.assertEqual(len(response.context['page'].items), 25)
        self.assertIn('q=Match', response.context['next_url'])
        self.assertIn('semester=', response.context['next_url'])
        second = self.client_a.get(response.context['next_url'].replace('?', '/courses/?', 1))
        self.assertEqual(len(second.context['page'].items), 1)

    def test_search_wildcards_are_literal_not_sql_patterns(self):
        self.seed()
        services.assignments.create(self.identity_a,course_id=self.course_a.pk,title='100% _done',due_date=date(2026,12,1))
        response = self.client_a.get('/assignments/', {'q': '% _'})
        self.assertEqual(response.context['page'].total, 1)
        self.assertEqual(response.context['page'].items[0].title, '100% _done')
        self.assertEqual(self.client_a.get('/courses/', {'q': "' OR 1=1 --"}).context['page'].total, 0)

    def test_assignment_search_matches_title_code_and_course_name(self):
        self.seed()
        for term in ('A task', 'one', 'A course'):
            response = self.client_a.get('/assignments/', {'q': term})
            self.assertEqual(response.context['page'].total, 1)
            self.assertNotContains(response, 'Synthetic B task')

    def test_assignment_search_combines_status_and_sort(self):
        self.seed()
        services.assignments.create(self.identity_a,course_id=self.course_a.pk,title='Synthetic done',due_date=date(2026,12,1),completed=True)
        response = self.client_a.get('/assignments/', {'q': 'Synthetic', 'status':'completed','sort':'latest'})
        self.assertEqual(response.context['page'].total, 1)
        self.assertTrue(response.context['page'].items[0].completed)

    def test_search_bound_rejected_at_forms_and_service(self):
        self.seed()
        for path, kind in (('/courses/', 'course'), ('/assignments/', 'assignment')):
            response = self.client_a.get(path, {'q': 'x'*81})
            self.assertEqual(response.status_code, 400)
            self.assertIn('q', response.context['filter'].errors)
            self.assertContains(response, 'id="error-summary" tabindex="-1"', status_code=400)
            self.assertContains(response, 'href="#id_q"', status_code=400)
            for value in ('x'*81, None, 7):
                with self.assertRaises(services.InvalidRecord):
                    queries.page(self.identity_a, kind, search=value)
        with self.assertRaises(services.InvalidRecord):
            queries.page(self.identity_a, 'semester', search='unsupported')

    def test_search_feedback_escapes_html_and_preserves_input(self):
        self.seed()
        response = self.client_a.get('/courses/', {'q':'<script>alert(1)</script>'})
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'Clear filters')
        self.assertEqual(response.context['filter']['q'].value(), '<script>alert(1)</script>')

    def test_search_has_accessible_help_and_native_get_submission(self):
        self.seed()
        response = self.client_a.get('/assignments/')
        self.assertContains(response, 'for="id_q"')
        self.assertContains(response, 'aria-describedby="id_q_helptext"')
        self.assertContains(response, 'maxlength="80"')
        self.assertContains(response, '<form method="get"')
        self.assertContains(response, 'type="search"')

    def test_hidden_version_error_has_no_invisible_focus_target(self):
        self.seed()
        response = self.client_a.post(f'/courses/{self.course_a.pk}/edit/', {
            'name':'Keep my input','original_code':'ONE','credit_units':'3','semester_id':str(self.sem_a.pk),'actual_grade':'A','version':'bad'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'This form is out of date or incomplete', status_code=400)
        self.assertNotContains(response, 'href="#id_version"', status_code=400)
        self.assertContains(response, 'Keep my input', status_code=400)
        self.assertContains(response, 'id="error-summary" tabindex="-1"', status_code=400)

    def test_optional_grade_and_required_field_guidance(self):
        self.seed()
        response = self.client_a.get('/courses/new/')
        self.assertContains(response, 'Actual grade (optional)')
        self.assertContains(response, 'Complete each field unless it is marked optional')
        self.assertContains(response, 'Only your semesters are available')

    def test_account_errors_share_focusable_summary_only_in_website_profile(self):
        self.assertContains(self.client_a.get('/accounts/login/'), 'If your session expired, sign in again')
        response = self.client_a.post('/accounts/login/', {'username':'alpha','password':'incorrect'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="error-summary"')

    def test_error_focus_script_does_not_store_private_state(self):
        response = self.client.get('/static/student_web/site.js')
        script = b''.join(response.streaming_content).decode()
        self.assertIn("document.querySelector('#error-summary')?.focus()", script)
        self.assertNotIn('localStorage', script)
        self.assertNotIn('sessionStorage', script)

    def test_every_optimized_read_rejects_missing_and_forged_context(self):
        self.seed()
        operations = (lambda identity: queries.options(identity, 'course'),
                      lambda identity: queries.page(identity, 'course', search='ONE'),
                      queries.academic_snapshot,
                      lambda identity: queries.assignment_metrics(identity, date(2026,12,1)),
                      lambda identity: queries.code_in_use(identity, 'ONE'))
        for operation in operations:
            for identity in (None, self.a.pk, {'student_id': self.a.pk}):
                with self.assertRaises(OwnershipRequired):
                    operation(identity)
        self.client_a.post('/accounts/logout/')
        for operation in operations:
            with self.assertRaises(OwnershipRequired):
                operation(self.identity_a)

    def test_query_budgets_and_no_n_plus_one_growth(self):
        self.seed()
        paths = ('/', '/courses/', '/assignments/?status=pending', '/performance/')
        def measure(path):
            with CaptureQueriesContext(connections['runtime']) as runtime, CaptureQueriesContext(connections['auth']) as auth, CaptureQueriesContext(connections['default']) as migration:
                response = self.client_a.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(migration), 0)
            return len(runtime), len(auth)
        # Warm middleware role-safety checks; live identity checks remain per operation.
        self.client_a.get('/')
        before = {path: measure(path) for path in paths}
        for i in range(27):
            course = services.courses.create(self.identity_a,semester_id=self.sem_a.pk,original_code=f'GROW{i}',name='Synthetic growth',credit_units=1)
            services.assignments.create(self.identity_a,course_id=course.pk,title='Synthetic growth',due_date=date(2026,12,1))
        after = {path: measure(path) for path in paths}
        self.assertEqual(before, after)
        for runtime, auth in after.values():
            self.assertLessEqual(runtime, 20)
            self.assertLessEqual(auth, 20)

    def test_search_does_not_change_global_cgpa_or_limits(self):
        self.seed()
        services.courses.create(self.identity_a,semester_id=self.sem_a.pk,original_code='FAIL',name='Other',credit_units=3,actual_grade='F')
        self.client_a.get('/courses/', {'q':'ONE'})
        response = self.client_a.get('/performance/')
        self.assertEqual(response.context['summary']['gpa'], 2)
        self.assertEqual((queries.PAGE_SIZE, queries.MAX_COURSES, queries.MAX_SEMESTERS, queries.MAX_PREDICTION_COURSES), (25,1000,200,200))
        with patch('academics.queries.MAX_COURSES', 1):
            self.assertEqual(self.client_a.get('/performance/').status_code, 413)
