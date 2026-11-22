"""Mistake bank in a real browser: after a quiz the save form appears with exactly the wrong (and
timed-out) questions ticked; without JavaScript the same form is shown for the student to tick.
Synthetic quiz rendered from the real template with the real CSS and JavaScript; no server."""
import os
import unittest
from playwright.sync_api import sync_playwright
from test_ai_browser import QUIZ, STATIC, html_for


class MistakeBankBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, javascript=True):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce',
                                           java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.clock.install()
        html = html_for('quiz', QUIZ).replace('<link rel="stylesheet" href="/static/student_web/ai_choices.css">',
                                              '<style>' + (STATIC / 'ai_choices.css').read_text() + '</style>')
        page.route('http://localhost/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        page.goto('http://localhost/ai-results/synthetic/')
        return page

    def ticked(self, page):
        return [box.get_attribute('value') for box in page.locator('[data-ai-mistakes] input[name="question"]').all()
                if box.is_checked()]

    def test_the_form_waits_until_the_quiz_is_finished_then_ticks_the_wrong_ones(self):
        page = self.page()
        form = page.locator('[data-ai-mistakes]')
        self.assertTrue(form.is_hidden())
        questions = page.locator('.ai-question')
        # Correct answers are n % 4 (A, B, C, D, A). Get 1 and 3 right, the rest wrong.
        for index, choice in enumerate((0, 0, 2, 0, 1)):
            questions.nth(index).locator('.ai-option').nth(choice).click()
        page.wait_for_selector('[data-ai-mistakes]:not([hidden])')
        self.assertEqual(self.ticked(page), ['2', '4', '5'])
        self.assertIn('You got 3 wrong', form.text_content())
        page.get_by_role('button', name='Try again').click()
        self.assertTrue(form.is_hidden())

    def test_a_perfect_score_offers_nothing_to_save(self):
        page = self.page()
        questions = page.locator('.ai-question')
        for index in range(5):
            questions.nth(index).locator('.ai-option').nth(index % 4).click()
        page.wait_for_selector('.ai-final:not([hidden])')
        self.assertTrue(page.locator('[data-ai-mistakes]').is_hidden())

    def test_questions_left_when_time_runs_out_count_as_wrong(self):
        page = self.page()
        page.get_by_label('Timer').select_option('10')
        page.locator('.ai-question').nth(0).locator('.ai-option').nth(0).click()  # right
        page.clock.run_for(601_000)
        page.wait_for_selector('[data-ai-mistakes]:not([hidden])')
        self.assertEqual(self.ticked(page), ['2', '3', '4', '5'])

    def test_without_javascript_the_student_ticks_the_boxes_themselves(self):
        page = self.page(javascript=False)
        form = page.locator('[data-ai-mistakes]')
        self.assertTrue(form.is_visible())
        self.assertEqual(self.ticked(page), [])
        self.assertEqual(page.locator('[data-ai-mistakes] input[name="question"]').count(), 5)
        self.assertTrue(page.get_by_role('button', name='Save to Mistake bank').is_visible())


if __name__ == '__main__':
    unittest.main()
