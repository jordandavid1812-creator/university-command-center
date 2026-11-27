"""Emerald & Brass (owner's choice): the premium look and the dashboard's class ladder.
Fonts are served from this site; the ladder uses the student's own scale and bands and adds no
database read. Synthetic data only."""
from datetime import date
from pathlib import Path
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from academics import queries, services
from .base import WebsiteCase

STATIC = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'


class BrandAssetTests(WebsiteCase):
    def test_every_page_loads_the_brand_sheet_after_site_css(self):
        for url in (reverse('accounts:login'), '/'):
            html = self.client.get(url).content.decode()
            self.assertLess(html.index('/static/student_web/site.css'), html.index('/static/student_web/brand.css'))

    def test_typefaces_are_local_licensed_and_small(self):
        css = (STATIC / 'brand.css').read_text()
        self.assertNotIn('http', css)
        self.assertNotIn('@import', css)
        fonts = sorted((STATIC / 'fonts').glob('*.woff2'))
        self.assertEqual(len(fonts), 6)
        self.assertLessEqual(sum(f.stat().st_size for f in fonts), 120_000)
        for font in fonts:
            self.assertIn(f'url(fonts/{font.name})', css)
        for licence in ('OFL-Newsreader.txt', 'OFL-Manrope.txt'):
            self.assertIn('SIL Open Font License', (STATIC / 'fonts' / licence).read_text())
        response = self.client.get('/static/student_web/fonts/manrope-latin-400-normal.woff2')
        self.assertEqual(response.status_code, 200)

    def test_brass_is_kept_for_achievement(self):
        css = (STATIC / 'brand.css').read_text()
        self.assertIn('.ladder-seg.tone-5{background:var(--color-brass)}', css)
        self.assertIn('prefers-reduced-motion:no-preference', css)  # the ladder only moves when motion is welcome


class ClassLadderTests(WebsiteCase):
    def dashboard(self):
        return self.client_a.get(reverse('student_web:dashboard')).content.decode()

    def test_a_graded_student_sees_their_class_and_the_next_step(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        html = self.dashboard()
        self.assertIn('<div class="class-ladder"><p class="ladder-class">Second Class Upper</p>', html)
        self.assertIn('aria-label="Your CGPA 4.00 on the class bands, from Pass to First Class."', html)
        self.assertIn('class="ladder-pin" style="left:80.0%"', html)
        self.assertIn('<li class="is-current" style="left:', html)
        self.assertIn('0.50 more reaches First Class.', html)

    def test_the_top_class_says_so(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='A')
        self.assertIn('You are in the top class.', self.dashboard())

    def test_no_ladder_before_any_grade(self):
        self.login()
        self.assertNotIn('class-ladder', self.dashboard())

    def test_four_point_without_bands_asks_for_them(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        services.profiles.set_scale(self.identity_a, 'four')
        html = self.dashboard()
        self.assertNotIn('class-ladder', html)
        self.assertIn(f'<a href="{reverse("student_web:class-bands")}">Add your university\'s class bands</a>', html)

    def test_own_bands_are_used(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        services.profiles.create(self.identity_a, first_class_min='3.90', second_upper_min='3.00',
                                 second_lower_min='2.20', third_class_min='1.50', pass_min='1.00')
        self.assertIn('<p class="ladder-class">First Class</p>', self.dashboard())

    def test_the_bands_come_in_the_existing_profile_read(self):
        self.seed()
        self.assertEqual(queries.dashboard_reads(self.identity_a, date.today())[-3], ())  # no profile yet
        services.profiles.create(self.identity_a, first_class_min='3.90', second_upper_min='3.00',
                                 second_lower_min='2.20', third_class_min='1.50', pass_min='1.00')
        with CaptureQueriesContext(connections['runtime']) as captured:
            result = queries.dashboard_reads(self.identity_a, date.today())
        self.assertEqual(len(result[-3]), 5)  # the five band values, before the streak days
        band_reads = [q['sql'] for q in captured.captured_queries if 'first_class_min' in q['sql']]
        self.assertEqual(len(band_reads), 1)
        self.assertIn('"display_name"', band_reads[0])  # the same read as the greeting name


class LandingLadderTests(WebsiteCase):
    def test_the_welcome_page_shows_an_example_ladder(self):
        html = self.client.get('/').content.decode()
        self.assertIn('<p class="ladder-class">Second Class Upper</p>', html)
        self.assertIn('0.29 more reaches First Class.', html)
