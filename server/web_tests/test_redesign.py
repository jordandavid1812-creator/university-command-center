"""Site-wide look and motion layer: assets are loaded everywhere, stay small and local, and the
menu has no numbers. Browser behaviour is checked in tools/test_redesign_browser.py."""
from pathlib import Path
from django.urls import reverse
from .base import WebsiteCase

STATIC = Path(__file__).resolve().parents[1] / 'student_web/static/student_web'
FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'


class RedesignTests(WebsiteCase):
    def test_every_page_loads_the_shared_look_and_the_menu_has_no_numbers(self):
        self.seed()
        for page in (self.client_a.get(reverse('student_web:dashboard')),
                     self.client_a.get(reverse('student_web:overview')),
                     self.client.get(reverse('accounts:login'))):
            self.assertContains(page, '/static/student_web/enhance.css')
            self.assertNotContains(page, 'nav-mark')
        menu = self.client_a.get(reverse('student_web:course-list')).content.decode()
        for number in ('>01<', '>02<', '>09<'):
            self.assertNotIn(number, menu)

    def test_assets_stay_small_local_and_built_from_the_typescript_source(self):
        self.assertLessEqual((STATIC / 'enhance.css').stat().st_size, 10_000)
        self.assertLessEqual((STATIC / 'app.js').stat().st_size, 12_000)
        for name in ('enhance.css', 'app.js'):
            text = (STATIC / name).read_text()
            self.assertNotIn('@import', text)
            self.assertNotIn('url(', text)
            self.assertNotIn('http', text)
        script = (STATIC / 'app.js').read_text()
        # No storage, network or cookies: motion only.
        for forbidden in ('localStorage', 'sessionStorage', 'fetch(', 'XMLHttpRequest', 'document.cookie', 'innerHTML'):
            self.assertNotIn(forbidden, script)
        self.assertIn('Source: frontend/src/app.ts', script)
        self.assertTrue((FRONTEND / 'src/app.ts').is_file())
        self.assertIn('"typescript": "6.0.3"', (FRONTEND / 'package.json').read_text())
        self.assertIn('"integrity": "sha512-', (FRONTEND / 'package-lock.json').read_text())
        self.assertEqual(self.client_a.get('/static/student_web/app.js').status_code, 200)
