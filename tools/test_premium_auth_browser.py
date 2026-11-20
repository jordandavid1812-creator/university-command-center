"""Synthetic presentation checks; no auth requests, database or production credentials.

Real auth workflows are tested separately on PostgreSQL by auth_tests/web_tests.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import unittest
from importlib.metadata import version

# Reuse the existing isolated static-template harness (dummy DB rejects queries).
import test_frontend_foundation_browser as foundation
from accounts.forms import (BoundedAuthenticationForm, RegistrationForm, EmailRequestForm,
                            BoundedSetPasswordForm, BoundedPasswordChangeForm)
from accounts.models import Student
from accounts.tokens import GENERIC_EMAIL_MESSAGE
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve
from types import SimpleNamespace
from playwright.sync_api import sync_playwright

ROOT = foundation.REPO
SCENES = ('login', 'register', 'forgot', 'reset', 'confirmation', 'login-errors', 'change')


def html_for(scene):
    # Fixed fixture paths resolve through the real URLconf, like Django's request handler.
    paths = {'register': '/accounts/register/', 'forgot': '/accounts/reset/',
             'reset': '/accounts/reset/00000000-0000-0000-0000-000000000001/synthetic-secret/',
             'change': '/accounts/password/change/'}
    request = RequestFactory().get(paths.get(scene, '/accounts/login/'))
    request.resolver_match = resolve(request.path)
    forms = {
        'login': ('Login', 'Login', BoundedAuthenticationForm()),
        'register': ('Register', 'Register', RegistrationForm()),
        'forgot': ('Reset password', 'Send email', EmailRequestForm()),
        'reset': ('Choose a new password', 'Change password',
                  BoundedSetPasswordForm(Student(username='synthetic-preview'))),
        'change': ('Change password', 'Change password',
                   BoundedPasswordChangeForm(Student(username='synthetic-preview'))),
        'login-errors': ('Login', 'Login', BoundedAuthenticationForm(data={})),
    }
    context = dict(website_enabled=True, workspace_authenticated=False,
                   request=request, csrf_token='synthetic-form-token', messages=[])
    if scene == 'change':
        request.user = SimpleNamespace(username='Synthetic preview')
        request.student_identity = object()  # Static fixture only; never an authorization capability.
        with override_settings(STUDENT_WEBSITE_ENABLED=True):
            context.update(foundation.navigation(request))
    if scene == 'confirmation':
        template = 'accounts/message.html'
        context['message'] = GENERIC_EMAIL_MESSAGE
    else:
        template = 'accounts/form.html'
        title, submit, form = forms[scene]
        if form.is_bound:
            form.is_valid()  # Missing required fields; never attempts authentication/DB access.
        context.update(title=title, submit=submit, form=form)
    html = render_to_string(template, context)
    for public_path, local in (
        ('student_web/site.css', 'server/student_web/static/student_web/site.css'),
        ('accounts/auth.css', 'server/accounts/static/accounts/auth.css'),
    ):
        html = html.replace(f'<link rel="stylesheet" href="/static/{public_path}">',
                            '<style>' + (ROOT / local).read_text() + '</style>')
    return html.replace('<script defer src="/static/student_web/site.js"></script>',
                        '<script>' + (ROOT / 'server/student_web/static/student_web/site.js').read_text() + '</script>')


class PremiumAuthBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.executable = os.environ.get('UCC_CHROMIUM_EXECUTABLE')
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=cls.executable)
        cls.scenes = {scene: html_for(scene) for scene in SCENES}
        print('Browser:', cls.browser.version, 'Playwright:', version('playwright'))
        if OUTPUT:
            (OUTPUT / 'browser-metadata.json').write_text(json.dumps({
                'browser': cls.browser.version, 'executable': cls.executable or 'Playwright-managed Chromium',
                'playwright': version('playwright'), 'django': foundation.django.get_version(),
                'fixtures': 'synthetic static auth forms; no live login, token or DB',
            }, indent=2) + '\n')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def page(self, scene='login', width=1440, height=1000, text=100, javascript=True):
        context = self.browser.new_context(viewport={'width': width, 'height': height},
                                           java_script_enabled=javascript)
        self.addCleanup(context.close)
        context.set_default_timeout(4000)
        page = context.new_page()
        html = self.scenes[scene].replace('</head>', f'<style>html {{font-size:{text}%}}</style></head>')
        page.set_content(html)
        return page

    def test_all_screens_reflow_and_evidence(self):
        for scene in SCENES:
            for width, text in ((320, 100), (390, 100), (768, 100), (1440, 100), (1280, 200)):
                with self.subTest(scene=scene, width=width, text=text):
                    page = self.page(scene, width=width, text=text)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                    self.assertEqual(page.locator('h1').count(), 1)
                    self.assertTrue(page.locator('h1').is_visible())
                    for field in page.locator('input:not([type=hidden])').all():
                        r = field.bounding_box()
                        self.assertGreaterEqual(r['x'], 0)
                        self.assertLessEqual(r['x'] + r['width'], width)
                    if OUTPUT and width in (390, 1440):
                        page.screenshot(path=str(OUTPUT / f'{scene}-{width}.png'), full_page=True)
                    if OUTPUT and scene == 'login' and text == 200:
                        page.screenshot(path=str(OUTPUT / 'login-1280-text-200.png'), full_page=True)
                    page.close()

    def test_registration_has_optional_name_separate_from_username_without_js(self):
        page = self.page('register', width=390, javascript=False)
        self.assertEqual(page.locator('input[name=full_name]').count(), 1)
        self.assertEqual(page.locator('input[name=username]').count(), 1)
        self.assertFalse(page.locator('input[name=full_name]').evaluate('(e) => e.required'))
        self.assertEqual(page.locator('input[name=matric_number]').count(), 0)
        page.close()

    def test_full_name_edit_reflows_and_submits_with_keyboard_without_js(self):
        from student_web.forms import FullNameForm
        from urllib.parse import parse_qs
        request = RequestFactory().get('/settings/full-name/')
        request.resolver_match = resolve(request.path)
        request.user = SimpleNamespace(username='synthetic-preview')
        request.student_identity = object()  # Static fixture only, never used for authorization.
        with override_settings(STUDENT_WEBSITE_ENABLED=True):
            context = foundation.navigation(request)
        context.update(request=request, csrf_token='synthetic-token', messages=[],
                       form=FullNameForm(initial={'full_name': 'Synthetic Name', 'previous_name': 'Synthetic Name'}))
        html = render_to_string('student_web/full_name.html', context)
        html = html.replace('<link rel="stylesheet" href="/static/student_web/site.css">',
                            '<style>' + (ROOT / 'server/student_web/static/student_web/site.css').read_text() + '</style>')
        self.scenes['full-name'] = html
        for width, text in ((390, 100), (1280, 200), (1440, 200)):
            with self.subTest(width=width, text=text):
                page = self.page('full-name', width=width, text=text, javascript=False)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                field = page.locator('input[name=full_name]')
                field.focus()
                self.assertEqual(page.evaluate('document.activeElement.name'), 'full_name')
                self.assertGreaterEqual(field.evaluate('(e) => parseFloat(getComputedStyle(e).outlineWidth)'), 3)
                self.assertEqual(page.get_by_role('link', name='Back to Settings').get_attribute('href'), '/settings/')
                if OUTPUT:
                    page.screenshot(path=str(OUTPUT / f'full-name-{width}-text-{text}.png'), full_page=True)
                page.close()
        page = self.page('full-name', width=390, javascript=False)
        captured = []
        def respond(route):
            if route.request.method == 'POST':
                captured.append(parse_qs(route.request.post_data))
                route.fulfill(status=200, content_type='text/html', body='<p>Synthetic name POST received</p>')
            else:
                route.fulfill(status=200, content_type='text/html', body=html)
        page.route('https://ucc.example.invalid/**', respond)
        page.goto('https://ucc.example.invalid/settings/full-name/')
        page.locator('[name=full_name]').fill('Ọlá O’Connor')
        page.locator('[name=full_name]').press('Tab')
        page.keyboard.press('Enter')
        page.get_by_text('Synthetic name POST received').wait_for()
        self.assertEqual(captured[0]['full_name'], ['Ọlá O’Connor'])
        self.assertEqual(captured[0]['previous_name'], ['Synthetic Name'])
        self.assertNotIn('matric_number', captured[0])
        page.close()

    def test_keyboard_focus_no_javascript_and_native_submission(self):
        page = self.page(javascript=False, width=390)
        page.locator('.skip-link').focus()
        seen = set()
        for _ in range(12):
            page.keyboard.press('Tab')
            data = page.evaluate('''() => {
                const e=document.activeElement,r=e.getBoundingClientRect(),s=getComputedStyle(e);
                return {name:e.name||e.textContent.trim(),top:r.top,bottom:r.bottom,
                    outline:s.outlineStyle,width:parseFloat(s.outlineWidth)};
            }''')
            if data['name']:
                seen.add(data['name'])
            self.assertEqual(data['outline'], 'solid')
            self.assertGreaterEqual(data['width'], 3)
            self.assertGreaterEqual(data['top'], 0)
            self.assertLessEqual(data['bottom'], 1000)
            if 'Forgot password?' in seen:
                break
        self.assertTrue({'username', 'password', 'Forgot password?'}.issubset(seen))
        # Intercept all navigation in-memory. This checks native HTML POST, not server authentication.
        captured = []
        def respond(route):
            if route.request.method == 'POST':
                captured.append(route.request.post_data)
                route.fulfill(status=200, content_type='text/html', body='<p>Synthetic POST received</p>')
            else:
                route.fulfill(status=200, content_type='text/html', body=self.scenes['login'])
        page.route('https://ucc.example.invalid/**', respond)
        page.goto('https://ucc.example.invalid/accounts/login/')
        page.locator('[name=username]').fill('synthetic-preview')
        page.locator('[name=password]').fill('Synthetic-Preview-Only!')
        page.locator('button[type=submit]').click()
        page.get_by_text('Synthetic POST received').wait_for()
        self.assertEqual(len(captured), 1)
        self.assertIn('csrfmiddlewaretoken=synthetic-form-token', captured[0])
        self.assertIn('username=synthetic-preview', captured[0])

    def test_signed_in_change_navigation_without_javascript(self):
        for width in (390, 1280):
            page = self.page('change', width=width, javascript=False)
            nav = page.locator('.auth-secondary')
            self.assertEqual(nav.locator('a').count(), 1)
            self.assertEqual(nav.locator('a').get_attribute('href'), '/settings/')
            self.assertEqual(page.locator('a[href="/accounts/login/"],a[href="/accounts/reset/"],a[href="/accounts/register/"],a[href="/accounts/verify/request/"]').count(), 0)
            page.locator('.skip-link').focus()
            seen = set()
            for _ in range(25):
                page.keyboard.press('Tab')
                focused = page.locator(':focus')
                name = focused.get_attribute('name')
                if name:
                    seen.add(name)
                r = focused.bounding_box()
                self.assertGreaterEqual(r['y'], 0)
                self.assertLessEqual(r['y'] + r['height'], 1000)
                self.assertEqual(focused.evaluate('(e)=>getComputedStyle(e).outlineStyle'), 'solid')
                if focused.evaluate('(e)=>!!e.closest(".auth-secondary")'):
                    self.assertEqual(focused.get_attribute('href'), '/settings/')
                    break
            else:
                self.fail('Account Settings return link is not keyboard reachable')
            self.assertTrue({'old_password', 'new_password1', 'new_password2'}.issubset(seen))
            captured = []
            def respond(route):
                if route.request.method == 'POST':
                    captured.append(route.request.post_data)
                    route.fulfill(status=200, content_type='text/html', body='<p>Synthetic change POST received</p>')
                else:
                    route.fulfill(status=200, content_type='text/html', body=self.scenes['change'])
            page.route('https://ucc.example.invalid/**', respond)
            page.goto('https://ucc.example.invalid/accounts/password/change/')
            for field in ('old_password', 'new_password1', 'new_password2'):
                page.locator(f'[name={field}]').fill('Synthetic-Preview-Only!')
            page.locator('.auth-form button[type=submit]').click()
            page.get_by_text('Synthetic change POST received').wait_for()
            self.assertEqual(len(captured), 1)
            for name in ('old_password', 'new_password1', 'new_password2', 'csrfmiddlewaretoken'):
                self.assertIn(name + '=', captured[0])

    def test_error_focus_and_feedback_styles(self):
        page = self.page('login-errors', width=390)
        self.assertEqual(page.locator(':focus').get_attribute('id'), 'error-summary')
        for link in page.locator('#error-summary a').all():
            target = page.locator(link.get_attribute('href'))
            self.assertTrue(target.is_visible())
            link.click()
            self.assertTrue(target.evaluate('(e)=>e===document.activeElement'))
        submit = page.locator('button[type=submit]')
        before = submit.evaluate('(e)=>getComputedStyle(e).backgroundColor')
        submit.hover()
        page.wait_for_timeout(180)  # Wait only for the declared 140ms color transition.
        self.assertNotEqual(before, submit.evaluate('(e)=>getComputedStyle(e).backgroundColor'))
        page.emulate_media(reduced_motion='reduce')
        self.assertEqual(submit.evaluate('(e)=>getComputedStyle(e).transitionDuration'), '0s')
        # Existing busy/bfcache script must restore the original plain-text label.
        page.evaluate("document.querySelector('form').dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}))")
        self.assertTrue(submit.is_disabled())
        self.assertEqual(submit.inner_text(), 'Working…')
        page.evaluate("window.dispatchEvent(new Event('pageshow'))")
        self.assertTrue(submit.is_enabled())
        self.assertEqual(submit.inner_text(), 'Login')
        self.assertFalse(page.locator('form').get_attribute('aria-busy'))
        submit.evaluate('(e)=>e.disabled=true')
        self.assertEqual(submit.evaluate('(e)=>getComputedStyle(e).opacity'), '1')

    def test_glass_contrast_bound_and_opaque_fallback(self):
        # The 96%-white glass fill is >=244.8 on every channel even over black.
        # Validate text/focus against both extrema, independent of blur and glow.
        def luminance(rgb):
            c = [v / 255 for v in rgb]
            c = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c]
            return sum(v * w for v, w in zip(c, (.2126, .7152, .0722)))
        def contrast(a, b):
            lo, hi = sorted((luminance(a), luminance(b)))
            return (hi + .05) / (lo + .05)
        page = self.page()
        glass = page.locator('.auth-card').evaluate('(e)=>getComputedStyle(e).backgroundColor')
        components = [float(x) for x in re.findall(r'[\d.]+', glass)]
        self.assertEqual(components[:3], [255, 255, 255])
        self.assertGreaterEqual(components[3] if len(components) == 4 else 1, .96)
        for selector in ('h1', '.auth-card-header .muted', '.auth-secondary p', '.auth-secondary a:not(.button)'):
            color = page.locator(selector).first.evaluate('(e)=>getComputedStyle(e).color')
            rgb = [float(x) for x in re.findall(r'[\d.]+', color)[:3]]
            for surface in ([244.8] * 3, [255] * 3):
                self.assertGreaterEqual(contrast(rgb, surface), 4.5)
        focus = page.locator('html').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--color-focus").trim()')
        focus_rgb = [int(focus[i:i+2], 16) for i in (1, 3, 5)]
        for surface in ([244.8] * 3, [255] * 3):
            self.assertGreaterEqual(contrast(focus_rgb, surface), 3)
        # Simulate a browser without backdrop-filter: the opaque fallback stays readable.
        fallback = self.scenes['login'].replace('@supports (backdrop-filter:blur(1px))', '@supports (ucc-unsupported:yes)')
        page.set_content(fallback)
        self.assertEqual(page.locator('.auth-card').evaluate('(e)=>getComputedStyle(e).backgroundColor'), 'rgb(255, 255, 255)')
        page.emulate_media(forced_colors='active')
        self.assertEqual(page.locator('.auth-card').evaluate('(e)=>getComputedStyle(e).backdropFilter'), 'none')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir', type=Path)
    args, rest = parser.parse_known_args()
    OUTPUT = args.screenshots_dir
    if OUTPUT:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[sys.argv[0], *rest])
