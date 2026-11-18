"""Browser checks for the site-wide look and motion layer (enhance.css + app.js from frontend/src/app.ts).

Real templates with synthetic records only. Pages are served from http://localhost with the real
static files, so site.js loads app.js exactly as on the local website. No network access.
"""
from datetime import date
from decimal import Decimal
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import uuid

import test_frontend_foundation_browser as foundation
import test_dashboard_browser as dashboard
import test_ai_browser as ai
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from playwright.sync_api import sync_playwright

ROOT = foundation.REPO
STATIC = ROOT / 'server'
OUTPUT = Path(os.environ['UCC_BROWSER_SCREENSHOTS']) if os.environ.get('UCC_BROWSER_SCREENSHOTS') else None
STATIC_DIRS = {'student_web': ROOT / 'server/student_web/static/student_web',
               'accounts': ROOT / 'server/accounts/static/accounts'}
TYPES = {'.css': 'text/css', '.js': 'text/javascript'}


def served(html):
    """Put site.js back as a real file reference (the older fixtures inline it), so it loads app.js."""
    site = (STATIC_DIRS['student_web'] / 'site.js').read_text()
    return html.replace('<script>' + site + '</script>', '<script defer src="/static/student_web/site.js"></script>')


def standing_html():
    sys.path.insert(0, str(ROOT / 'server'))
    from student_web.data import workspace
    from student_web.views import standing_context
    semesters = [NS(pk=uuid.UUID(int=i), label=label, display_order=i)
                 for i, label in enumerate(['Synthetic one', 'Synthetic two', 'Synthetic three'], 1)]
    grades = [['A', 'B', 'C'], ['B', 'A', None], ['A', 'A', 'B']]
    courses = [NS(pk=uuid.UUID(int=100 + n * 10 + m), semester_id=s.pk, semester=s, normalized_code=f'SYN{n}{m}',
                  name='Synthetic course', credit_units=Decimal(3), actual_grade=g)
               for n, (s, gs) in enumerate(zip(semesters, grades)) for m, g in enumerate(gs)]
    request = RequestFactory().get('/performance/')
    request.resolver_match = resolve('/performance/')
    request.student_identity = object()  # Static presentation marker, never a web capability.
    request.user = NS(username='Synthetic preview')
    with override_settings(STUDENT_WEBSITE_ENABLED=True):
        context = foundation.navigation(request)
    data = workspace(semesters, courses)
    context.update(request=request, csrf_token='synthetic-token', messages=[], **data)
    context.update(standing_context(data))
    return render_to_string('student_web/overview.html', context)


EXTRA = ('<section class="panel planner-result impossible" id="impossible"><h2>Synthetic impossible target</h2></section>'
         '<section class="panel planner-result achievable" id="achievable"><h2>Synthetic achievable target</h2></section>'
         '<section class="panel ai-status ai-status-failed" id="failed"><p>Synthetic failed request</p></section>'
         '<section class="panel" id="tall" style="height:14000px"><h2>Synthetic very tall section</h2></section>'
         '<section class="panel" id="focused-holder"><label>Synthetic field <input id="focused"></label></section>'
         '<script>document.getElementById("focused").focus({preventScroll: true})</script>')


def with_extra():
    """The GPA page plus status cards, a section 20 screens tall and a field that has focus
    before app.js loads, all placed below the fold."""
    return standing_html().replace('</main>', EXTRA + '</main>')


def auto_refreshing():
    """Like the AI 'still working' page, which reloads itself (600 s here, so the test never reloads)."""
    return standing_html().replace('</head>', '<meta http-equiv="refresh" content="600"></head>')


PAGES = {
    'dashboard': lambda: served(dashboard.html_for('graded')),
    'overview': standing_html,
    'cards': lambda: served(ai.html_for('flashcards', ai.CARDS)),
    'cards-dark': lambda: served(ai.html_for('flashcards', ai.CARDS, theme='dark')),
    'login': lambda: served(foundation.fixture_html(public=True)),
}
EXTRA_PAGES = {'extra': with_extra, 'refresh': auto_refreshing}


def luminance(colour):
    channels = [float(n) / 255 for n in re.findall(r'[\d.]+', colour)[:3]]
    return sum((c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4) * w
               for c, w in zip(channels, (.2126, .7152, .0722)))


def contrast(pair):
    low, high = sorted(luminance(c) for c in pair)
    return (high + .05) / (low + .05)


class RedesignBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=os.environ.get('UCC_CHROMIUM_EXECUTABLE'))
        cls.html = {name: build() for name, build in {**PAGES, **EXTRA_PAGES}.items()}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, name, motion='no-preference', scheme='light', width=1280, height=800, javascript=True):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, reduced_motion=motion,
                                           color_scheme=scheme, java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(5000)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        html = self.html[name]

        def respond(route):
            path = route.request.url.split('localhost', 1)[1].split('?')[0]
            match = re.fullmatch(r'/static/(student_web|accounts)/([a-z-]+\.(?:css|js))', path)
            if match:
                file = STATIC_DIRS[match.group(1)] / match.group(2)
                if file.is_file():
                    return route.fulfill(status=200, content_type=TYPES[file.suffix], body=file.read_text())
                return route.fulfill(status=404, body='')
            return route.fulfill(status=200, content_type='text/html', body=html)
        page.route('http://localhost/**', respond)
        page.goto('http://localhost/')
        return page

    def assert_scheme(self, page, scheme):
        """Make sure the dark checks really ran with the dark colours."""
        body = luminance(page.evaluate('getComputedStyle(document.body).backgroundColor'))
        self.assertLess(body, .05) if scheme == 'dark' else self.assertGreater(body, .8)

    def settle(self, page):
        """Scroll through the page like a reader, then wait for every animation to finish."""
        height = page.evaluate('document.documentElement.scrollHeight')
        viewport = page.viewport_size
        page.mouse.move(viewport['width'] - 20, viewport['height'] // 2)  # over the page, not the sidebar
        for y in range(0, height + 400, 300):
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(40)
        page.wait_for_function('document.getAnimations().every(a => a.playState !== "running")', timeout=8000)

    def test_motion_runs_and_every_section_ends_fully_visible(self):
        for name in PAGES:
            with self.subTest(page=name):
                page = self.page(name)
                page.wait_for_function('document.documentElement.classList.contains("ucc-motion")')
                if name != 'login':
                    self.assertEqual(page.locator('.ucc-progress').count(), 1)
                self.settle(page)
                self.assertEqual(page.locator('[data-reveal]').count(), 0)
                hidden = page.evaluate("""() => [...document.querySelectorAll('main *')]
                    .filter(e => getComputedStyle(e).opacity !== '1' && !e.closest('.ai-face-back'))
                    .map(e => e.className)""")
                self.assertEqual(hidden, [])
                self.assertEqual(page.locator('.ucc-counting, [data-count-now]').count(), 0)
                if OUTPUT:
                    page.evaluate('window.scrollTo(0, 0)')
                    page.screenshot(path=str(OUTPUT / f'redesign-{name}.png'), full_page=True)

    def test_sections_below_the_fold_wait_and_then_appear(self):
        page = self.page('overview', height=500)
        page.wait_for_function('document.documentElement.classList.contains("ucc-motion")')
        waiting = page.locator('[data-reveal=waiting]')
        self.assertGreater(waiting.count(), 0)
        self.assertEqual(waiting.first.evaluate('e => getComputedStyle(e).opacity'), '0')
        # Keyboard focus inside a waiting section shows it at once.
        found = page.locator('[data-reveal=waiting] :is(a, button, [tabindex="0"])')
        self.assertGreater(found.count(), 0)
        target = found.first.element_handle()  # fixed element: the locator would move on once it is revealed
        target.focus()
        self.assertEqual(target.evaluate('e => e.closest("[data-reveal]")'), None)
        self.settle(page)
        self.assertEqual(page.locator('[data-reveal]').count(), 0)

    def test_count_up_never_changes_the_real_number(self):
        page = self.page('dashboard')
        page.wait_for_function('document.documentElement.classList.contains("ucc-motion")')
        value = page.locator('#actual-cgpa-value')
        self.assertEqual(value.inner_text(), '4.50')
        self.assertEqual(value.text_content(), '4.50')
        self.settle(page)
        self.assertEqual(value.evaluate('e => e.innerHTML'), '4.50')

    def test_reduced_motion_and_no_javascript_show_everything_at_once(self):
        for name in ('dashboard', 'overview'):
            with self.subTest(page=name, mode='reduce'):
                page = self.page(name, motion='reduce', height=500)
                page.wait_for_function('document.documentElement.classList.contains("ucc-calm")')
                self.assertEqual(page.locator('[data-reveal], .ucc-progress, .ucc-glide, .ucc-counting').count(), 0)
                self.assertEqual(page.evaluate('document.getAnimations().length'), 0)
            with self.subTest(page=name, mode='no javascript'):
                page = self.page(name, javascript=False, height=500)
                self.assertEqual(page.evaluate('document.documentElement.className'), '')
                self.assertEqual(page.locator('[data-reveal], .ucc-progress').count(), 0)
                self.assertEqual(page.evaluate("""() => [...document.querySelectorAll('main *')]
                    .filter(e => getComputedStyle(e).opacity !== '1').length"""), 0)

    def test_print_shows_waiting_and_still_entering_sections(self):
        page = self.page('overview', height=500)
        page.wait_for_function('document.querySelectorAll("[data-reveal]").length > 0')
        # Right after opening: the sections on screen are still in their entrance delay.
        self.assertGreater(page.evaluate('document.getAnimations().filter(a => a.playState === "running").length'), 0)
        page.emulate_media(media='print')
        faded = page.evaluate("""() => [...document.querySelectorAll('main .panel, main .metric, main .page-heading, .standing-bar path')]
            .filter(e => getComputedStyle(e).opacity !== '1' || getComputedStyle(e).transform !== 'none').length""")
        self.assertEqual(faded, 0)
        self.assertEqual(page.evaluate("""() => [...document.querySelectorAll('.ucc-counting')]
            .filter(e => getComputedStyle(e).color === 'rgba(0, 0, 0, 0)').length"""), 0)

    def test_a_very_tall_section_still_appears(self):
        page = self.page('extra', width=390, height=700)
        page.wait_for_function('document.querySelector("#tall")?.dataset.reveal === "waiting"')
        page.locator('#tall h2').scroll_into_view_if_needed()
        page.wait_for_function('!document.querySelector("#tall").hasAttribute("data-reveal")')
        page.wait_for_function('getComputedStyle(document.querySelector("#tall")).opacity === "1"')

    def test_focused_content_is_never_hidden(self):
        page = self.page('extra', height=500)
        page.wait_for_function('document.documentElement.classList.contains("ucc-motion")')
        self.assertEqual(page.evaluate('document.activeElement.id'), 'focused')
        self.assertIsNone(page.locator('#focused-holder').get_attribute('data-reveal'))
        self.assertEqual(page.locator('#focused-holder').evaluate('e => getComputedStyle(e).opacity'), '1')

    def test_status_stripes_survive_the_card_colours(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('extra', motion='reduce', scheme=scheme)
                tokens = page.evaluate("""() => { const s = getComputedStyle(document.documentElement);
                    const probe = document.createElement('i'); document.body.append(probe);
                    const resolve = name => { probe.style.color = s.getPropertyValue(name).trim(); return getComputedStyle(probe).color; };
                    return {error: resolve('--color-error-text'), success: resolve('--color-success-text')}; }""")
                for selector, colour in (('#impossible', tokens['error']), ('#failed', tokens['error']),
                                         ('#achievable', tokens['success'])):
                    left = page.locator(selector).evaluate('e => [getComputedStyle(e).borderLeftWidth, getComputedStyle(e).borderLeftColor]')
                    self.assertEqual(left, ['4px', colour], selector)

    def test_an_auto_refreshing_page_does_not_replay_entrances(self):
        page = self.page('refresh', height=500)
        page.wait_for_function('document.documentElement.classList.contains("ucc-motion")')
        self.assertEqual(page.locator('[data-reveal], .ucc-counting').count(), 0)
        # Only small hover/menu transitions may run; no entrance, count-up or chart animation.
        self.assertEqual(page.evaluate('document.getAnimations().filter(a => !(a instanceof CSSTransition)).length'), 0)

    def test_menu_has_no_numbers_and_a_highlight_follows_the_pointer(self):
        page = self.page('overview', motion='reduce')
        self.assertEqual(page.locator('.nav-mark').count(), 0)
        self.assertNotRegex(page.locator('.sidebar nav').inner_text(), r'\b0\d\b')
        page = self.page('overview')
        glide = page.locator('.ucc-glide')
        glide.wait_for(state='attached')
        courses = page.locator('.sidebar .nav-link', has_text='Courses')
        courses.hover()
        page.wait_for_timeout(500)
        glide_box, link_box = glide.bounding_box(), courses.bounding_box()
        self.assertAlmostEqual(glide_box['y'], link_box['y'], delta=2)
        self.assertAlmostEqual(glide_box['height'], link_box['height'], delta=2)

    def test_links_look_like_buttons_and_keep_contrast(self):
        for scheme in ('light', 'dark'):
            for name in ('dashboard', 'overview', 'login'):
                with self.subTest(scheme=scheme, page=name):
                    page = self.page(name, motion='reduce', scheme=scheme)
                    self.assert_scheme(page, scheme)
                    links = page.locator('main a:not(.skip-link, .dashboard-attention), .public-nav a')
                    self.assertGreater(links.count(), 0)
                    for index in range(links.count()):
                        link = links.nth(index)
                        style = link.evaluate("""e => { const s = getComputedStyle(e);
                            return [s.textDecorationLine, parseFloat(s.borderTopLeftRadius), e.getBoundingClientRect().height]; }""")
                        self.assertEqual(style[0], 'none', link.inner_text())
                        self.assertGreater(style[1], 4)
                        self.assertGreaterEqual(style[2], 40)
                        self.assertGreaterEqual(contrast(foundation.FoundationBrowserTests.painted_colors(self, link)), 4.5)
                    first = links.first
                    first.hover()
                    self.assertGreaterEqual(contrast(foundation.FoundationBrowserTests.painted_colors(self, first)), 4.5)
                    self.assertEqual(first.evaluate('e => getComputedStyle(e).textDecorationLine'), 'none')

    def test_coloured_cards_stand_apart_and_keep_contrast(self):
        for scheme in ('light', 'dark'):
            for name in ('dashboard', 'overview'):
                with self.subTest(scheme=scheme, page=name):
                    page = self.page(name, motion='reduce', scheme=scheme)
                    self.assert_scheme(page, scheme)
                    canvas = page.evaluate('getComputedStyle(document.body).backgroundColor')
                    cards = page.locator('main .panel, main .metric')
                    colours = set()
                    for index in range(cards.count()):
                        card = cards.nth(index)
                        background = card.evaluate('e => getComputedStyle(e).backgroundColor')
                        colours.add(background)
                        self.assertNotEqual(background, canvas)
                        for selector in ('h2', 'p', 'strong', 'span'):
                            # The first visible element of this kind that holds its own words.
                            texts = card.locator(selector)
                            text = next((texts.nth(i) for i in range(texts.count())
                                         if texts.nth(i).is_visible() and texts.nth(i).evaluate(
                                             'e => !e.closest("a, button") && [...e.childNodes].some('
                                             'n => n.nodeType === 3 && n.textContent.trim())')), None)
                            if text is not None:
                                pair = foundation.FoundationBrowserTests.painted_colors(self, text)
                                self.assertGreaterEqual(contrast(pair), 4.5, (selector, pair))
                    if cards.count() > 1:
                        self.assertGreater(len(colours), 1)

    def test_flashcards_have_coloured_faces_that_change_per_card(self):
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.page('cards' if scheme == 'light' else 'cards-dark', motion='reduce', scheme=scheme)
                self.assert_scheme(page, scheme)
                seen = []
                for _ in range(5):
                    front, back = page.locator('.ai-face-front'), page.locator('.ai-face-back')
                    pair = []
                    for face in (front, back):
                        colours = face.evaluate('e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]')
                        self.assertGreaterEqual(contrast(colours), 4.5, colours)
                        pair.append(colours[1])
                    self.assertNotEqual(pair[0], pair[1])  # question and answer sides differ
                    seen.append(pair[0])
                    page.get_by_role('button', name='Next →').click()
                self.assertEqual(len(set(seen)), 5)
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'redesign-cards-{scheme}.png'), full_page=True)

    def test_phone_width_never_scrolls_sideways(self):
        for name in PAGES:
            for width in (320, 390):
                with self.subTest(page=name, width=width):
                    page = self.page(name, width=width)
                    self.settle(page)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    if OUTPUT and width == 390:
                        page.evaluate('window.scrollTo(0, 0)')
                        page.screenshot(path=str(OUTPUT / f'redesign-{name}-390.png'), full_page=True)


if __name__ == '__main__':
    unittest.main()
