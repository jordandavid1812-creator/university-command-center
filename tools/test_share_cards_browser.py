"""Shareable result cards in a real browser (owner's choice; frontend/src/share.ts).

The picture is drawn in the browser and handed to the phone's share sheet, or saved as a download
where there is none. Nothing is sent to the server. Real templates, synthetic data, no network.
"""
from datetime import date
import os
from pathlib import Path
import re
import struct
import sys
import unittest

import test_dashboard_browser as dashboard
import test_redesign_browser as redesign
import test_ai_browser as ai
from playwright.sync_api import sync_playwright

TODAY = date(2026, 11, 23)
# A phone-like share sheet: records what it was given (name, type, PNG size) instead of opening.
SHARE_SHEET = """
window.__shared = [];
navigator.canShare = (data) => Array.isArray(data.files) && data.files.length === 1;
navigator.share = async (data) => {
  const file = data.files[0];
  const bytes = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(bytes.buffer);
  window.__shared.push({ name: file.name, type: file.type, text: data.text,
    png: String.fromCharCode(...bytes.slice(1, 4)), width: view.getUint32(16), height: view.getUint32(20) });
};
"""


def dashboard_html(current=4, best=9):
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from datetime import timedelta
    from student_web.data import study_streak
    original = dashboard.render_to_string

    def with_streak(template, context):
        context['streak'] = study_streak({TODAY - timedelta(days=n) for n in range(current)}
                                         | {TODAY - timedelta(days=20 + n) for n in range(best)}, TODAY)
        context['scale'] = {'max': '5.00'}
        return original(template, context)
    dashboard.render_to_string = with_streak
    try:
        return redesign.served(dashboard.html_for('graded'))
    finally:
        dashboard.render_to_string = original


def quiz_html():
    site = (ai.STATIC / 'site.js').read_text()
    return ai.html_for('quiz', ai.QUIZ).replace('<script>' + site + '</script>',
                                                '<script defer src="/static/student_web/site.js"></script>')


class ShareCardBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'dashboard': dashboard_html(), 'quiz': quiz_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def open(self, scene, share_sheet=False, javascript=True, refuse=False):
        context = self.browser.new_context(viewport={'width': 412, 'height': 900}, reduced_motion='reduce',
                                           java_script_enabled=javascript, accept_downloads=True)
        self.addCleanup(context.close)
        context.set_default_timeout(20000)  # drawing a 1080x1920 picture is slow on a busy CI machine
        if share_sheet:
            context.add_init_script(SHARE_SHEET)
        if refuse:  # a phone that refuses to share (for example, too long after the tap)
            context.add_init_script(SHARE_SHEET + "navigator.share = () => Promise.reject(new DOMException('no', 'NotAllowedError'));")
        requests = []

        def respond(route):
            requests.append(route.request.method + ' ' + route.request.url)
            path = route.request.url.split('localhost', 1)[1].split('?')[0]
            match = re.fullmatch(r'/static/(student_web|accounts)/([a-z_-]+\.(?:css|js))', path)
            if match:
                file = redesign.STATIC_DIRS[match.group(1)] / match.group(2)
                return route.fulfill(status=200 if file.is_file() else 404, content_type=redesign.TYPES[file.suffix],
                                     body=file.read_text() if file.is_file() else '')
            return route.fulfill(status=200, content_type='text/html', body=self.html[scene])
        context.route('http://localhost/**', respond)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto('http://localhost/')
        page.wait_for_load_state('networkidle')
        page.requests = requests
        return page

    def test_the_streak_card_goes_to_the_share_sheet_as_a_story_sized_png(self):
        page = self.open('dashboard', share_sheet=True)
        before = len(page.requests)
        page.get_by_role('button', name='Share my streak').click()
        page.wait_for_function('window.__shared.length === 1')
        shared = page.evaluate('window.__shared[0]')
        self.assertEqual((shared['name'], shared['type'], shared['png']), ('unicommand-streak.png', 'image/png', 'PNG'))
        self.assertEqual((shared['width'], shared['height']), (1080, 1920))
        self.assertIn("I'm on a 4-day study streak", shared['text'])
        self.assertIn('https://unicommand.com.ng', shared['text'])
        self.assertTrue(page.get_by_text('Shared!').is_visible())
        self.assertEqual(page.requests[before:], [])  # nothing is sent to the server

    def test_the_cgpa_card_is_saved_as_a_picture_without_a_share_sheet(self):
        page = self.open('dashboard')
        self.assertFalse(page.evaluate('Boolean(navigator.canShare && navigator.canShare({files: []}))'))
        with page.expect_download() as download:
            page.get_by_role('button', name='Share my CGPA').click()
        self.assertEqual(download.value.suggested_filename, 'unicommand-cgpa.png')
        data = Path(download.value.path()).read_bytes()
        self.assertEqual(data[1:4], b'PNG')
        self.assertEqual(struct.unpack('>II', data[16:24]), (1080, 1920))
        self.assertTrue(page.get_by_text('Picture saved.').is_visible())

    def test_if_the_phone_refuses_to_share_the_picture_is_saved_instead(self):
        page = self.open('dashboard', refuse=True)
        page.wait_for_timeout(600)  # the picture is drawn in advance
        with page.expect_download() as download:
            page.get_by_role('button', name='Share my streak').click()
        self.assertEqual(download.value.suggested_filename, 'unicommand-streak.png')
        self.assertTrue(page.get_by_text('Picture saved.').is_visible())

    def test_finishing_a_quiz_offers_to_share_the_score(self):
        page = self.open('quiz', share_sheet=True)
        self.assertEqual(page.get_by_role('button', name='Share my score').count(), 0)
        questions = page.locator('.ai-question')
        for index in range(5):
            questions.nth(index).locator('.ai-option').nth(index % 4).click()  # all correct
        page.wait_for_selector('.ai-final:not([hidden])')
        page.get_by_role('button', name='Share my score').click()
        page.wait_for_function('window.__shared.length === 1')
        shared = page.evaluate('window.__shared[0]')
        self.assertEqual(shared['name'], 'unicommand-quiz.png')
        self.assertIn('I scored 5/5', shared['text'])
        page.get_by_role('button', name='Try again').click()  # a new attempt clears the old button
        self.assertEqual(page.get_by_role('button', name='Share my score').count(), 0)

    def test_the_scripts_keep_the_deployment_version_stamp(self):
        stamped = self.html['dashboard'].replace('src="/static/student_web/site.js"',
                                                 'src="/static/student_web/site.js?v=abc123def456"')
        self.assertNotEqual(stamped, self.html['dashboard'])
        self.html['stamped'] = stamped
        page = self.open('stamped')
        page.get_by_role('button', name='Share my streak').wait_for()
        loaded = [url.split('/static/student_web/', 1)[1] for url in page.requests if '/static/student_web/' in url]
        for name in ('site.js', 'app.js', 'reminders.js', 'share.js'):
            self.assertIn(name + '?v=abc123def456', loaded)  # each deployment refreshes them all

    def test_without_javascript_the_buttons_stay_hidden(self):
        page = self.open('dashboard', javascript=False)
        self.assertEqual(page.locator('button[data-share-card]').count(), 2)
        self.assertEqual(page.get_by_role('button', name='Share my streak').count(), 0)  # hidden, not usable
        self.assertEqual(page.get_by_role('button', name='Share my CGPA').count(), 0)


if __name__ == '__main__':
    unittest.main()
