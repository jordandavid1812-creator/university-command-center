"""Each student chooses the 4- or 5-point scale in Settings. 5-point stays the default and its
pages are unchanged; 4-point (A=4 to F=0, no E) is refused while any course is graded E, clears
the student's own class bands, and has no built-in class guide. Synthetic data, real PostgreSQL."""
from django.db import DatabaseError, connections, transaction
from django.urls import reverse
from academics import services
from .base import WebsiteCase

BANDS4 = {'first_class_min': '3.5', 'second_upper_min': '3.0', 'second_lower_min': '2.4', 'third_class_min': '1.5',
          'pass_min': '1.0'}


class GradingScaleTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()  # course_a: 3 credits, grade B -> 4.00 on 5-point, 3.00 on 4-point

    def choose(self, scale, client=None):
        client = client or self.client_a
        version = client.get(reverse('student_web:settings')).context['scale_form'].initial['version']
        return client.post(reverse('student_web:grading-scale'), {'scale': scale, 'version': version or ''})

    def test_five_point_is_the_default_and_settings_offer_the_choice(self):
        page = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(page, 'the <strong>5-point</strong> scale', html=False)
        self.assertContains(page, 'name="scale"')
        self.assertContains(page, '<option value="four">')
        self.assertContains(self.client_a.get('/'), '<span> / 5.00</span>', html=False)
        self.assertIsNone(services.profiles.current(self.identity_a))  # nothing saved by looking

    def test_four_point_recalculates_every_page_from_the_same_letters(self):
        response = self.choose('four')
        self.assertRedirects(response, reverse('student_web:settings'), fetch_redirect_response=False)
        self.assertEqual(services.profiles.current(self.identity_a).grading_scale, 'four')
        self.assertEqual(services.courses.retrieve(self.identity_a, self.course_a.pk).actual_grade, 'B')  # unchanged
        dashboard = self.client_a.get('/')
        self.assertContains(dashboard, '3.00</strong><span> / 4.00</span>', html=False)
        overview = self.client_a.get(reverse('student_web:overview'))
        self.assertContains(overview, 'out of 4.00')
        self.assertContains(overview, '4-point scale')
        self.assertContains(overview, 'A=4, B=3, C=2, D=1 and F=0')
        self.assertContains(overview, 'Enter class bands')  # no built-in 4-point guide
        self.assertNotContains(overview, 'A common Nigerian guide')
        self.assertContains(overview, 'Each grade has points: A=4, B=3, C=2, D=1, F=0.')
        self.assertContains(overview, '<td>3 × 3 = 9</td>', html=False)
        self.assertEqual(overview.context['chart']['ticks'][-1]['value'], 4)
        self.assertContains(self.client_a.get(reverse('student_web:standing-print')), 'Enter class bands')
        # Student B is untouched.
        self.assertContains(self.client_b.get('/'), '<span> / 5.00</span>', html=False)

    def test_four_point_forms_have_no_e_and_stop_at_four(self):
        self.choose('four')
        course_form = self.client_a.get(reverse('student_web:course-edit', args=[self.course_a.pk]))
        choices = [value for value, _ in course_form.context['form'].fields['actual_grade'].choices]
        self.assertEqual(choices, ['', 'A', 'B', 'C', 'D', 'F'])
        self.assertContains(course_form, 'A=4, B=3, C=2, D=1, F=0')
        predictor = self.client_a.get(reverse('student_web:predictor'))
        field = predictor.context['form'].fields['grade_' + self.course_a.pk.hex]
        self.assertNotIn('E', [value for value, _ in field.choices])
        result = self.client_a.post(reverse('student_web:predictor'), {'grade_' + self.course_a.pk.hex: 'A'})
        self.assertContains(result, '4.00<span> / 4.00</span>', html=False)
        too_high = self.client_a.post(reverse('student_web:planner'), {'target': '4.5', 'remaining': '30'})
        self.assertEqual(too_high.status_code, 400)
        plan = self.client_a.post(reverse('student_web:planner'), {'target': '3.5', 'remaining': '3'})
        self.assertEqual(plan.context['result']['required'], 4)  # (3.5*6 - 9) / 3
        projection = self.client_a.post(reverse('student_web:planner-projection'), {'expected': '4', 'remaining': '3'})
        self.assertEqual(projection.context['projection']['projected'], 3.5)
        self.assertEqual(self.client_a.post(reverse('student_web:planner-projection'),
                                            {'expected': '4.5', 'remaining': '3'}).status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:planner') + '?aim=0').status_code, 400)

    def test_e_grades_block_four_point_until_changed(self):
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='E')
        response = self.choose('four')
        self.assertContains(response, 'Change your E grades first', status_code=409)
        self.assertContains(response, 'ONE', status_code=409)
        self.assertIsNone(services.profiles.current(self.identity_a))
        services.courses.update(self.identity_a, self.course_a.pk, version=2, actual_grade='D')
        self.assertEqual(self.choose('four').status_code, 302)

    def test_four_point_class_bands_are_the_students_own_and_a_change_clears_them(self):
        self.choose('four')
        url = reverse('student_web:class-bands')
        page = self.client_a.get(url)
        self.assertNotContains(page, 'The common guide')
        version = page.context['form'].initial['version']
        self.assertEqual(self.client_a.post(url, dict(BANDS4, first_class_min='4.5', version=version)).status_code, 400)
        self.assertRedirects(self.client_a.post(url, dict(BANDS4, version=version)), reverse('student_web:settings'),
                             fetch_redirect_response=False)
        overview = self.client_a.get(reverse('student_web:overview'))
        self.assertContains(overview, 'is in <strong>Second Class Upper</strong> by these bands.', html=False)
        self.assertContains(self.client_a.get(reverse('student_web:planner')), 'First Class (3.50)')
        self.choose('five')  # back to 5-point: the 4-point bands go, the common guide returns
        profile = services.profiles.current(self.identity_a)
        self.assertEqual((profile.grading_scale, profile.first_class_min), ('five', None))
        self.assertContains(self.client_a.get(reverse('student_web:overview')), 'A common Nigerian guide (5-point scale)')
        export = self.client_a.get(reverse('student_web:data-export'))
        self.assertIn(b'"grading_scale": "five"', export.content)

    def test_a_stale_settings_tab_or_bad_value_changes_nothing(self):
        self.choose('four')
        stale = self.client_a.post(reverse('student_web:grading-scale'), {'scale': 'five', 'version': ''})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client_a.post(reverse('student_web:grading-scale'), {'scale': 'ten'}).status_code, 400)
        self.assertEqual(self.client_a.post(reverse('student_web:grading-scale'),
                                            {'scale': 'five', 'owner_id': 'x'}).status_code, 400)
        self.assertEqual(services.profiles.current(self.identity_a).grading_scale, 'four')
        self.assertEqual(self.client.post(reverse('student_web:grading-scale'), {'scale': 'four'}).status_code, 302)

    def test_the_database_accepts_only_known_scales_and_the_website_may_change_only_that_column(self):
        self.choose('four')
        with self.assertRaises(DatabaseError), transaction.atomic(using='default'):
            with connections['default'].cursor() as cursor:
                cursor.execute("ALTER TABLE academics_studentprofile NO FORCE ROW LEVEL SECURITY")
                cursor.execute("UPDATE academics_studentprofile SET grading_scale = 'ten'")
        runtime = connections['runtime'].settings_dict['USER']
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT has_column_privilege(%s, 'academics_studentprofile', 'grading_scale', 'UPDATE'),"
                           " has_column_privilege(%s, 'academics_studentprofile', 'owner_id', 'UPDATE')",
                           [runtime, runtime])
            self.assertEqual(cursor.fetchone(), (True, False))
