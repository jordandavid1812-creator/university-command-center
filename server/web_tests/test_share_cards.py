"""Shareable result cards (owner's choice): streak, CGPA and quiz-score pictures drawn in the browser
by share.js. The server only adds hidden buttons with the numbers already on the page; nothing new is
stored or read, and the script never sends anything to the server. Synthetic data only."""
import re
from pathlib import Path
from django.urls import reverse
from academics import services
from .base import WebsiteCase

STATIC = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'
SOURCE = Path(__file__).resolve().parents[2] / 'frontend/src/share.ts'


def button(html, kind):
    match = re.search(rf'<button[^>]*data-share-card="{kind}"[^>]*>', html)
    return match.group(0) if match else None


class ShareCardPageTests(WebsiteCase):
    def dashboard(self):
        return self.client_a.get(reverse('student_web:dashboard')).content.decode()

    def test_a_new_student_has_nothing_to_share_yet(self):
        self.login()
        html = self.dashboard()
        self.assertIsNone(button(html, 'streak'))  # no streak yet
        self.assertIsNone(button(html, 'cgpa'))  # not graded yet

    def test_graded_results_and_a_streak_offer_hidden_share_buttons(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        services.assignments.update(self.identity_a, self.task_a.pk, version=1, completed=True)
        html = self.dashboard()
        cgpa = button(html, 'cgpa')
        self.assertIn('data-share-value="4.00"', cgpa)
        self.assertIn('data-share-max="5.00"', cgpa)
        self.assertIn(' hidden', cgpa)  # shown only by share.js
        streak = button(html, 'streak')
        self.assertIn('data-share-value="1"', streak)
        self.assertIn('data-share-best="1"', streak)
        self.assertIn(' hidden', streak)
        self.assertIn('Share my CGPA', html)
        self.assertIn('Share my streak', html)

    def test_the_four_point_scale_shares_out_of_four(self):
        self.seed()
        services.courses.update(self.identity_a, self.course_a.pk, version=1, actual_grade='B')
        services.profiles.set_scale(self.identity_a, 'four')
        self.assertIn('data-share-max="4.00"', button(self.dashboard(), 'cgpa'))


class ShareScriptTests(WebsiteCase):
    def test_site_js_loads_it_and_ci_checks_the_build(self):
        self.assertIn("'share.js'", (STATIC / 'site.js').read_text())
        workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/quality.yml').read_text()
        self.assertIn('server/student_web/static/student_web/share.js', workflow)
        self.assertIn('test_share_cards_browser.py', workflow)

    def test_it_never_sends_or_stores_anything(self):
        for path in (SOURCE, STATIC / 'share.js'):
            code = path.read_text()
            for forbidden in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage', 'sessionStorage',
                              'indexedDB', 'document.cookie', 'innerHTML', 'new Image', 'http://'):
                with self.subTest(path=path.name, forbidden=forbidden):
                    self.assertNotIn(forbidden, code)
            self.assertIn("'unicommand.com.ng'", code)

    def test_the_quiz_announces_its_result_for_the_share_button(self):
        ai = (STATIC / 'ai.js').read_text()
        self.assertIn("new CustomEvent('ucc:quiz-finished'", ai)
        self.assertLessEqual((STATIC / 'ai.js').stat().st_size, 20_000)
