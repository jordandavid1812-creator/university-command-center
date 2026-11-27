"""Command Centre (owner's choice, from the UX research): Today's mission, XP and scholar levels,
the "what if" grade picker data, the phone tab bar and the quick start. Everything is worked out
from records the dashboard already reads; nothing new is stored. Synthetic data only."""
import json
import re
from django.test import SimpleTestCase
from django.urls import reverse
from academics import services
from accounts.models import Student
from student_web.data import scholar_level
from .base import WebsiteCase


class LevelTests(SimpleTestCase):
    def test_levels_rise_with_xp(self):
        self.assertEqual(scholar_level(0)[:2], (1, 'Fresher'))
        self.assertEqual(scholar_level(99)[:2], (1, 'Fresher'))
        self.assertEqual(scholar_level(100)[:2], (2, 'Scholar'))
        self.assertEqual(scholar_level(1500)[:2], (6, 'First Class Legend'))
        self.assertIsNone(scholar_level(5000)[3])


class CommandCentreTests(WebsiteCase):
    def dashboard(self, client=None):
        return (client or self.client_a).get(reverse('student_web:dashboard')).content.decode()

    def test_new_student_sees_the_quick_start_invitation(self):
        self.login()
        html = self.dashboard()
        self.assertIn('class="command-centre"', html)
        self.assertIn('See where you stand in a minute.', html)
        self.assertIn(f'href="{reverse("student_web:quick-start")}"', html)
        self.assertIn("Today's mission", html)
        self.assertIn('Level 1: Fresher', html)
        self.assertIn('Upload one lecture note', html)  # no notes yet

    def test_mission_reflects_the_students_own_day(self):
        self.seed()  # task_a is overdue, nothing studied today
        html = self.dashboard()
        self.assertIn('Clear an overdue task', html)
        self.assertIn('aria-label="Today\'s mission: 0 of 3 done"', html)
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, completed=True)
        html = self.dashboard()
        self.assertIn('No deadline today', html)  # a head start counts as done
        self.assertIn('aria-label="Today\'s mission: 2 of 3 done"', html)  # studied (completed a task) + no deadline
        self.assertIn('data-cc-done="2"', html)
        self.assertNotIn('Clear an overdue task', self.dashboard(self.client_a))

    def test_xp_counts_real_activity(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='A')
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, completed=True)
        html = self.dashboard()
        # 10 per study day (1) + 15 per finished assignment (1) + 20 per graded course (1) + 5 per course (1) + 5 x best streak (1)
        self.assertIn('55 XP', html)
        self.assertIn('45 XP to Scholar', html)

    def test_what_if_data_lists_only_ungraded_courses(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='OPEN101',
                                name='Synthetic open course', credit_units=2)
        html = self.dashboard()
        data = json.loads(re.search(r'<script id="ucc-whatif" type="application/json">(.*?)</script>', html).group(1))
        self.assertEqual([c['code'] for c in data['courses']], ['OPEN101'])
        self.assertEqual((data['points'], data['units'], data['max']), (12.0, 3.0, 5.0))
        self.assertEqual(data['grades']['A'], 5.0)
        self.assertEqual(data['bands'][0]['name'], 'First Class')
        self.assertIn('data-code="OPEN101" data-grade="A"', html)
        self.assertIn('class="cc-whatif" id="cc-whatif" data-cc-whatif hidden', html)  # shown by command.js only

    def test_other_students_records_never_appear(self):
        self.seed()
        self.assertNotIn('Synthetic A', self.dashboard(self.client_b))


class TabBarTests(WebsiteCase):
    def test_signed_in_pages_have_four_tabs_and_mark_the_current_one(self):
        self.login()
        html = self.client_a.get(reverse('student_web:overview')).content.decode()
        bar = html[html.index('<nav class="tabbar"'):]
        bar = bar[:bar.index('</nav>')]
        self.assertEqual(re.findall(r'<span>(\w+)</span>', bar), ['Home', 'Grades', 'Study', 'Plan'])
        self.assertIn(f'<a href="{reverse("student_web:overview")}" class="is-current">', bar)
        self.assertNotIn('aria-current', bar)  # the main navigation already announces the current page

    def test_public_pages_have_none(self):
        self.assertNotIn('class="tabbar"', self.client.get(reverse('accounts:login')).content.decode())


class QuickStartTests(WebsiteCase):
    def post(self, **rows):
        values = {'label': 'Synthetic last semester', **rows}
        return self.client_a.post(reverse('student_web:quick-start'), values)

    def test_adds_a_semester_and_courses_then_shows_the_dashboard(self):
        self.seed()
        page = self.client_a.get(reverse('student_web:quick-start'))
        self.assertContains(page, 'See where you stand in a minute.')
        self.assertContains(page, 'name="code_7"')
        response = self.post(code_0='syn101', units_0='3', grade_0='A', code_1='SYN102', units_1='2', grade_1='')
        self.assertRedirects(response, reverse('student_web:dashboard'), fetch_redirect_response=False)
        html = self.client_a.get(reverse('student_web:dashboard')).content.decode()
        self.assertIn('2 courses added. Here is where you stand.', html)
        self.assertIn('id="actual-cgpa-value">', html)
        self.assertIn('SYN102', html)  # ungraded: offered in the what-if picker

    def test_rows_are_checked_and_nothing_is_saved_on_error(self):
        self.login()
        response = self.post(code_0='SYN101', grade_0='A')
        self.assertContains(response, 'Enter the credit units for this course.', status_code=400)
        response = self.post(code_0='SYN101', units_0='3', code_1='syn101', units_1='3')
        self.assertContains(response, 'This course code is already in the list.', status_code=400)
        response = self.post()
        self.assertContains(response, 'Add at least one course with its credit units.', status_code=400)
        self.assertNotIn('Synthetic last semester', self.client_a.get(reverse('student_web:semester-list')).content.decode())

    def test_existing_codes_are_refused(self):
        self.seed()
        code = self.course_a.original_code
        response = self.post(code_0=code, units_0='3', grade_0='A')
        self.assertContains(response, f'You already have {code}.', status_code=400)

    def test_four_point_scale_refuses_e(self):
        self.seed()
        services.profiles.set_scale(self.identity_a, 'four')
        response = self.post(code_0='SYN101', units_0='3', grade_0='E')
        self.assertEqual(response.status_code, 400)
        self.assertContains(self.client_a.get(reverse('student_web:quick-start')), '4-point', status_code=200)

    def test_needs_a_signed_in_student(self):
        self.assertEqual(self.client.get(reverse('student_web:quick-start')).status_code, 302)
