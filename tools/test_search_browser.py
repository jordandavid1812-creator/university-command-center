"""Browser checks for "Search study files": highlighted matches stay readable (4.5:1) in light and
dark, the page fits phones, and it works without JavaScript. Synthetic data only."""
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
TEXT = ("Week 3. TCP is the Transmission Control Protocol. It resends lost packets so data arrives "
        "in order. Later: tcp handshakes use SYN and ACK. " * 3)


def search_html():
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from student_web import forms, search
    request = RequestFactory().get('/materials/search/', {'q': 'TCP'})
    request.resolver_match = resolve('/materials/search/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    form = forms.MaterialSearchForm({'q': 'TCP'})
    form.is_valid()
    course = NS(normalized_code='GST121')
    results = []
    for n in range(2):
        pieces, count = search.snippets(TEXT, 'TCP')
        results.append({'material': NS(pk=uuid.UUID(int=n + 1), title=f'Synthetic notes {n + 1}', course=course),
                        'pieces': pieces, 'count': count})
    context.update(request=request, csrf_token='synthetic', messages=[], form=form, results=results, more=False,
                   waiting=1, no_text=1, words='TCP')
    return render_to_string('student_web/material_search.html', context)


class SearchBrowserTests(unittest.TestCase):
    page = redesign.RedesignBrowserTests.page

    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'search': search_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def test_highlights_are_readable_in_light_and_dark(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('search', motion='reduce', scheme=scheme)
                redesign.RedesignBrowserTests.assert_scheme(self, page, scheme)
                marks = page.locator('.search-pieces mark')
                self.assertEqual(marks.count(), 6)
                self.assertEqual(marks.first.inner_text(), 'TCP')
                colours = foundation.FoundationBrowserTests.painted_colors(self, marks.first)
                self.assertGreaterEqual(redesign.contrast(colours), 4.5, colours)
                piece = page.locator('.search-pieces li').first
                self.assertIn('Week 3. TCP is the', piece.inner_text())  # spaces kept around the match
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'search-{scheme}.png'), full_page=True)

    def test_fits_phones_and_works_without_javascript(self):
        for width in (320, 390):
            with self.subTest(width=width):
                page = self.page('search', motion='reduce', width=width)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
        page = self.page('search', javascript=False)
        self.assertEqual(page.locator('.search-results > li').count(), 2)
        self.assertTrue(page.get_by_role('button', name='Search').is_visible())


if __name__ == '__main__':
    unittest.main()
