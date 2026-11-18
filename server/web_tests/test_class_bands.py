"""Class-of-degree bands (part B): Settings card, edit and reset, the "Where you stand" bar on
the GPA page, and the planner's "Aim for a class" shortcuts. A guide only; nothing hypothetical
is saved, and each student sees and changes only their own bands."""
import json
from decimal import Decimal
from django.urls import reverse
from academics import services
from .base import WebsiteCase

OWN = {'first_class_min': '4.0', 'second_upper_min': '3.0', 'second_lower_min': '2.0', 'third_class_min': '1.0',
       'pass_min': '0.5'}


class ClassBandTests(WebsiteCase):
    def setUp(self):
        super().setUp()
        self.seed()  # course_a: 3 units, B (CGPA 4.00); course_b: student B
        self.url = reverse('student_web:class-bands')

    def test_settings_and_overview_use_the_common_guide_until_edited(self):
        settings = self.client_a.get(reverse('student_web:settings'))
        self.assertContains(settings, 'Class of degree')
        self.assertContains(settings, 'common Nigerian guide')
        self.assertContains(settings, '<dt>First Class</dt><dd>from 4.50</dd>', html=False)
        page = self.client_a.get(reverse('student_web:overview'))
        self.assertContains(page, 'Where you stand')
        self.assertContains(page, 'is in <strong>Second Class Upper</strong> by these bands.', html=False)
        self.assertContains(page, '<strong>0.50</strong> more reaches <strong>First Class</strong> (4.50).', html=False)
        self.assertContains(page, "handbook decides your actual class")
        self.assertContains(self.client_a.get(reverse('student_web:standing-print')), 'Where you stand')

    def test_save_own_bands_then_reset(self):
        form = self.client_a.get(self.url)
        self.assertContains(form, 'value="4.50"')
        version = form.context['form'].initial.get('version')
        data = dict(OWN, **({'version': version} if version else {}))
        saved = self.client_a.post(self.url, data)
        self.assertRedirects(saved, reverse('student_web:settings'), fetch_redirect_response=False)
        profile = services.profiles.current(self.identity_a)
        self.assertEqual(profile.first_class_min, Decimal('4.0'))
        page = self.client_a.get(reverse('student_web:overview'))
        self.assertContains(page, 'is in <strong>First Class</strong> by these bands. That is the top band.', html=False)
        self.assertContains(page, 'Your own class bands')
        export = json.loads(self.client_a.get(reverse('student_web:data-export')).content)
        self.assertEqual(export['profile']['class_bands']['first_class_min'], '4.0000')
        # Reset goes back to the common guide.
        reset = self.client_a.post(reverse('student_web:class-bands-reset'), {'version': profile.record_version})
        self.assertRedirects(reset, reverse('student_web:settings'), fetch_redirect_response=False)
        self.assertIsNone(services.profiles.current(self.identity_a).first_class_min)
        self.assertContains(self.client_a.get(reverse('student_web:overview')), 'Second Class Upper</strong> by these')

    def test_bad_bands_are_refused_and_never_rounded(self):
        for bad, message in ((dict(OWN, second_lower_min='3.0'), 'lower minimum than the class above'),
                             (dict(OWN, first_class_min='5.5'), 'Ensure this value is less than or equal to 5'),
                             (dict(OWN, pass_min='0.12345'), 'no more than 4 decimal places'),
                             (dict(OWN, extra='1'), None)):
            with self.subTest(bad=bad):
                response = self.client_a.post(self.url, bad)
                self.assertEqual(response.status_code, 400)
                if message:
                    self.assertContains(response, message, status_code=400)
        self.assertIsNone(services.profiles.current(self.identity_a))  # nothing was created

    def test_other_students_and_signed_out_visitors(self):
        self.client_b.post(reverse('student_web:class-bands'), OWN)
        self.assertContains(self.client_a.get(reverse('student_web:settings')), 'common Nigerian guide')
        self.assertEqual(self.client.get(reverse('student_web:class-bands')).status_code, 302)
        self.assertEqual(self.client.post(reverse('student_web:class-bands-reset'), {'version': 1}).status_code, 302)
        self.assertEqual(self.client_a.get(reverse('student_web:class-bands-reset')).status_code, 405)

    def test_planner_aim_buttons_fill_the_target_only(self):
        planner = self.client_a.get(reverse('student_web:planner'))
        self.assertContains(planner, 'href="?aim=0">First Class (4.50)</a>', html=False)
        filled = self.client_a.get(reverse('student_web:planner'), {'aim': '1'})
        self.assertContains(filled, 'value="3.50"')
        self.assertEqual(self.client_a.get(reverse('student_web:planner'), {'aim': '9'}).status_code, 400)
        self.assertEqual(self.client_a.get(reverse('student_web:planner'), {'aim': '0', 'x': '1'}).status_code, 400)
        self.assertIsNone(services.profiles.current(self.identity_a))  # nothing saved

    def test_no_grades_means_no_bar_but_the_bands_still_show(self):
        course = services.courses.retrieve(self.identity_b, self.course_b.pk)
        services.courses.update(self.identity_b, course.pk, version=course.record_version, actual_grade=None)
        page = self.client_b.get(reverse('student_web:overview'))
        self.assertContains(page, 'Add a grade to see where you stand.')
        self.assertNotContains(page, 'class="class-bar"')
        self.assertContains(page, '<th scope="row"><span class="class-swatch tone-5" aria-hidden="true"></span>First Class</th>',
                            html=False)
