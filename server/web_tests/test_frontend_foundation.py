"""Shared-shell contracts remain server-rendered with native form/navigation HTML."""
from html.parser import HTMLParser
from pathlib import Path
from .base import WebsiteCase


class ShellParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.active = []
        self.details = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.forms.append(attrs)
        if tag == 'a' and attrs.get('aria-current') == 'page':
            self.active.append(attrs['href'])
        if tag == 'details':
            self.details.append(attrs)
        if tag == 'script':
            self.scripts.append(attrs)


class FrontendFoundationTests(WebsiteCase):
    def test_shared_shell_keeps_native_navigation_and_post_logout(self):
        self.login()
        for path in ('/', '/courses/', '/assignments/', '/settings/'):
            with self.subTest(path=path):
                response = self.client_a.get(path)
                self.assertEqual(response.status_code, 200)
                shell = ShellParser()
                shell.feed(response.content.decode())
                self.assertEqual(shell.active, [path, path])  # desktop + closed native disclosure
                logout_methods = [f['method'] for f in shell.forms if f.get('action') == '/accounts/logout/']
                self.assertGreaterEqual(len(logout_methods), 2)
                self.assertEqual(set(logout_methods), {'post'})
                self.assertTrue(any(d.get('class') == 'mobile-nav' and 'open' not in d for d in shell.details))
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
                self.assertContains(response, 'href="#main-content"')
                self.assertContains(response, 'class="mobile-wordmark">UCC')
                self.assertContains(response, 'Welcome back, alpha.' if path == '/' else '<h1>')

    def test_public_login_keeps_existing_form_and_local_assets(self):
        response = self.client_a.get('/accounts/login/')
        shell = ShellParser()
        shell.feed(response.content.decode())
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, 'class="sidebar"')
        self.assertEqual([s.get('src') for s in shell.scripts], ['/static/student_web/site.js'])
        self.assertTrue(all(f.get('method') == 'post' for f in shell.forms))
        self.assertEqual(shell.details, [])

    def test_shared_assets_stay_within_approved_budget(self):
        root = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'
        self.assertLessEqual((root / 'site.css').stat().st_size, 30_000)
        self.assertLessEqual((root / 'site.js').stat().st_size, 5_000)
        # No font host, tracking request or remote CSS dependency.
        css = (root / 'site.css').read_text()
        self.assertNotIn('@import', css)
        self.assertNotIn('url(', css)
