"""UI2 presents the existing authorized context without extra reads or new math."""
from contextlib import ExitStack
from datetime import date, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from django.db import connections
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from academics import services
from .base import WebsiteCase

TODAY = date(2026, 11, 12)


class PrimaryAction(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_header = False
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'header' and 'dashboard-welcome' in attrs.get('class', '').split():
            self.in_header = True
        if tag == 'a' and self.in_header:
            classes = attrs.get('class', '').split()
            if 'button' in classes and 'secondary' not in classes:
                self.links.append(attrs['href'])

    def handle_endtag(self, tag):
        if tag == 'header':
            self.in_header = False


class DashboardDesignTests(WebsiteCase):
    def workspace(self):
        self.login()
        self.owner = self.identity(self.client_a)
        return services.semesters.create(self.owner, label='Synthetic semester', display_order=1)

    def course(self, semester, code='ONE', grade=None, credits=3):
        return services.courses.create(self.owner, semester_id=semester.pk, original_code=code,
                                       name='Synthetic dashboard course', credit_units=credits, actual_grade=grade)

    def test_no_parent_records_offer_only_valid_creation_actions(self):
        self.login()
        response = self.client_a.get('/')
        self.assertEqual(PrimaryAction(response.content.decode()).links, ['/semesters/new/'])
        self.assertNotContains(response, 'href="/courses/new/"')
        self.assertNotContains(response, 'href="/assignments/new/"')
        self.assertContains(response, 'id="actual-cgpa-value">Not graded</strong>')
        self.assertNotContains(response, 'dashboard-attention')

    def test_semester_without_courses_promotes_course_not_assignment(self):
        self.workspace()
        response = self.client_a.get('/')
        self.assertEqual(PrimaryAction(response.content.decode()).links, ['/courses/new/'])
        self.assertNotContains(response, 'href="/assignments/new/"')
        self.assertIsNone(response.context['summary']['gpa'])

    def test_ungraded_courses_are_not_zero_and_promote_assignments(self):
        semester = self.workspace()
        self.course(semester)
        response = self.client_a.get('/')
        self.assertEqual(PrimaryAction(response.content.decode()).links, ['/assignments/new/'])
        self.assertContains(response, 'id="actual-cgpa-value">Not graded</strong>')
        self.assertEqual(response.context['summary']['units'], 0)
        self.assertEqual(response.context['summary']['ungraded'], 1)

    def test_real_zero_is_preserved_globally_and_for_selected_semester(self):
        semester = self.workspace()
        self.course(semester, grade='F')
        response = self.client_a.get('/', {'semester': str(semester.pk)})
        self.assertContains(response, 'id="actual-cgpa-value">0.00</strong>')
        self.assertEqual(response.context['summary']['units'], Decimal(3))
        self.assertEqual(response.context['current']['gpa'], Decimal(0))
        self.assertContains(response, 'class="dashboard-selected-value">0.00')
        self.assertContains(response, f'value="{semester.pk}" selected')
        self.assertContains(response, 'Selected semester')
        self.assertNotContains(response, 'Current semester')

    def test_mixed_actual_and_ungraded_summary_is_unchanged(self):
        semester = self.workspace()
        self.course(semester, code='A', grade='A')
        self.course(semester, code='F', grade='F')
        self.course(semester, code='WAIT', credits=7)
        response = self.client_a.get('/')
        self.assertContains(response, 'id="actual-cgpa-value">2.50</strong>')
        summary = response.context['summary']
        self.assertEqual((summary['units'], summary['graded'], summary['ungraded']), (Decimal(6), 2, 1))
        self.assertEqual(len(response.context['courses']), 3)

    @patch('student_web.views.timezone.localdate', return_value=TODAY)
    def test_overdue_only_keeps_attention_without_claiming_completion(self, _date):
        semester = self.workspace()
        course = self.course(semester)
        services.assignments.create(self.owner, course_id=course.pk, title='Synthetic overdue', due_date=TODAY-timedelta(days=1))
        response = self.client_a.get('/')
        self.assertContains(response, 'Review 1 overdue assignment')
        self.assertContains(response, 'No upcoming deadlines')
        self.assertContains(response, 'review overdue tasks')
        self.assertEqual(len(response.context['upcoming']), 0)
        self.assertNotContains(response, 'All caught up')

    @patch('student_web.views.timezone.localdate', return_value=TODAY)
    def test_upcoming_preview_remains_five_with_codes_dates_and_links(self, _date):
        semester = self.workspace()
        course = self.course(semester)
        tasks = [services.assignments.create(self.owner, course_id=course.pk, title=f'Synthetic pending {n}',
                  due_date=TODAY+timedelta(days=n)) for n in range(7)]
        response = self.client_a.get('/')
        self.assertEqual(len(response.context['upcoming']), 5)
        for task in tasks[:5]:
            self.assertContains(response, task.title)
            self.assertContains(response, f'datetime="{task.due_date.isoformat()}"')
            self.assertContains(response, f'href="/assignments/{task.pk}/edit/"')
        self.assertNotContains(response, tasks[5].title)
        self.assertContains(response, '<span>ONE</span>')
        self.assertContains(response, '12 Nov 2026</time>')
        self.assertNotContains(response, 'dashboard-attention')

    @patch('student_web.views.timezone.localdate', return_value=TODAY)
    def test_empty_and_completed_only_workspaces_use_neutral_deadline_guidance(self, _date):
        semester=self.workspace()
        course=self.course(semester)
        response=self.client_a.get('/')
        self.assertEqual(response.context['totals']['total'],0)
        self.assertContains(response,'Add an assignment when you have a deadline.')
        self.assertNotContains(response,'review overdue tasks')
        self.assertContains(response,'Up to five pending deadlines due today or later')
        services.assignments.create(self.owner,course_id=course.pk,title='Synthetic completed work',
                                    due_date=TODAY-timedelta(days=1),completed=True)
        response=self.client_a.get('/')
        self.assertEqual(response.context['totals']['overdue'],0)
        self.assertContains(response,'Visit Assignments to view your work.')
        self.assertNotContains(response,'review overdue tasks')
        self.assertNotContains(response,'All caught up')

    @patch('student_web.views.timezone.localdate', return_value=TODAY)
    def test_same_label_semesters_keep_full_uuid_comparison_and_isolation(self, _date):
        self.seed()
        self.owner = self.identity_a
        other = services.semesters.create(self.owner, label=self.sem_a.label, display_order=2)
        self.course(other, code='TWO', grade='F')
        services.assignments.create(self.identity_b, course_id=self.course_b.pk, title='Foreign upcoming synthetic task', due_date=TODAY+timedelta(days=1))
        response = self.client_a.get('/')
        self.assertEqual(len(response.context['summary']['semesters']), 2)
        for semester in (self.sem_a, other):
            self.assertContains(response, f'value="{semester.pk}"')
        self.assertContains(response, 'Actual grades by semester')
        self.assertNotContains(response, 'Synthetic B')
        self.assertNotContains(response, 'Foreign upcoming synthetic task')
        self.assertEqual(response.context['summary']['gpa'], Decimal(2))
        self.assertNotContains(response, str(self.sem_b.pk))
        self.assertEqual(self.client_a.get('/', {'semester': self.sem_b.pk}).status_code, 400)

    def test_priority_order_and_native_selector(self):
        self.seed()
        response = self.client_a.get('/')
        html = response.content.decode()
        markers = ['dashboard-welcome', 'actual-cgpa-title', 'upcoming-title', 'selected-title', 'performance-title']
        self.assertEqual([html.index(m) for m in markers], sorted(html.index(m) for m in markers))
        self.assertContains(response, '<form method="get"')
        self.assertContains(response, 'name="semester"')

    def test_rendering_the_loaded_context_adds_zero_queries(self):
        self.seed()
        response = self.client_a.get('/')
        names = ('summary', 'courses', 'semesters', 'totals', 'upcoming', 'selector', 'current', 'current_selected', 'today')
        context = {name: response.context[name] for name in names}
        with ExitStack() as stack:
            captured = {alias: stack.enter_context(CaptureQueriesContext(connections[alias])) for alias in ('default', 'runtime', 'auth')}
            render_to_string('student_web/dashboard.html', context, request=response.wsgi_request)
        self.assertEqual({alias: len(q) for alias, q in captured.items()}, {'default': 0, 'runtime': 0, 'auth': 0})

    def test_dashboard_assets_keep_page_budget_and_local_delivery(self):
        root = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'
        self.assertLessEqual((root/'site.css').stat().st_size+(root/'dashboard.css').stat().st_size, 30_000)
        self.assertNotIn('url(', (root/'dashboard.css').read_text())
        self.assertNotIn('@import', (root/'dashboard.css').read_text())
        self.assertEqual(self.client_a.get('/static/student_web/dashboard.css').status_code, 200)
