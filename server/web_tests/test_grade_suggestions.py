"""Grade suggestions on the Target CGPA Planner (owner's choice): a letter for each of the student's
own ungraded courses that reaches a target. Read-only: nothing is saved. Synthetic data only."""
from django.urls import reverse
from academics import services
from .base import WebsiteCase


class GradeSuggestionPageTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()  # each student: one graded course (A: B, B: A) and an assignment
        for code, units in (('TWO', 3), ('THREE', 2)):
            services.courses.create(self.identity_a, semester_id=self.sem_a.pk, original_code=code,
                                    name=f'Synthetic {code}', credit_units=units)
        services.courses.create(self.identity_b, semester_id=self.sem_b.pk, original_code='BONLY',
                                name='Synthetic B only', credit_units=4)

    def suggest(self, target, client=None):
        return (client or self.client_a).post(reverse('student_web:planner-suggest'), {'target': target})

    def test_the_planner_offers_the_form(self):
        page = self.client_a.get(reverse('student_web:planner'))
        self.assertContains(page, 'Grade suggestions for your courses')
        self.assertContains(page, f'action="{reverse("student_web:planner-suggest")}"')
        self.assertContains(page, 'id="suggest_target"')
        self.assertContains(page, 'value="4.50"')  # starts at the First Class band

    def test_suggests_a_grade_for_each_own_ungraded_course(self):
        page = self.suggest('4.5')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'One way to reach 4.50')
        for code in ('TWO', 'THREE'):
            self.assertContains(page, f'<th scope="row">{code}</th>', html=False)
        self.assertNotContains(page, 'BONLY')  # another student's course is never used
        self.assertContains(page, 'reaching your target')

    def test_nothing_is_saved(self):
        before = sorted((c.original_code, c.actual_grade) for c in services.courses.list(self.identity_a))
        self.suggest('4.5')
        after = sorted((c.original_code, c.actual_grade) for c in services.courses.list(self.identity_a))
        self.assertEqual(before, after)

    def test_safe_out_of_reach_and_nothing_ungraded(self):
        self.assertContains(self.suggest('1'), 'Already safe')
        self.assertContains(self.suggest('4.99'), 'Out of reach with these courses')
        self.assertContains(self.suggest('4', self.client_b), 'One way to reach 4.00')
        for course in services.courses.list(self.identity_a):
            if not course.actual_grade:
                services.courses.update(self.identity_a, course.pk, version=course.record_version, actual_grade='C')
        self.assertContains(self.suggest('4'), 'No ungraded courses')

    def test_bad_targets_are_refused(self):
        for target in ('', '5.5', 'abc', '-1'):
            with self.subTest(target=target):
                self.assertEqual(self.suggest(target).status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:planner-suggest')).status_code, 405)

    def test_signed_out_visitors_are_sent_to_login(self):
        self.client_a.logout()
        response = self.suggest('4')
        self.assertIn(response.status_code, (302, 403))
