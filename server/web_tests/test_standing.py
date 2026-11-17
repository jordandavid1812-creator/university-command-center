"""Know where you stand (part A): chart, CGPA breakdown, grade scale, graduation predictor, print page."""
import re
from decimal import Decimal
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class StandingTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()  # course_a: ONE, 3 units, B
        self.second = services.semesters.create(self.identity_a, label='Synthetic second semester')
        services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code='TWO', name='Two',
                                credit_units=Decimal('2'), actual_grade='A')
        services.courses.create(self.identity_a, semester_id=self.second.pk, original_code='THREE', name='Three',
                                credit_units=Decimal('4'), actual_grade='C')
        services.courses.create(self.identity_a, semester_id=self.second.pk, original_code='FOUR', name='Four',
                                credit_units=Decimal('3'), actual_grade=None)

    def test_overview_shows_the_chart_the_working_and_the_scale(self):
        page = self.client_a.get(reverse('student_web:overview'))
        html = page.content.decode()
        # Chart: one bar per graded semester, the CGPA reference line and its direct label.
        self.assertEqual(len(re.findall(r'<g class="standing-bar"><rect class="standing-hit"', html)), 2)
        self.assertContains(page, 'class="standing-cgpa"')
        # CGPA = (3x4 + 2x5 + 4x3) / 9 = 34/9 = 3.78
        self.assertContains(page, 'CGPA 3.78')
        self.assertContains(page, 'role="img" aria-label="Bar chart of GPA for each semester, with overall CGPA 3.78.')
        # Breakdown: each course's working, semester GPAs and the overall division.
        self.assertContains(page, '3 × 4 = 12')
        self.assertContains(page, '2 × 5 = 10')
        self.assertContains(page, 'GPA = 22 ÷ 5 = <strong>4.40</strong>', html=False)
        self.assertContains(page, 'Not graded yet: not counted')
        self.assertContains(page, 'CGPA = 34 ÷ 9 = <strong>3.78</strong>', html=False)
        # Grade scale, highest first, and the handbook note.
        self.assertRegex(html, r'(?s)<th scope="row">A</th><td>5</td>.*<th scope="row">F</th><td>0</td>')
        self.assertContains(page, 'Check your student handbook')
        self.assertContains(page, reverse('student_web:standing-print'))
        self.assertContains(page, 'student_web/standing.css')

    def test_other_students_and_signed_out_visitors_see_nothing_of_it(self):
        other = self.client_b.get(reverse('student_web:overview'))
        self.assertNotContains(other, 'TWO')
        self.assertNotContains(other, 'Synthetic second semester')
        for name in ('overview', 'standing-print', 'planner'):
            self.assertRedirects(self.client.get(reverse(f'student_web:{name}')), reverse('accounts:login'),
                                 fetch_redirect_response=False)

    def test_no_grades_means_no_chart(self):
        self.assertContains(self.client_b.get(reverse('student_web:overview')), '<svg', count=1)
        course = services.courses.retrieve(self.identity_b, self.course_b.pk)
        services.courses.update(self.identity_b, course.pk, version=course.record_version, actual_grade=None)
        page = self.client_b.get(reverse('student_web:overview'))
        self.assertNotContains(page, '<svg')
        self.assertContains(page, 'Not graded yet: not counted')
        self.assertContains(page, 'No graded courses yet.')

    def test_graduation_predictor(self):
        url = reverse('student_web:planner-projection')
        planner = self.client_a.get(reverse('student_web:planner'))
        self.assertContains(planner, 'Graduation predictor')
        self.assertContains(planner, 'id="projection_expected"')
        self.assertContains(planner, 'id="id_target"')
        before = len(services.courses.list(self.identity_a))
        result = self.client_a.post(url, {'expected': '4.5', 'remaining': '60'})
        # (34 + 4.5 x 60) / 69 = 304 / 69 = 4.4058
        self.assertContains(result, '<p class="standing-result">4.41</p>', html=False)
        self.assertContains(result, '4.4058')
        self.assertContains(result, 'it is 3.78 now')
        self.assertEqual(len(services.courses.list(self.identity_a)), before)  # nothing saved
        refused = self.client_a.post(url, {'expected': '5.5', 'remaining': '60'})
        self.assertEqual(refused.status_code, 400)
        self.assertContains(refused, 'href="#projection_expected"', status_code=400)
        # More than four decimal places is refused, never silently rounded.
        self.assertContains(self.client_a.post(url, {'expected': '4.12345', 'remaining': '60'}),
                            'href="#projection_expected"', status_code=400)
        self.assertContains(self.client_a.post(url, {'expected': '4', 'remaining': '0'}),
                            'href="#projection_remaining"', status_code=400)
        self.assertEqual(self.client_a.post(url, {'expected': '4', 'remaining': '60', 'extra': '1'}).status_code, 400)
        self.assertEqual(self.client_a.get(url).status_code, 405)

    def test_printable_summary(self):
        page = self.client_a.get(reverse('student_web:standing-print'))
        self.assertContains(page, '<h1>alpha</h1>', html=False)
        self.assertContains(page, 'data-print hidden')
        self.assertContains(page, 'Ctrl+P')
        self.assertContains(page, 'CGPA = 34 ÷ 9 = <strong>3.78</strong>', html=False)
        self.assertContains(page, 'this is not an official transcript')
        self.assertNotContains(self.client_b.get(reverse('student_web:standing-print')), 'TWO')
