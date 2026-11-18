"""Browser checks for class-of-degree bands (part B): the "Where you stand" bar, the planner's
"Aim for a class" buttons and the bands page, in light and dark, desktop and phone.
Real templates, synthetic records only, real static files served from http://localhost."""
from decimal import Decimal
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import uuid

import test_frontend_foundation_browser as foundation
import test_redesign_browser as redesign
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from playwright.sync_api import sync_playwright

OUTPUT = redesign.OUTPUT
OWN = dict(first_class_min=Decimal('4.0000'), second_upper_min=Decimal('3.0000'), second_lower_min=Decimal('2.0000'),
           third_class_min=Decimal('1.0000'), pass_min=Decimal('0.5000'))


def context_for(path, profile, grades=None):
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from student_web.data import workspace
    semesters = [NS(pk=uuid.UUID(int=i), label=label, display_order=i) for i, label in enumerate(['Synthetic one', 'Synthetic two'], 1)]
    grades = grades or [['A', 'B', 'C'], ['B', 'A', 'B']]
    courses = [NS(pk=uuid.UUID(int=100 + n * 10 + m), semester_id=s.pk, semester=s, normalized_code=f'SYN{n}{m}',
                  name='Synthetic course', credit_units=Decimal(3), actual_grade=g)
               for n, (s, gs) in enumerate(zip(semesters, grades)) for m, g in enumerate(gs)]
    request = RequestFactory().get(path)
    request.resolver_match = resolve(path.split('?')[0])
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    context.update(request=request, csrf_token='synthetic-token', messages=[], **workspace(semesters, courses),
                   profile=profile)
    return context


def overview_html(profile=None, grades=None):
    from student_web.views import standing_context
    context = context_for('/performance/', profile, grades)
    context.update(standing_context(context))
    return render_to_string('student_web/overview.html', context)


def planner_html():
    from student_web import forms
    from student_web.views import _aims
    from academic_logic import DEFAULT_CLASS_BANDS
    context = context_for('/planner/', None)
    context.update(form=forms.PlannerForm(initial={'target': DEFAULT_CLASS_BANDS[0]}), result=None,
                   projection_form=forms.ProjectionForm(), aims=_aims(DEFAULT_CLASS_BANDS), aims_custom=False)
    return render_to_string('student_web/planner.html', context)


def bands_html():
    from student_web import forms
    from academic_logic import CLASS_NAMES, DEFAULT_CLASS_BANDS
    context = context_for('/settings/class-bands/', None)
    context.update(form=forms.ClassBandsForm(initial=dict(zip(forms.ClassBandsForm.FIELDS, DEFAULT_CLASS_BANDS))),
                   custom=False, defaults=list(zip(CLASS_NAMES, DEFAULT_CLASS_BANDS)), reset_form=None)
    return render_to_string('student_web/class_bands.html', context)


PAGES = {'overview': overview_html, 'overview-own': lambda: overview_html(NS(**OWN)), 'planner': planner_html,
         'bands': bands_html, 'overview-top': lambda: overview_html(grades=[['A'] * 3, ['A'] * 3]),
         'overview-zero': lambda: overview_html(grades=[['F'] * 3, ['F'] * 3])}


class ClassBandBrowserTests(unittest.TestCase):
    page = redesign.RedesignBrowserTests.page

    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {name: build() for name, build in PAGES.items()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def colours(self, locator):
        return foundation.FoundationBrowserTests.painted_colors(self, locator)

    def test_where_you_stand_bar_marks_the_cgpa_and_the_current_band(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('overview', motion='reduce', scheme=scheme)
                redesign.RedesignBrowserTests.assert_scheme(self, page, scheme)
                # CGPA (5+4+3+4+5+4) x 3 / 18 = 4.1667: Second Class Upper, 0.34 below First Class.
                summary = page.locator('.class-summary')
                self.assertIn('4.17 is in Second Class Upper by these bands. 0.34 more reaches First Class (4.50).',
                              re.sub(r'\s+', ' ', summary.inner_text()))
                self.assertGreaterEqual(redesign.contrast(self.colours(summary)), 4.5)
                bar, marker = page.locator('.class-bar').bounding_box(), page.locator('.class-marker').bounding_box()
                self.assertAlmostEqual(marker['x'] + marker['width'] / 2, bar['x'] + bar['width'] * 4.1667 / 5, delta=2)
                current = page.locator('.class-segment.is-current')
                self.assertEqual(current.count(), 1)
                self.assertEqual(current.evaluate('e => e.className'), 'class-segment tone-4 is-current')
                others = page.locator('.class-segment:not(.is-current)').evaluate_all(
                    'els => els.map(e => getComputedStyle(e).backgroundColor)')
                self.assertNotIn(current.evaluate('e => getComputedStyle(e).backgroundColor'), others)
                label = page.locator('.class-marker span')
                self.assertGreaterEqual(redesign.contrast(self.colours(label)), 4.5)
                self.assertIn('You are here', page.locator('.class-table tr.is-current').inner_text())
                if OUTPUT:
                    page.locator('.class-standing').screenshot(path=str(OUTPUT / f'class-standing-{scheme}.png'))

    def test_own_bands_top_band(self):
        page = self.page('overview-own', motion='reduce')
        self.assertIn('First Class by these bands. That is the top band.',
                      re.sub(r'\s+', ' ', page.locator('.class-summary').inner_text()))
        self.assertIn('Your own class bands', page.locator('.class-table caption').inner_text())

    def test_planner_aims_and_bands_page(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('planner', motion='reduce', scheme=scheme)
                aims = page.locator('.class-aims a')
                self.assertEqual(aims.count(), 5)
                self.assertEqual(aims.first.inner_text(), 'First Class (4.50)')
                self.assertEqual(aims.first.get_attribute('href'), '?aim=0')
                self.assertGreaterEqual(redesign.contrast(self.colours(aims.first)), 4.5)
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'class-planner-{scheme}.png'), full_page=True)
                page = self.page('bands', motion='reduce', scheme=scheme)
                self.assertEqual(page.locator('input[name=first_class_min]').input_value(), '4.50')
                self.assertEqual(page.locator('form.stacked-form input[name$=_min]').count(), 5)
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'class-bands-{scheme}.png'), full_page=True)

    def test_marker_label_stays_inside_the_card_at_both_ends(self):
        for name, cgpa in (('overview-top', '5.00'), ('overview-zero', '0.00')):
            for width in (320, 390, 1280):
                with self.subTest(page=name, width=width):
                    page = self.page(name, motion='reduce', width=width)
                    label = page.locator('.class-marker span')
                    self.assertEqual(label.inner_text(), cgpa)
                    box, card = label.bounding_box(), page.locator('.class-standing').bounding_box()
                    self.assertGreaterEqual(box['x'], card['x'])
                    self.assertLessEqual(box['x'] + box['width'], card['x'] + card['width'])

    def test_phone_width_never_scrolls_sideways(self):
        for name in PAGES:
            for width in (320, 390):
                with self.subTest(page=name, width=width):
                    page = self.page(name, motion='reduce', width=width)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)


if __name__ == '__main__':
    unittest.main()
