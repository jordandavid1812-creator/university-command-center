"""UI1 browser regression tests on real templates, with no DB/server or real students.

Requires test-only Playwright. Use --screenshots-dir to retain synthetic visual evidence.
This is CSS/HTML evidence; real PostgreSQL workflow tests run separately in web_tests.
"""
import argparse
import os
import re
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'server'), str(REPO)]
from django.conf import settings

settings.configure(
    SECRET_KEY='synthetic-ui-rendering-only-not-a-runtime-key', DEBUG=False,
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes',
                    'django.contrib.staticfiles', 'accounts', 'academics', 'student_web'],
    AUTH_USER_MODEL='accounts.Student', ROOT_URLCONF='config.web_urls',
    STATIC_URL='/static/', USE_TZ=True,
    DATABASES={'default': {'ENGINE': 'django.db.backends.dummy'}},
    TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True, 'OPTIONS': {'context_processors': []}}],
)
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from student_web.context import navigation
from student_web.forms import SemesterFilter
from accounts.forms import BoundedAuthenticationForm
from playwright.sync_api import sync_playwright
from types import SimpleNamespace


def fixture_html(public=False):
    """Real navigation context and templates, explicitly empty synthetic workspace."""
    request = RequestFactory().get('/')
    request.student_identity = object()
    request.user = SimpleNamespace(username='Synthetic UI fixture')
    # Only enable the existing context function while constructing the static fixture.
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = navigation(request)
    context.update(request=request, csrf_token='synthetic-render-only', messages=[],
                   summary={'gpa': None, 'units': 0, 'graded': 0, 'ungraded': 0,
                            'semesters': [], 'warnings': []},
                   semesters=[], courses=[], totals={}, upcoming=[],
                   selector=SemesterFilter(semesters=[]), current_selected=False)
    template = 'student_web/dashboard.html'
    if public:
        context.update(workspace_authenticated=False, title='Login', submit='Login',
                       form=BoundedAuthenticationForm())
        template = 'accounts/form.html'
    html = render_to_string(template, context)
    asset = REPO / 'server/student_web/static/student_web'
    # Inline unchanged entry assets for static browser inspection; no external requests.
    html = html.replace('<link rel="stylesheet" href="/static/student_web/site.css">',
                        '<style>' + (asset / 'site.css').read_text() + '</style>')
    return html.replace('<script defer src="/static/student_web/site.js"></script>',
                        '<script>' + (asset / 'site.js').read_text() + '</script>')


class FoundationBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        executable = os.environ.get('UCC_CHROMIUM_EXECUTABLE')
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=executable,
                                                args=['--disable-background-networking'])
        print('Browser:', cls.browser.version, 'Django:', django.get_version())
        cls.html = fixture_html()
        cls.public = fixture_html(public=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, width, height, public=False, javascript=True, text_percent=100):
        context = self.browser.new_context(viewport={'width': width, 'height': height},
                                           java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(3000)
        page = context.new_page()
        html = self.public if public else self.html
        html = html.replace("</head>", f"<style>html {{font-size:{text_percent}%}}</style></head>")
        page.set_content(html)
        return page

    def test_reflow_and_shared_auth_shell(self):
        for width, height in [(320, 800), (360, 800), (390, 844), (768, 1024),
                              (820, 1180), (1024, 768), (1280, 500), (1440, 900)]:
            for public in (False, True):
                with self.subTest(width=width, public=public):
                    page = self.page(width, height, public)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    if not public:
                        self.assertEqual(page.locator('.sidebar').is_visible(), width >= 1024)
                        self.assertEqual(page.locator('.mobile-nav').is_visible(), width < 1024)
                    self.assertEqual(page.locator('h1').count(), 1)
                    if SCREENSHOTS and width in (360, 1440):
                        page.screenshot(path=str(SCREENSHOTS / f'{"login" if public else "workspace"}-{width}.png'), full_page=True)

    def test_short_desktop_tab_focus_and_text_resize(self):
        for scale in (100, 200):
            with self.subTest(text_percent=scale):
                page = self.page(1280, 500, javascript=False, text_percent=scale)
                # Real Tab navigation must expose every sidebar action, including Logout.
                expected = page.locator('.sidebar a, .sidebar button').count()
                seen = 0
                for _ in range(expected + 3):
                    page.keyboard.press('Tab')
                    focused = page.evaluate('''() => {
                        const e=document.activeElement;
                        if(!e.closest('.sidebar')) return null;
                        const r=e.getBoundingClientRect(), s=getComputedStyle(e);
                        return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,
                                sidebarRight:e.closest('.sidebar').getBoundingClientRect().right,
                                outline:s.outlineStyle,width:parseFloat(s.outlineWidth),
                                offset:parseFloat(s.outlineOffset)};
                    }''')
                    if focused:
                        seen += 1
                        ring = focused['width'] + focused['offset']
                        self.assertGreaterEqual(focused['top'] - ring, 0)
                        self.assertLessEqual(focused['bottom'] + ring, 500)
                        self.assertGreaterEqual(focused['left'] - ring, 0)
                        self.assertLessEqual(focused['right'] + ring, focused['sidebarRight'] - 1)
                        self.assertEqual(focused['outline'], 'solid')
                        self.assertGreaterEqual(focused['width'], 3)
                        if page.locator('.sidebar .logout-button').evaluate('(e)=>e===document.activeElement'):
                            break
                self.assertEqual(seen, expected)
                self.assertGreater(page.locator('.sidebar').evaluate('(e)=>e.scrollTop'), 0)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 1280)
                if SCREENSHOTS:
                    page.screenshot(path=str(SCREENSHOTS / f'focus-1280x500-text-{scale}.png'))

    def test_native_mobile_disclosure_and_skip_link_without_javascript(self):
        page = self.page(360, 800, javascript=False)
        page.keyboard.press('Tab')
        self.assertEqual(page.locator(':focus').inner_text(), 'Skip to main content')
        page.keyboard.press('Enter')
        self.assertEqual(page.locator(':focus').get_attribute('id'), 'main-content')
        # Reload fixture to test native disclosure from its initial collapsed state.
        page = self.page(360, 800, javascript=False)
        page.keyboard.press('Tab')
        page.keyboard.press('Tab')
        self.assertEqual(page.locator(':focus').evaluate('(e)=>e.tagName'), 'SUMMARY')
        self.assertFalse(page.locator('.mobile-nav nav').is_visible())
        page.keyboard.press('Enter')
        self.assertTrue(page.locator('.mobile-nav nav').is_visible())
        page.keyboard.press('Tab')
        self.assertEqual(page.locator(':focus').inner_text(), 'Dashboard')
        for _ in range(8):  # remaining seven routes, then the POST Logout button
            page.keyboard.press('Tab')
            self.assertTrue(page.locator(':focus').evaluate('(e)=>!!e.closest(".mobile-nav nav")'))
        self.assertEqual(page.locator(':focus').inner_text(), 'Logout')
        # Native close restores hidden content's exclusion from keyboard navigation.
        page.locator('summary').focus()
        page.keyboard.press('Enter')
        page.keyboard.press('Tab')
        self.assertFalse(page.locator(':focus').evaluate('(e)=>!!e.closest(".mobile-nav nav")'))

    def test_long_identity_reflows_on_phone_and_resized_desktop(self):
        for width, scale in ((320, 100), (1280, 200)):
            page = self.page(width, 800, text_percent=scale)
            page.set_content(self.html.replace('Synthetic UI fixture', 'Synthetic-Student-Long-Name-1234')
                             .replace('</head>', f'<style>html {{font-size:{scale}%}}</style></head>'))
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)

    def test_rendered_shell_contrast_in_default_hover_and_focus_states(self):
        def luminance(value):
            if value.startswith('#'):
                channels = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
            else:
                channels = [float(n) / 255 for n in re.findall(r'[\d.]+', value)[:3]]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))

        def contrast(a, b):
            low, high = sorted((luminance(a), luminance(b)))
            return (high + .05) / (low + .05)

        page = self.page(1440, 900)
        for selector in ('body', '.nav-link.active', '.button:not(.secondary)', '.button.secondary'):
            with self.subTest(selector=selector):
                colors = page.locator(selector).first.evaluate('(e)=>{const s=getComputedStyle(e);return [s.color,s.backgroundColor]}')
                self.assertGreaterEqual(contrast(*colors), 4.5)
        for selector in ('.nav-link', '.button:not(.secondary)', '.button.secondary'):
            page.locator(selector).first.hover()
            colors = page.locator(selector).first.evaluate('(e)=>{const s=getComputedStyle(e);return [s.color,s.backgroundColor]}')
            self.assertGreaterEqual(contrast(*colors), 4.5)
        focus = page.locator('html').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--color-focus").trim()')
        for selector in ('body', '.sidebar', '.nav-link.active'):
            background = page.locator(selector).evaluate('(e)=>getComputedStyle(e).backgroundColor')
            self.assertGreaterEqual(contrast(focus, background), 3)
        page = self.page(360, 800, public=True)
        colors = page.locator('input[name=username]').evaluate('(e)=>{const s=getComputedStyle(e);return [s.borderTopColor,s.backgroundColor]}')
        self.assertGreaterEqual(contrast(*colors), 3)

    def test_forced_colors_focus_and_light_theme_scope(self):
        page = self.page(1280, 500)
        page.emulate_media(color_scheme='dark', reduced_motion='reduce')
        self.assertEqual(page.locator('html').evaluate('(e)=>getComputedStyle(e).colorScheme'), 'light')
        page.emulate_media(forced_colors='active')
        page.keyboard.press('Tab')
        page.keyboard.press('Tab')
        self.assertEqual(page.locator(':focus').evaluate('(e)=>getComputedStyle(e).outlineStyle'), 'solid')
        # Forced-colors is browser-owned and may itself override color-scheme.
        self.assertEqual(page.locator('body').evaluate('(e)=>getComputedStyle(e).transitionDuration'), '0s')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir', type=Path)
    args, remaining = parser.parse_known_args()
    SCREENSHOTS = args.screenshots_dir
    if SCREENSHOTS:
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[sys.argv[0], *remaining])
