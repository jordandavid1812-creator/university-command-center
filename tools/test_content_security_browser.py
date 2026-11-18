"""Browser checks for the Content-Security-Policy: every page works under it with nothing blocked.

Real templates with synthetic records only. Each page is served from http://localhost with the
exact header the website sends and with real static files (older fixtures that copy CSS or
JavaScript into the page are turned back into file references first). No network access.
"""
import os
import re
import sys
import unittest

import test_redesign_browser as redesign  # sets up Django for template rendering
import test_ai_browser as ai
import test_class_bands_browser as bands
import test_reminders_browser as reminders
import test_study_planner_browser as planner
import test_timetable_browser as timetable
import test_search_browser as search
import test_results_pdf_browser as results
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(redesign.ROOT / 'server'))
from accounts.middleware import CONTENT_SECURITY_POLICY  # noqa: E402

STATIC_DIRS = redesign.STATIC_DIRS
TYPES = redesign.TYPES


def as_files(html):
    """Turn copied-in style sheets and scripts back into the file references the website uses."""
    for app, folder in STATIC_DIRS.items():
        for file in folder.iterdir():
            text = file.read_text() if file.suffix in TYPES else None
            if text is None:
                continue
            if file.suffix == '.css':
                html = re.sub(r'<style( media="[^"]*")?>' + re.escape(text) + '</style>',
                              lambda m, f=file: f'<link rel="stylesheet" href="/static/{app}/{f.name}"{m.group(1) or ""}>', html)
            else:
                html = html.replace('<script>' + text + '</script>', f'<script defer src="/static/{app}/{file.name}"></script>')
    return html


PAGES = {
    'dashboard': lambda: redesign.served(redesign.dashboard.html_for('graded')),
    'reminders': reminders.dashboard_html,
    'overview': redesign.standing_html,
    'class-bands': bands.bands_html,
    'planner': bands.planner_html,
    'settings': redesign.settings_html,
    'login': lambda: redesign.served(redesign.foundation.fixture_html(public=True)),
    'ai-confirm': lambda: redesign.served(ai.confirm_html()),
    'ai-confirm-short': redesign.confirm_short_html,
    'flashcards': lambda: redesign.served(ai.html_for('flashcards', ai.CARDS)),
    'flashcards-dark': lambda: redesign.served(ai.html_for('flashcards', ai.CARDS, theme='dark')),
    'quiz': lambda: redesign.served(ai.html_for('quiz', ai.QUIZ)),
    'summary': lambda: redesign.served(ai.html_for('summary', ai.SUMMARY)),
    'study-plan': planner.plan_html,
    'timetable': timetable.timetable_html,
    'search': search.search_html,
    'results-pdf': results.print_html,
}

WATCH = ("window.__blocked = [];"
         "document.addEventListener('securitypolicyviolation', e => window.__blocked.push("
         "e.violatedDirective + ' ' + (e.blockedURI || 'inline')));")


class ContentSecurityBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {name: as_files(build()) for name, build in PAGES.items()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, html, motion='no-preference'):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 800}, reduced_motion=motion)
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.add_init_script(WATCH)
        headers = {'Content-Security-Policy': CONTENT_SECURITY_POLICY}

        def respond(route):
            path = route.request.url.split('localhost', 1)[1].split('?')[0]
            match = re.fullmatch(r'/static/(student_web|accounts)/([a-z_-]+\.(?:css|js))', path)
            if match:
                file = STATIC_DIRS[match.group(1)] / match.group(2)
                if file.is_file():
                    return route.fulfill(status=200, content_type=TYPES[file.suffix], body=file.read_text(), headers=headers)
                return route.fulfill(status=404, body='')
            return route.fulfill(status=200, content_type='text/html', body=html, headers=headers)
        page.route('http://localhost/**', respond)
        page.route(re.compile(r'^(?!http://localhost/).*'), lambda route: route.abort())
        page.goto('http://localhost/')
        page.wait_for_load_state('load')
        self.requests = requests
        return page

    def settle(self, page):
        """Scroll through like a reader, then wait for animations (polled here, because the policy
        rightly refuses Playwright's wait_for_function, which evaluates a string)."""
        page.mouse.move(1260, 400)
        for _ in range(0, page.evaluate('document.documentElement.scrollHeight') + 400, 300):
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(40)
        page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        for _ in range(200):
            if page.evaluate('document.getAnimations().every(a => a.playState !== "running")'
                             ' && !document.querySelector(".ucc-counting")'):
                return
            page.wait_for_timeout(50)
        self.fail('animations never finished')

    def blocked(self, page):
        page.wait_for_timeout(150)  # violation events are queued as tasks
        return page.evaluate('window.__blocked')

    def test_pages_use_only_real_files(self):
        for name, html in self.html.items():
            with self.subTest(page=name):
                self.assertNotIn('<style', html)
                inline = re.findall(r'<script(?![^>]*\bsrc=)([^>]*)>', html)
                self.assertTrue(all('application/json' in attributes for attributes in inline), inline)
                self.assertNotRegex(html, r'\son[a-z]+="')  # no inline event handlers
                self.assertNotRegex(html, r'(src|href)="(https?:)?//')  # nothing from other websites

    def test_every_page_works_with_nothing_blocked(self):
        for name, html in self.html.items():
            for motion in ('no-preference', 'reduce'):
                with self.subTest(page=name, motion=motion):
                    page = self.page(html, motion)
                    self.settle(page)
                    self.assertEqual(self.blocked(page), [])
                    self.assertTrue(all(url.startswith('http://localhost/') for url in self.requests), self.requests)
                    # The scripts really ran: the motion layer marks the page either way.
                    self.assertTrue(page.evaluate("document.documentElement.matches('.ucc-motion, .ucc-calm')"))
                    # Every style sheet loaded.
                    self.assertEqual(page.evaluate("document.styleSheets.length"),
                                     html.count('rel="stylesheet"'))

    def test_class_band_bar_is_still_drawn_in_place(self):
        page = self.page(self.html['overview'])
        marker = page.locator('.class-marker')
        self.assertNotEqual(marker.evaluate('e => getComputedStyle(e).left'), '0px')
        widths = page.locator('.class-segment').evaluate_all('s => s.map(e => e.getBoundingClientRect().width)')
        self.assertGreater(len(widths), 1)
        self.assertTrue(all(width > 0 for width in widths))
        self.assertEqual(self.blocked(page), [])

    def test_flashcards_and_quiz_still_respond(self):
        page = self.page(self.html['flashcards'], motion='reduce')
        before = page.locator('.ai-flip').first.get_attribute('aria-pressed')
        page.locator('.ai-flip').first.click()
        self.assertNotEqual(page.locator('.ai-flip').first.get_attribute('aria-pressed'), before)
        page.get_by_role('button', name='Next →').click()
        self.assertEqual(self.blocked(page), [])
        page = self.page(self.html['quiz'], motion='reduce')
        page.locator('.ai-quiz input[type=radio], .ai-option').first.click()
        self.assertEqual(self.blocked(page), [])

    def test_the_policy_really_blocks_injected_code(self):
        """Control: an injected inline script, <style> block and outside script are all refused."""
        html = self.html['overview'].replace('</main>', '<script>window.__ran = true</script>'
                                             '<style>body { display:none }</style>'
                                             '<script src="https://example.invalid/x.js"></script></main>')
        page = self.page(html)
        blocked = self.blocked(page)
        self.assertIsNone(page.evaluate('window.__ran'))
        self.assertNotEqual(page.evaluate('getComputedStyle(document.body).display'), 'none')
        self.assertTrue(any(item.startswith('script-src-elem inline') for item in blocked), blocked)
        self.assertTrue(any(item.startswith('style-src-elem inline') for item in blocked), blocked)
        self.assertTrue(any('example.invalid' in item for item in blocked), blocked)


if __name__ == '__main__':
    unittest.main()
