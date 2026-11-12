"""Premium presentation keeps native forms, generic messages and existing routes."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from django.core import mail
from django.test import Client
from accounts.tokens import GENERIC_EMAIL_MESSAGE
from auth_tests.base import NEW_PASSWORD
from .base import WebsiteCase


class AuthMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.inputs = {}
        self.links = []
        self.h1_count = 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == 'form':
            self.forms.append(data)
        elif tag == 'input':
            self.inputs[data.get('name')] = data
        elif tag == 'a':
            self.links.append(data.get('href'))
        elif tag == 'h1':
            self.h1_count += 1


class AuthPresentationTests(WebsiteCase):
    def test_public_forms_keep_native_fields_and_existing_destinations(self):
        for path, fields in (
            ('/accounts/login/', {'username', 'password'}),
            ('/accounts/register/', {'username', 'email', 'password1', 'password2'}),
            ('/accounts/reset/', {'email'}),
            ('/accounts/verify/request/', {'email'}),
        ):
            with self.subTest(path=path):
                response = self.client_a.get(path)
                self.assertEqual(response.status_code, 200)
                parsed = AuthMarkup()
                parsed.feed(response.content.decode())
                self.assertEqual(parsed.h1_count, 1)
                self.assertEqual(len(parsed.forms), 1)
                self.assertEqual(parsed.forms[0]['method'], 'post')
                self.assertNotIn('action', parsed.forms[0])  # Submit to the existing route.
                self.assertEqual(set(parsed.inputs), fields | {'csrfmiddlewaretoken'})
                self.assertEqual(parsed.inputs['csrfmiddlewaretoken']['type'], 'hidden')
                self.assertTrue(all(link.startswith(('/accounts/', '#')) for link in parsed.links))
                self.assertContains(response, '/static/accounts/auth.css')
                self.assertNotContains(response, 'class="public-nav"')

    def test_generic_login_error_and_csrf_denial_are_preserved(self):
        known = self.client_a.post('/accounts/login/', {'username': 'alpha', 'password': 'wrong'})
        unknown = self.client_a.post('/accounts/login/', {'username': 'synthetic-unknown', 'password': 'wrong'})
        self.assertEqual(known.context['form'].non_field_errors(), unknown.context['form'].non_field_errors())
        self.assertContains(known, 'id="error-summary"')
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post('/accounts/login/', {'username': 'alpha', 'password': 'wrong'}).status_code, 403)

    def test_reset_form_and_confirmation_preserve_recovery_workflow(self):
        for email in ('alpha@example.invalid', 'synthetic-unknown@example.invalid'):
            response = self.client_a.post('/accounts/reset/', {'email': email})
            self.assertContains(response, GENERIC_EMAIL_MESSAGE)
            self.assertContains(response, 'role="status"')
        link = urlsplit(mail.outbox[-1].body.splitlines()[0]).path
        response = self.client_a.get(link)
        parsed = AuthMarkup()
        parsed.feed(response.content.decode())
        self.assertEqual(set(parsed.inputs), {'new_password1', 'new_password2', 'csrfmiddlewaretoken'})
        for name in ('new_password1', 'new_password2'):
            self.assertEqual(parsed.inputs[name]['type'], 'password')
            self.assertEqual(parsed.inputs[name]['maxlength'], '128')
        completed = self.client_a.post(link, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})
        self.assertContains(completed, 'Password changed. Please log in again.')
        self.assertEqual(self.client_a.get(link).status_code, 400)

    def test_glass_assets_stay_local_and_within_combined_css_budget(self):
        server = Path(__file__).resolve().parents[1]
        css = server / 'accounts/static/accounts/auth.css'
        total = css.stat().st_size + (server / 'student_web/static/student_web/site.css').stat().st_size
        self.assertLessEqual(total, 30_000)
        self.assertNotIn('@import', css.read_text())
        self.assertNotIn('url(', css.read_text())
        response = self.client_a.get('/static/accounts/auth.css')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'.auth-page', b''.join(response.streaming_content))
