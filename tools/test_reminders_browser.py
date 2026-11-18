"""Browser checks for deadline pop-ups (frontend/src/reminders.ts) and the "Due this week" section.
The browser's Notification is replaced by a recorder, so nothing is really shown. Synthetic data."""
from datetime import date, timedelta
import json
import os
import re
import sys
from types import SimpleNamespace as NS
import unittest
import uuid

import test_frontend_foundation_browser as foundation
import test_dashboard_browser as dashboard
import test_redesign_browser as redesign
from playwright.sync_api import sync_playwright

TODAY = dashboard.TODAY
STUB = """
window.__shown = [];
class RecordedNotification {
  constructor(title, options) { window.__shown.push([title, options.body, options.tag]); }
}
// Like a real browser, a granted permission is remembered for the site (here in a test cookie).
RecordedNotification.permission = document.cookie.includes('test_permission=granted') ? 'granted' : %s;
RecordedNotification.requestPermission = () => {
  RecordedNotification.permission = 'granted';
  document.cookie = 'test_permission=granted; path=/';
  return Promise.resolve(RecordedNotification.permission);
};
window.Notification = RecordedNotification;
"""


def dashboard_html():
    """The real dashboard with a week of synthetic work (titles never reach the pop-up)."""
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from student_web.data import due_this_week
    course = NS(normalized_code='SYN-1')
    tasks = [NS(pk=uuid.UUID(int=500 + n), title=f'Synthetic secret title {n}', course=course,
                due_date=TODAY + timedelta(days=days)) for n, days in enumerate((0, 1, 1, 4))]
    original = dashboard.render_to_string

    def with_week(template, context):
        context['week'] = due_this_week(tasks, TODAY)
        return original(template, context)
    dashboard.render_to_string = with_week
    try:
        return redesign.served(dashboard.html_for('graded'))
    finally:
        dashboard.render_to_string = original


def settings_html():
    return redesign.settings_html()


class ReminderBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {'dashboard': dashboard_html(), 'settings': settings_html()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def context(self, permission="'default'", javascript=True, width=1280):
        context = self.browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce',
                                           java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        context.add_init_script(STUB % permission)
        html = self.html

        def respond(route):
            path = route.request.url.split('localhost', 1)[1].split('?')[0]
            match = re.fullmatch(r'/static/(student_web|accounts)/([a-z_-]+\.(?:css|js))', path)
            if match:
                file = redesign.STATIC_DIRS[match.group(1)] / match.group(2)
                return route.fulfill(status=200 if file.is_file() else 404, content_type=redesign.TYPES[file.suffix],
                                     body=file.read_text() if file.is_file() else '')
            return route.fulfill(status=200, content_type='text/html',
                                 body=html['settings' if path.startswith('/settings') else 'dashboard'])
        context.route('http://localhost/**', respond)
        return context

    def open(self, context, path):
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto('http://localhost' + path)
        page.wait_for_load_state('networkidle')
        return page

    def test_off_until_turned_on_then_once_a_day_with_counts_only(self):
        context = self.context()
        page = self.open(context, '/')
        self.assertEqual(page.evaluate('window.__shown'), [])  # off by default
        settings = self.open(context, '/settings/')
        settings.get_by_role('button', name='Turn on pop-ups').click()
        settings.get_by_text('Pop-ups are on in this browser.').wait_for()
        self.assertTrue(settings.get_by_role('button', name='Turn off pop-ups').is_visible())
        self.assertFalse(settings.get_by_role('button', name='Turn on pop-ups').is_visible())
        page = self.open(context, '/')
        page.wait_for_function('window.__shown.length === 1')
        title, body, tag = page.evaluate('window.__shown[0]')
        self.assertEqual((title, body, tag), ('University Command Center',
                                              '1 assignment due today · 2 assignments due tomorrow', 'ucc-deadlines'))
        self.assertNotIn('Synthetic', body)
        storage = page.evaluate('Object.fromEntries(Object.entries(localStorage))')
        self.assertEqual(storage, {'ucc-reminders': 'on', 'ucc-reminded-on': TODAY.isoformat()})
        again = self.open(context, '/')  # the same day: no second pop-up
        again.wait_for_timeout(300)
        self.assertEqual(again.evaluate('window.__shown'), [])
        settings = self.open(context, '/settings/')
        settings.get_by_role('button', name='Turn off pop-ups').click()
        settings.get_by_text('Pop-ups are off in this browser.').wait_for()
        self.assertEqual(settings.evaluate("localStorage.getItem('ucc-reminders')"), None)

    def test_blocked_permission_is_explained(self):
        settings = self.open(self.context(permission="'denied'"), '/settings/')
        settings.get_by_text('Pop-ups are blocked for this site in your browser settings.', exact=False).wait_for()

    def test_without_javascript_the_week_still_shows_and_settings_explains(self):
        context = self.context(javascript=False)
        page = self.open(context, '/')
        self.assertIn('Due this week', page.locator('#week-title').inner_text())
        self.assertEqual(page.locator('.week-day').count(), 7)
        settings = self.open(context, '/settings/')
        self.assertIn('Pop-ups need JavaScript', settings.locator('[data-reminders-status]').inner_text())
        self.assertFalse(settings.locator('[data-reminders]').is_visible())

    def test_week_cards_fit_phones(self):
        for width in (320, 390):
            with self.subTest(width=width):
                page = self.open(self.context(width=width), '/')
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                # On phones only today and days with work are shown.
                self.assertEqual(page.locator('.week-day:visible').count(), 3)


if __name__ == '__main__':
    unittest.main()
