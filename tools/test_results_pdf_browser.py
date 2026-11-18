"""Results PDF: the printable summary saved as a real PDF by the browser (Chromium's own PDF
writer, the same as "Save as PDF"). The PDF's text is read back with pypdf. Synthetic data."""
from datetime import date
from decimal import Decimal
from io import BytesIO
import os
import re
from types import SimpleNamespace as NS
import unittest

import test_class_bands_browser as bands
import test_redesign_browser as redesign
from django.template.loader import render_to_string
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

OUTPUT = redesign.OUTPUT


def print_html(profile=None, courses_per_semester=3):
    from student_web.views import standing_context
    grades = [['A', 'B', 'C'] * (courses_per_semester // 3), ['B', 'A', 'B'] * (courses_per_semester // 3)]
    context = bands.context_for('/performance/print/', profile, grades)
    context.update(standing_context(context), printed_on=date(2026, 11, 18))
    return render_to_string('student_web/standing_print.html', context)


PROFILE = NS(display_name='Synthetic Student', programme='B.Sc. Synthetic Studies', level='200',
             get_level_display=lambda: '200 level', institution='Synthetic University',
             **{name: None for name in ('first_class_min', 'second_upper_min', 'second_lower_min', 'third_class_min',
                                        'pass_min')})


class ResultsPdfTests(unittest.TestCase):
    page = redesign.RedesignBrowserTests.page

    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'short': print_html(PROFILE), 'long': print_html(PROFILE, courses_per_semester=30),
                    'plain': print_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def pdf(self, name, scheme='light'):
        page = self.page(name, motion='reduce', scheme=scheme)
        data = page.pdf(prefer_css_page_size=True, print_background=True)
        if OUTPUT:
            (OUTPUT / f'results-{name}-{scheme}.pdf').write_bytes(data)
        reader = PdfReader(BytesIO(data))
        return page, reader, [re.sub(r'\s+', ' ', p.extract_text()) for p in reader.pages]

    def test_pdf_has_a4_pages_header_page_numbers_and_the_results(self):
        page, reader, pages = self.pdf('short')
        self.assertEqual(page.title(), 'Academic summary 2026-11-18 - University Command Center')
        width, height = float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)
        self.assertAlmostEqual(width, 595, delta=2)   # A4 in points
        self.assertAlmostEqual(height, 842, delta=2)
        text = ' '.join(pages)
        for expected in ('Synthetic Student', 'B.Sc. Synthetic Studies', '200 level', 'Synthetic University',
                         'Where you stand', 'CGPA', 'not an official transcript'):
            self.assertIn(expected, text)
        self.assertIn('University Command Center · Academic summary', pages[0])
        self.assertIn(f'Page 1 of {len(pages)}', pages[0])
        # No menu, buttons or links to other pages in the file.
        for absent in ('Dashboard', 'Save as PDF', 'Change class bands', 'Back to GPA', 'Ctrl+P'):
            self.assertNotIn(absent, text)

    def test_long_results_continue_over_pages_without_cutting_rows(self):
        page, reader, pages = self.pdf('long')
        self.assertGreater(len(pages), 1)
        self.assertIn(f'Page {len(pages)} of {len(pages)}', pages[-1])
        rows = page.locator('.standing-table tr').evaluate_all(
            "rows => rows.map(r => getComputedStyle(r).breakInside)")
        page.emulate_media(media='print')
        rows = page.locator('.standing-table tr').evaluate_all("rows => rows.map(r => getComputedStyle(r).breakInside)")
        self.assertEqual(set(rows), {'avoid'})

    def test_dark_mode_still_prints_in_light_colours(self):
        page, _, pages = self.pdf('short', scheme='dark')
        page.emulate_media(media='print', color_scheme='dark')
        self.assertGreater(redesign.luminance(page.evaluate('getComputedStyle(document.body).backgroundColor')), .8)

    def test_download_pdf_opens_the_save_window_once(self):
        for query, expected in (('?save=pdf', 1), ('', 0), ('?save=other', 0)):
            with self.subTest(query=query):
                context = self.browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
                self.addCleanup(context.close)
                context.add_init_script('window.__printed = 0; window.print = () => { window.__printed += 1; };')
                html = self.html['short']

                def respond(route):
                    path = route.request.url.split('localhost', 1)[1].split('?')[0]
                    match = re.fullmatch(r'/static/(student_web|accounts)/([a-z_-]+\.(?:css|js))', path)
                    if match:
                        file = redesign.STATIC_DIRS[match.group(1)] / match.group(2)
                        return route.fulfill(status=200, content_type=redesign.TYPES[file.suffix], body=file.read_text())
                    return route.fulfill(status=200, content_type='text/html', body=html)
                context.route('http://localhost/**', respond)
                page = context.new_page()
                page.goto('http://localhost/performance/print/' + query)
                page.wait_for_load_state('load')
                page.wait_for_timeout(700)
                self.assertEqual(page.evaluate('window.__printed'), expected)
                self.assertTrue(page.get_by_role('button', name='Save as PDF').is_visible())

    def test_without_a_profile_only_the_username_shows(self):
        _, _, pages = self.pdf('plain')
        self.assertIn('Synthetic preview', pages[0])
        self.assertNotIn('Synthetic University', ' '.join(pages))


if __name__ == '__main__':
    unittest.main()
