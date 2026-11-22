"""The dashboard's "Get started" checklist for new students (owner's request: help new users set
things up). Six steps, each done or not from the student's OWN records, read in the dashboard's one
verified transaction. Synthetic data only."""
from datetime import date, time
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from academics import queries, services
from student_web.data import getting_started
from .base import WebsiteCase


class GettingStartedTests(WebsiteCase):
    def dashboard(self, client=None):
        return (client or self.client_a).get(reverse('student_web:dashboard'))

    def test_a_brand_new_student_sees_six_steps_with_the_first_one_highlighted(self):
        self.login()
        page = self.dashboard()
        self.assertContains(page, 'Get started with UniCommand')
        self.assertContains(page, '0 of 6 done')
        self.assertContains(page, 'aria-valuenow="0"')
        self.assertContains(page, '/static/student_web/getting_started.css')
        html = page.content.decode()
        self.assertEqual(html.count('class="start-step is-next"'), 1)
        self.assertEqual(html.count('class="start-step is-blocked"'), 5)  # each needs an earlier step first
        self.assertContains(page, f'href="{reverse("student_web:semester-create")}"')
        checklist = html[html.index('<details class="panel getting-started"'):html.index('</details>')]
        for url in ('course-create', 'assignment-create', 'session-create', 'material-upload', 'material-list'):
            self.assertNotIn(f'href="{reverse("student_web:" + url)}"', checklist)  # nothing that cannot work yet
        self.assertContains(page, 'Create a semester first.')
        self.assertContains(page, 'Add a course first.')
        self.assertContains(page, 'Upload your notes first.')

    def test_each_button_appears_once_its_earlier_step_is_done(self):
        self.seed()
        page = self.dashboard()
        for url in ('session-create', 'material-upload'):
            self.assertContains(page, f'href="{reverse("student_web:" + url)}"')
        self.assertContains(page, 'Upload your notes first.')  # study tools still need a file
        html = page.content.decode()
        self.assertIn('class="start-step is-next"', html)
        self.assertLess(html.index('is-next'), html.index('Upload your lecture notes'))  # the timetable comes first

    def test_steps_tick_off_from_the_students_own_records_only(self):
        self.seed()  # each student: a semester, a graded course and an assignment
        page = self.dashboard()
        self.assertContains(page, '3 of 6 done')
        self.assertEqual(page.content.decode().count('start-step is-done'), 3)
        # Bravo adds a class and a file; alpha's checklist does not change.
        services.class_sessions.create(self.identity_b, course_id=self.course_b.pk, weekday=1,
                                       start_time=time(8), end_time=time(10), kind='lecture', venue='LT1')
        services.materials.create(self.identity_b, course_id=self.course_b.pk, title='Synthetic B notes',
                                  original_filename='b.txt', file_type='txt', size_bytes=3)
        self.assertContains(self.dashboard(), '3 of 6 done')
        self.assertContains(self.dashboard(self.client_b), '5 of 6 done')

    def test_an_ungraded_course_does_not_tick_the_course_step(self):
        self.login()
        owner = self.identity(self.client_a)
        semester = services.semesters.create(owner, label='Synthetic semester')
        services.courses.create(owner, semester_id=semester.pk, original_code='UNG', name='Synthetic ungraded',
                                credit_units=2)
        self.assertContains(self.dashboard(), '1 of 6 done')

    def test_the_list_disappears_once_every_step_is_done(self):
        done = {'materials': True, 'classes': True}
        course = type('Course', (), {'actual_grade': 'A'})()
        state = getting_started(['semester'], [course], {'total': 1}, done, {'recent': [{'id': 1}]})
        self.assertTrue(state['complete'])
        self.assertEqual((state['done'], state['total'], state['percent'], state['next']), (6, 6, 100, None))
        partial = getting_started([], [], {'total': 0}, {'materials': False, 'classes': False}, {'recent': []})
        self.assertEqual((partial['done'], partial['next']), (0, 'semester'))
        from django.template.loader import render_to_string
        self.assertEqual(render_to_string('student_web/components/getting_started.html',
                                          {'getting_started': state}).strip(), '')

    def test_it_adds_one_small_read_in_the_same_verified_transaction(self):
        self.seed()
        with CaptureQueriesContext(connections['runtime']) as captured:
            queries.dashboard_reads(self.identity_a, date(2026, 11, 16))
        statements = [query['sql'] for query in captured.captured_queries]
        self.assertEqual(sum('ucc_security.current_student()' in sql for sql in statements), 1)
        materials = [sql for sql in statements if 'FROM "academics_studymaterial"' in sql]
        self.assertEqual(len(materials), 1, materials)  # the only new read
        self.assertIn('UNION ALL', materials[0])
        self.assertIn('FROM "academics_classsession"', materials[0])
        self.assertEqual(sum('UNION ALL' in sql for sql in statements), 1)
        started = queries.dashboard_reads(self.identity_a, date(2026, 11, 16))[-1]
        self.assertEqual(started, {'materials': False, 'classes': False})
        services.class_sessions.create(self.identity_a, course_id=self.course_a.pk, weekday=1,
                                       start_time=time(8), end_time=time(10), kind='lecture', venue='LT1')
        self.assertEqual(queries.dashboard_reads(self.identity_a, date(2026, 11, 16))[-1],
                         {'materials': False, 'classes': True})
        services.materials.create(self.identity_a, course_id=self.course_a.pk, title='Synthetic A notes',
                                  original_filename='a.txt', file_type='txt', size_bytes=3)
        self.assertEqual(queries.dashboard_reads(self.identity_a, date(2026, 11, 16))[-1],
                         {'materials': True, 'classes': True})

    def test_the_checklist_works_without_javascript_and_stays_small(self):
        from pathlib import Path
        self.login()
        html = self.dashboard().content.decode()
        self.assertIn('<details class="panel getting-started" open>', html)
        self.assertIn('<summary>', html)
        css = Path(__file__).resolve().parents[1] / 'student_web/static/student_web/getting_started.css'
        self.assertLessEqual(css.stat().st_size, 4_000)
        text = css.read_text()
        for forbidden in ('@import', 'url('):
            self.assertNotIn(forbidden, text)
        self.assertIn('prefers-reduced-motion', text)
