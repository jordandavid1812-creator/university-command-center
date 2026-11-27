"""The Command Centre in a real browser (owner's choice; frontend/src/command.ts): the "what if"
picker, celebrations and the phone tab bar. Real templates and static files, synthetic data, no network."""
from datetime import date
import os
import re
import sys
import unittest

import test_dashboard_browser as dashboard
import test_redesign_browser as redesign
from playwright.sync_api import sync_playwright

TODAY = dashboard.TODAY
WHATIF = {'points': 27.0, 'units': 6.0, 'max': 5.0, 'grades': {'A': 5.0, 'B': 4.0, 'C': 3.0, 'D': 2.0, 'E': 1.0, 'F': 0.0},
          'courses': [{'code': 'SYN-9', 'name': 'Synthetic open course', 'units': 3.0}],
          'bands': [{'name': 'First Class', 'low': 4.5}, {'name': 'Second Class Upper', 'low': 3.5},
                    {'name': 'Second Class Lower', 'low': 2.4}, {'name': 'Third Class', 'low': 1.5}, {'name': 'Pass', 'low': 1.0}]}


def page_html(done=3, level=3, streak=7):
    sys.path.insert(0, str(redesign.ROOT / 'server'))
    from decimal import Decimal
    from academic_logic import DEFAULT_CLASS_BANDS
    from student_web.views import class_standing_view
    original = dashboard.render_to_string

    def with_command(template, context):
        context['standing'] = class_standing_view(context['summary']['gpa'], DEFAULT_CLASS_BANDS, False)
        context['streak'] = None
        mission = [{'key': k, 'done': i < done, 'title': f'Synthetic step {i + 1}', 'detail': 'Synthetic', 'url': '/'}
                   for i, k in enumerate(('study', 'deadline', 'practise'))]
        context['command'] = {'mission': mission, 'done': done, 'total': 3, 'left': 3 - done, 'ring': round(100 * done / 3),
                              'level': {'number': level, 'name': 'Rising Star', 'xp': 300, 'next_name': "Dean's List",
                                        'to_next': 200, 'percent': 33}, 'whatif': WHATIF}
        html = original(template, context)
        return html.replace('data-cc-streak="0"', f'data-cc-streak="{streak}"')
    dashboard.render_to_string = with_command
    try:
        return redesign.served(dashboard.html_for('graded'))
    finally:
        dashboard.render_to_string = original


class CommandCentreBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def context(self, html, width=412, motion='reduce', storage=None):
        context = self.browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion=motion)
        self.addCleanup(context.close)
        context.set_default_timeout(15000)
        if storage is not None:
            context.add_init_script(f"if (!localStorage.getItem('ucc-celebrated')) localStorage.setItem('ucc-celebrated', {storage!r})")

        def respond(route):
            path = route.request.url.split('localhost', 1)[1].split('?')[0]
            match = re.fullmatch(r'/static/(student_web|accounts)/([a-z_-]+\.(?:css|js))', path)
            if match:
                file = redesign.STATIC_DIRS[match.group(1)] / match.group(2)
                return route.fulfill(status=200 if file.is_file() else 404, content_type=redesign.TYPES[file.suffix],
                                     body=file.read_text() if file.is_file() else '')
            return route.fulfill(status=200, content_type='text/html', body=html)
        context.route('http://localhost/**', respond)
        return context

    def open(self, context):
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto('http://localhost/')
        page.wait_for_load_state('networkidle')
        return page

    def test_what_if_moves_the_cgpa_and_class_and_resets(self):
        page = self.open(self.context(page_html(done=1, streak=2), storage='["level-3"]'))
        number = page.locator('[data-cc-cgpa]')
        self.assertEqual(number.inner_text(), '4.50')
        page.get_by_role('button', name='What if? Try grades for this semester').click()
        page.get_by_role('group', name='Grade for SYN-9').get_by_role('button', name='C').click()
        self.assertEqual(number.inner_text(), '4.00')  # (27 + 3 x 3) / 9
        self.assertEqual(page.locator('.command-centre .ladder-class').inner_text(), 'Second Class Upper')
        self.assertTrue(page.locator('[data-cc-badge]').is_visible())
        self.assertIn('Your saved grades have not changed', page.locator('.command-centre .ladder-next').inner_text())
        page.get_by_role('group', name='Grade for SYN-9').get_by_role('button', name='A').click()
        self.assertEqual(number.inner_text(), '4.67')
        self.assertEqual(page.locator('.command-centre .ladder-class').inner_text(), 'First Class')
        page.get_by_role('button', name='Back to my real CGPA').click()
        self.assertEqual(number.inner_text(), '4.50')
        self.assertFalse(page.locator('[data-cc-badge]').is_visible())
        self.assertIn('You are in the top class.', page.locator('.command-centre .ladder-next').inner_text())  # restored as it was

    def test_without_javascript_the_picker_stays_hidden(self):
        context = self.browser.new_context(java_script_enabled=False)
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_content(page_html())
        self.assertEqual(page.get_by_role('button', name='What if? Try grades for this semester').count(), 0)
        self.assertFalse(page.locator('.cc-whatif').is_visible())

    def test_a_finished_mission_is_celebrated_once(self):
        context = self.context(page_html(done=3, streak=2), storage='["level-3"]')
        page = self.open(context)
        dialog = page.get_by_role('dialog', name='Mission complete!')
        dialog.wait_for()
        self.assertTrue(page.get_by_role('button', name='Keep going').evaluate('e => e === document.activeElement'))
        page.keyboard.press('Escape')
        self.assertEqual(page.get_by_role('dialog').count(), 0)
        again = self.open(context)  # same day: remembered, not shown twice
        again.wait_for_timeout(900)
        self.assertEqual(again.get_by_role('dialog').count(), 0)
        stored = again.evaluate("localStorage.getItem('ucc-celebrated')")
        self.assertNotRegex(stored, r'\d\.\d\d')  # only moment names, never grades

    def test_streak_milestones_and_new_levels_are_celebrated(self):
        page = self.open(self.context(page_html(done=1, level=4, streak=7), storage='["level-3"]'))
        page.get_by_role('dialog').wait_for()
        self.assertIn('7-day streak!', page.get_by_role('dialog').inner_text())  # the last moment wins

    def test_the_first_visit_only_records_where_you_are(self):
        page = self.open(self.context(page_html(done=1, level=4, streak=2)))
        page.wait_for_timeout(900)
        self.assertEqual(page.get_by_role('dialog').count(), 0)

    def test_tab_bar_on_phones_only(self):
        phone = self.open(self.context(page_html(done=1, streak=2), width=390, storage='["level-3"]'))
        bar = phone.get_by_role('navigation', name='Quick navigation')
        self.assertTrue(bar.is_visible())
        box = bar.bounding_box()
        self.assertGreaterEqual(box['y'] + box['height'], 899)  # fixed to the bottom
        desk = self.open(self.context(page_html(done=1, streak=2), width=1280, storage='["level-3"]'))
        self.assertFalse(desk.get_by_role('navigation', name='Quick navigation').is_visible())


if __name__ == '__main__':
    unittest.main()
