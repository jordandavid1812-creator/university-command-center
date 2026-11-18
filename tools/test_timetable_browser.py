"""Browser checks for the Timetable page: readable in light and dark (4.5:1), clash marking, phone
widths, and it works without JavaScript. Synthetic classes only."""
from datetime import time
import os
import sys
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
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def timetable_html():
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from student_web.data import timetable_days
    request = RequestFactory().get('/timetable/')
    request.resolver_match = resolve('/timetable/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    course = NS(normalized_code='GST121', name='Use of English and communication skills with a long name')
    rows = []
    for n, (day, start, end, kind) in enumerate(((0, 8, 10, 'Lecture'), (0, 9, 11, 'Tutorial'), (2, 14, 16, 'Practical or lab'),
                                                 (4, 10, 12, 'Lecture'))):
        rows.append(NS(pk=uuid.UUID(int=n + 1), weekday=day, start_time=time(start), end_time=time(end), course=course,
                       venue='Lecture Theatre 2', get_kind_display=lambda kind=kind: kind,
                       get_weekday_display=lambda day=day: DAYS[day]))
    days, clashes = timetable_days(rows)
    context.update(request=request, csrf_token='synthetic', messages=[], days=days, clashes=clashes, today=2,
                   has_classes=True)
    return render_to_string('student_web/timetable.html', context)


class TimetableBrowserTests(unittest.TestCase):
    page = redesign.RedesignBrowserTests.page

    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'timetable': timetable_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def test_classes_and_clashes_are_readable_in_light_and_dark(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('timetable', motion='reduce', scheme=scheme)
                redesign.RedesignBrowserTests.assert_scheme(self, page, scheme)
                self.assertEqual(page.locator('.timetable-class').count(), 4)
                self.assertEqual(page.locator('.timetable-class.has-clash').count(), 1)
                self.assertIn('Today', page.locator('.timetable-day.is-today h2').inner_text())
                for selector in ('.timetable-class .timetable-time', '.timetable-class.has-clash .timetable-meta',
                                 '.timetable-class .timetable-meta', '.timetable-free'):
                    colours = foundation.FoundationBrowserTests.painted_colors(self, page.locator(selector).first)
                    self.assertGreaterEqual(redesign.contrast(colours), 4.5, (selector, colours))
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'timetable-{scheme}.png'), full_page=True)

    def test_fits_phones_and_works_without_javascript(self):
        for width in (320, 390):
            with self.subTest(width=width):
                page = self.page('timetable', motion='reduce', width=width)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                # On phones only today and days with classes are shown.
                self.assertEqual(page.locator('.timetable-day:visible').count(), 3)
        page = self.page('timetable', javascript=False)
        self.assertEqual(page.locator('.timetable-class').count(), 4)


if __name__ == '__main__':
    unittest.main()
