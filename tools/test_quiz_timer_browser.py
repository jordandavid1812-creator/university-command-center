"""The optional quiz timer in a real browser (owner's choice): chosen per attempt, never saved,
marks unanswered questions when time runs out. Synthetic quiz, fake clock, no server."""
import os
import unittest
from playwright.sync_api import sync_playwright
from test_ai_browser import QUIZ, html_for


class QuizTimerBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.clock.install()
        html = html_for('quiz', QUIZ)
        page.route('http://localhost/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        page.goto('http://localhost/ai-results/synthetic/')
        return page

    def test_the_timer_is_off_until_chosen(self):
        page = self.page()
        timer = page.get_by_label('Timer')
        self.assertEqual(timer.input_value(), '0')
        self.assertEqual([o.strip() for o in timer.locator('option').all_inner_texts()],
                         ['Off', '30 seconds a question', '1 minute a question', '2 minutes a question'])
        self.assertEqual(page.locator('.ai-clock').text_content(), '')
        page.clock.run_for(600_000)
        self.assertTrue(page.locator('.ai-final').is_hidden())

    def test_time_running_out_marks_unanswered_questions_and_ends_the_quiz(self):
        page = self.page()
        page.get_by_label('Timer').select_option('30')
        self.assertEqual(page.locator('.ai-clock').text_content(), 'Time left 2:30')  # 5 questions x 30 s
        questions = page.locator('.ai-question')
        questions.nth(0).locator('.ai-option').nth(0).click()  # right
        questions.nth(1).locator('.ai-option').nth(0).click()  # wrong (answer B)
        page.clock.run_for(60_000)
        self.assertEqual(page.locator('.ai-clock').text_content(), 'Time left 1:30')
        page.clock.run_for(91_000)
        page.wait_for_selector('.ai-final:not([hidden])')
        self.assertIn("Time's up", page.locator('.ai-final').text_content())
        self.assertIn('1 / 5', page.locator('.ai-final strong').text_content())
        third = questions.nth(2)
        self.assertIn("Time's up. The answer is C.", third.locator('.ai-feedback').text_content())
        self.assertTrue(all(third.locator('.ai-option').nth(i).is_disabled() for i in range(4)))
        self.assertEqual(page.locator('.ai-clock').text_content(), '')

    def test_finishing_early_stops_the_clock_and_try_again_restarts_it(self):
        page = self.page()
        page.get_by_label('Timer').select_option('60')
        questions = page.locator('.ai-question')
        for index in range(5):
            questions.nth(index).locator('.ai-option').nth(index % 4).click()
        page.clock.run_for(1_000)
        page.wait_for_selector('.ai-final:not([hidden])')
        self.assertIn('Quiz complete', page.locator('.ai-final').text_content())
        self.assertEqual(page.locator('.ai-clock').text_content(), '')
        page.get_by_role('button', name='Try again').click()
        self.assertEqual(page.locator('.ai-clock').text_content(), 'Time left 5:00')
        self.assertIn('Score 0 / 5', page.locator('.ai-score').text_content())


if __name__ == '__main__':
    unittest.main()
