"""AI study pages in a real browser: interactive quiz, flashcard deck, copy, no-JS fallback, dark mode.

Synthetic results rendered from the real templates with the real CSS and JavaScript inlined;
no database, no session and no AI provider.
"""
import os
import re
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import test_frontend_foundation_browser as foundation
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from playwright.sync_api import sync_playwright

ROOT = foundation.REPO
STATIC = ROOT / 'server/student_web/static/student_web'
OUTPUT = Path(os.environ['UCC_BROWSER_SCREENSHOTS']) if os.environ.get('UCC_BROWSER_SCREENSHOTS') else None
QUIZ = {'questions': [{'question': f'Synthetic question {n + 1}?', 'options': ['Alpha', 'Beta', 'Gamma', 'Delta'],
                       'correct': n % 4, 'reason': f'Synthetic reason {n + 1}.'} for n in range(5)]}
CARDS = {'cards': [{'front': f'Synthetic term {n + 1}', 'back': f'Synthetic meaning {n + 1}'} for n in range(5)]}
SUMMARY = {'points': ['Cells are the basic unit of life.', '<b>Markup</b> stays plain text.']}


def confirm_html(tool='summary', question=''):
    """The real confirm page with two configured providers."""
    sys.path.insert(0, str(ROOT / 'server'))
    from student_web.forms import AiSendForm
    request = RequestFactory().get('/')
    request.resolver_match = resolve('/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    material = NS(pk=uuid.UUID(int=9), title='Synthetic notes')
    send_form = AiSendForm(initial={'tool': tool, 'question': question, 'token': 'synthetic-token-value'},
                           providers=['gemini', 'grok'], auto_id=False)
    context.update(request=request, csrf_token='synthetic-csrf', messages=[], material=material, tool=tool,
                   tool_name='Summary', question=question, amount='All 62 characters', send_form=send_form,
                   providers=[('gemini', 'Gemini (Google)'), ('grok', 'Grok (xAI)')],
                   usage={'used_today': 1, 'daily_limit': 50, 'results': 0, 'max_results': 500})
    return inline(render_to_string('student_web/ai_confirm.html', context))


def inline(html):
    for name in ('site.css', 'ai.css', 'theme-dark.css'):
        html = re.sub(rf'<link rel="stylesheet" href="/static/student_web/{re.escape(name)}"( media="[^"]*")?>',
                      lambda match: f'<style{(" " + match.group(1).strip()) if match.group(1) else ""}>'
                                    + (STATIC / name).read_text() + '</style>', html)
    for name in ('site.js', 'ai.js'):
        html = html.replace(f'<script defer src="/static/student_web/{name}"></script>',
                            '<script>' + (STATIC / name).read_text() + '</script>')
    return html


def html_for(tool, data, theme=None):
    sys.path.insert(0, str(ROOT / 'server'))
    from student_web.ai_views import TOOL_NAMES, result_as_text
    request = RequestFactory().get('/')
    request.resolver_match = resolve('/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    saved = NS(pk=uuid.UUID(int=7), request_id=uuid.UUID(int=8), tool=tool, question=('What do mitochondria do?' if tool == 'answer' else ''),
               created_at=datetime(2026, 11, 16, 9, 30, tzinfo=timezone.utc))
    material = NS(pk=uuid.UUID(int=9), title='Synthetic notes')
    context.update(request=request, csrf_token='synthetic-token', messages=[], saved=saved, material=material,
                   tool_name=TOOL_NAMES[tool], data=data, text=result_as_text(saved, material, data),
                   display_theme=theme or 'light')
    return inline(render_to_string('student_web/ai_result.html', context))


class AiBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, tool, data, javascript=True, theme=None, width=1280, motion='reduce'):
        context = self.browser.new_context(viewport={'width': width, 'height': 900}, java_script_enabled=javascript,
                                           reduced_motion=motion, permissions=['clipboard-read', 'clipboard-write'])
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        html = html_for(tool, data, theme)
        # Served from http://localhost like the real local site (a secure context for the clipboard).
        page.route('http://localhost/**', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        page.goto('http://localhost/ai-results/synthetic/')
        return page

    def test_send_buttons_post_the_chosen_provider_with_both_scripts_loaded(self):
        for javascript in (True, False):
            with self.subTest(javascript=javascript):
                context = self.browser.new_context(viewport={'width': 1280, 'height': 900}, java_script_enabled=javascript)
                self.addCleanup(context.close)
                context.set_default_timeout(5000)
                page = context.new_page()
                posted = []
                html = confirm_html()
                page.route('http://localhost/materials/**', lambda route: (
                    posted.append(route.request.post_data or '') if route.request.method == 'POST' else None,
                    route.fulfill(status=200, content_type='text/html',
                                  body=html if route.request.method == 'GET' else '<p>sent</p>'))[-1])
                page.goto('http://localhost/materials/synthetic/tools/confirm/')
                # Both scripts are really on the page: site.js (busy buttons) and ai.js (wait message).
                self.assertIn("button.textContent = 'Working…'", html)
                self.assertIn('data-ai-wait', html)
                page.get_by_role('button', name='Send to Grok (xAI)').click()
                page.wait_for_load_state()
                self.assertEqual(len(posted), 1)
                fields = dict(pair.split('=', 1) for pair in posted[0].split('&'))
                self.assertEqual(fields.get('provider'), 'grok')
                self.assertEqual((fields.get('tool'), fields.get('token')), ('summary', 'synthetic-token-value'))

    def test_send_posts_the_question_for_ask_a_question(self):
        from urllib.parse import parse_qs
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900})
        self.addCleanup(context.close)
        page = context.new_page()
        posted = []
        html = confirm_html('answer', 'What do mitochondria do & why?')
        page.route('http://localhost/materials/**', lambda route: (
            posted.append(route.request.post_data or '') if route.request.method == 'POST' else None,
            route.fulfill(status=200, content_type='text/html',
                          body=html if route.request.method == 'GET' else '<p>sent</p>'))[-1])
        page.goto('http://localhost/materials/synthetic/tools/confirm/')
        page.get_by_role('button', name='Send to Gemini (Google)').click()
        page.wait_for_load_state()
        fields = {key: values[0] for key, values in parse_qs(posted[0]).items()}
        self.assertEqual((fields['provider'], fields['tool'], fields['question']),
                         ('gemini', 'answer', 'What do mitochondria do & why?'))

    def test_back_button_makes_the_confirm_page_usable_again(self):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900})
        self.addCleanup(context.close)
        page = context.new_page()
        html = confirm_html()
        page.route('http://localhost/materials/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=html) if route.request.method == 'GET' else None)
        page.goto('http://localhost/materials/synthetic/tools/confirm/')
        page.evaluate("() => document.querySelectorAll('form[data-ai-send]').forEach(f => f.addEventListener('submit', e => e.preventDefault()))")
        page.get_by_role('button', name='Send to Gemini (Google)').click()
        self.assertTrue(page.get_by_role('button', name='Send to Grok (xAI)').is_disabled())
        page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        self.assertFalse(page.get_by_role('button', name='Send to Grok (xAI)').is_disabled())
        self.assertTrue(page.locator('[data-ai-wait]').is_hidden())

    def test_one_send_disables_both_providers_and_shows_the_wait(self):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900})
        self.addCleanup(context.close)
        page = context.new_page()
        html = confirm_html()
        page.route('http://localhost/materials/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=html) if route.request.method == 'GET' else None)
        page.goto('http://localhost/materials/synthetic/tools/confirm/')
        page.evaluate("""() => document.querySelectorAll('form[data-ai-send]').forEach(f =>
            f.addEventListener('submit', e => e.preventDefault()))""")
        page.get_by_role('button', name='Send to Gemini (Google)').click()
        self.assertTrue(page.locator('[data-ai-wait]').is_visible())
        self.assertTrue(page.get_by_role('button', name='Send to Grok (xAI)').is_disabled())

    def test_interactive_quiz_scores_and_retries(self):
        page = self.page('quiz', QUIZ)
        self.assertEqual(page.locator('.ai-option').count(), 20)
        self.assertTrue(page.locator('.ai-answer').first.is_hidden())  # answers wait for a choice
        questions = page.locator('.ai-question')
        for index in range(5):  # first answer wrong, the rest right
            correct = index % 4
            choice = (correct + 1) % 4 if index == 0 else correct
            questions.nth(index).locator('.ai-option').nth(choice).click()
        first = questions.nth(0)
        self.assertEqual(first.locator('.ai-option[data-state="wrong"]').count(), 1)
        self.assertEqual(first.locator('.ai-option[data-state="right"]').count(), 1)
        self.assertIn('Not quite. The answer is A.', first.locator('.ai-feedback').text_content())
        self.assertIn('Synthetic reason 1.', first.locator('.ai-feedback').text_content())
        self.assertTrue(all(first.locator('.ai-option').nth(i).is_disabled() for i in range(4)))
        page.wait_for_selector('.ai-final:not([hidden])')
        self.assertIn('4 / 5', page.locator('.ai-final strong').text_content())
        self.assertIn('Score 4 / 5', page.locator('.ai-score').text_content())
        page.get_by_role('button', name='Try again').click()
        self.assertIn('Score 0 / 5', page.locator('.ai-score').text_content())
        self.assertFalse(page.locator('.ai-option').first.is_disabled())

    def test_flashcard_deck_flips_moves_and_tracks_piles(self):
        page = self.page('flashcards', CARDS)
        self.assertTrue(page.locator('[data-ai-cards]').is_hidden())
        flip = page.locator('.ai-flip')
        self.assertEqual(flip.get_attribute('aria-pressed'), 'false')
        self.assertIn('Synthetic term 1', page.locator('.ai-face-front').text_content())
        flip.click()
        self.assertEqual(flip.get_attribute('aria-pressed'), 'true')
        page.get_by_role('button', name='Next →').click()
        self.assertIn('Card 2 of 5', page.locator('.ai-deck-count').text_content())
        self.assertEqual(flip.get_attribute('aria-pressed'), 'false')
        page.get_by_role('button', name='Review again').click()
        page.get_by_role('button', name='I know it').click()
        self.assertIn('Known 1 · Review again 1', page.locator('.ai-piles').text_content())
        page.get_by_role('button', name='Study review pile').click()
        self.assertIn('Card 1 of 1', page.locator('.ai-deck-count').text_content())
        page.locator('.ai-deck').press('ArrowRight')
        self.assertIn('Card 1 of 1', page.locator('.ai-deck-count').text_content())

    def test_flashcards_are_full_size_cards_at_desktop_and_phone_widths(self):
        for width in (1280, 390):
            with self.subTest(width=width):
                page = self.page('flashcards', CARDS, width=width)
                for face in ('.ai-face-front', '.ai-face-back'):
                    box = page.locator(face).bounding_box()
                    self.assertGreaterEqual(box['height'], 200, (face, box))
                    self.assertGreaterEqual(box['width'], min(width - 120, 400), (face, box))
                # The card text is not squeezed into a scrolling box.
                self.assertEqual(page.locator('.ai-face-front').evaluate('e => e.scrollHeight <= e.clientHeight'), True)
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'ai-flashcards-{width}.png'), full_page=True)

    def test_flipping_shows_the_front_then_the_back(self):
        page = self.page('flashcards', CARDS, motion='reduce')
        centre = """() => { const b = document.querySelector('.ai-flip').getBoundingClientRect();
            const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
            return hit && hit.closest('.ai-face') ? hit.closest('.ai-face').className : null; }"""
        self.assertIn('ai-face-front', page.evaluate(centre))
        page.locator('.ai-flip').click()
        self.assertIn('ai-face-back', page.evaluate(centre))
        page.locator('.ai-flip').click()
        self.assertIn('ai-face-front', page.evaluate(centre))

    def test_long_answers_grow_the_card_instead_of_scrolling(self):
        long_back = ('This synthetic answer is deliberately long so that it needs many lines. ' * 9)[:600]
        cards = {'cards': [{'front': 'Synthetic long term', 'back': long_back}] + CARDS['cards'][1:]}
        for width in (390, 1280):
            with self.subTest(width=width):
                page = self.page('flashcards', cards, width=width)
                page.locator('.ai-flip').click()
                back = page.locator('.ai-face-back')
                self.assertTrue(back.evaluate('e => e.scrollHeight <= e.clientHeight && e.scrollWidth <= e.clientWidth'))
                self.assertGreaterEqual(page.locator('.ai-flip').bounding_box()['height'] + 1, back.bounding_box()['height'])
                if OUTPUT and width == 390:
                    page.screenshot(path=str(OUTPUT / 'ai-flashcards-long-390.png'), full_page=True)

    def test_copy_puts_the_plain_text_on_the_clipboard(self):
        page = self.page('summary', SUMMARY)
        page.get_by_role('button', name='Copy').click()
        page.wait_for_selector('.ai-copied:text("Copied")')
        copied = page.evaluate('navigator.clipboard.readText()')
        self.assertIn('- Cells are the basic unit of life.', copied)
        self.assertIn('<b>Markup</b> stays plain text.', copied)
        self.assertEqual(page.locator('.ai-points b').count(), 0)  # never rendered as HTML

    def test_everything_works_without_javascript(self):
        quiz = self.page('quiz', QUIZ, javascript=False)
        self.assertEqual(quiz.locator('.ai-option').count(), 0)
        quiz.locator('.ai-answer summary').first.click()
        self.assertIn('Alpha', quiz.locator('.ai-answer').first.text_content())
        self.assertTrue(quiz.get_by_role('link', name='Download as text').is_visible())
        cards = self.page('flashcards', CARDS, javascript=False)
        self.assertTrue(cards.get_by_text('Synthetic meaning 5').is_visible())
        self.assertEqual(cards.get_by_role('button', name='Copy').count(), 0)

    def test_animations_run_without_errors_and_end_visible(self):
        page = self.page('summary', SUMMARY, motion='no-preference')
        page.wait_for_timeout(900)
        self.assertEqual(page.locator('[data-ai-reveal]').first.evaluate('e => getComputedStyle(e).opacity'), '1')

    def test_dark_mode_states_keep_contrast(self):
        def contrast(colours):
            values = [[float(n) for n in re.findall(r'[\d.]+', c)[:3]] for c in colours]
            lum = [sum((v / 255 / 12.92 if v / 255 <= .04045 else ((v / 255 + .055) / 1.055) ** 2.4) * w
                       for v, w in zip(c, (.2126, .7152, .0722))) for c in values]
            low, high = sorted(lum)
            return (high + .05) / (low + .05)

        for theme in ('light', 'dark'):
            page = self.page('quiz', QUIZ, theme=theme)
            page.emulate_media(color_scheme='dark' if theme == 'dark' else 'light')
            page.locator('.ai-question').nth(0).locator('.ai-option').nth(1).click()
            for selector in ('.ai-option[data-state="right"]', '.ai-option[data-state="wrong"]', '.ai-feedback',
                             '.ai-option:not([data-state])', '.ai-score'):
                with self.subTest(theme=theme, selector=selector):
                    locator = page.locator(selector).first
                    colours = locator.evaluate("""e => {
                        let n = e, bg = 'rgba(0, 0, 0, 0)';
                        while (n && (bg = getComputedStyle(n).backgroundColor) === 'rgba(0, 0, 0, 0)') n = n.parentElement;
                        return [getComputedStyle(e).color, bg];
                    }""")
                    self.assertGreaterEqual(contrast(colours), 4.5, colours)
            if OUTPUT:
                page.screenshot(path=str(OUTPUT / f'ai-quiz-{theme}.png'), full_page=True)


if __name__ == '__main__':
    unittest.main()
