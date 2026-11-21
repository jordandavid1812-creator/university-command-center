"""robots.txt, sitemap.xml and page descriptions for search engines (owner's choice). Only public
pages are offered; AI training crawlers are asked to stay away; nothing private is listed."""
from xml.etree import ElementTree
from django.test import override_settings
from .base import WebsiteCase

def google_allows(group, path):
    """Google's robots.txt rule: the longest matching pattern wins; Allow wins a tie; $ anchors."""
    import re
    best = (-1, True)
    for line in group.splitlines():
        if ':' not in line:
            continue
        kind, pattern = (part.strip() for part in line.split(':', 1))
        if kind not in ('Allow', 'Disallow') or not pattern:
            continue
        regex = re.escape(pattern).replace('\\*', '.*')
        if regex.endswith('\\$'):
            regex = regex[:-2] + '$'
        if re.match(regex, path):
            candidate = (len(pattern), kind == 'Allow')
            if candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1]):
                best = candidate
    return best[1]


PUBLIC = ['/', '/accounts/register/', '/accounts/login/', '/accounts/privacy/', '/accounts/terms/']


@override_settings(AUTH_LINK_ORIGIN='https://unicommand.example.ng')
class SeoTests(WebsiteCase):
    def test_robots_lists_public_pages_blocks_the_rest_and_ai_trainers(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        text = response.content.decode()
        for bot in ('GPTBot', 'ClaudeBot', 'CCBot', 'Google-Extended'):
            self.assertIn(f'User-agent: {bot}\nDisallow: /\n', text)
        everyone = text.split('User-agent: *\n', 1)[1]
        self.assertIn('Allow: /$', everyone)
        for page in PUBLIC[1:]:
            self.assertIn(f'Allow: {page}$', everyone)
        self.assertIn('Disallow: /\n', everyone)  # dashboards, files and results are never offered
        self.assertIn('Sitemap: https://unicommand.example.ng/sitemap.xml', text)
        self.assertNotIn('Set-Cookie', str(response.cookies.output()))

    def test_sitemap_is_valid_xml_with_only_public_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response['Content-Type'], 'application/xml; charset=utf-8')
        root = ElementTree.fromstring(response.content)
        locs = [e.text for e in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertEqual(locs, ['https://unicommand.example.ng' + page for page in PUBLIC])

    def test_crawlers_may_fetch_the_sitemap_robots_and_icon_themselves(self):
        # Regression: Google reported the sitemap "blocked by robots.txt" when it was not allowed.
        text = self.client.get('/robots.txt').content.decode().split('User-agent: *\n', 1)[1]
        for path in ('/sitemap.xml', '/robots.txt', '/favicon.ico', '/static/student_web/site.css'):
            with self.subTest(path=path):
                self.assertTrue(google_allows(text, path), path)
        for path in ('/courses/', '/materials/', '/settings/', '/accounts/verify/code/', '/ai-results/x/'):
            with self.subTest(path=path):
                self.assertFalse(google_allows(text, path), path)

    def test_favicon_redirects_to_the_real_icon(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/static/accounts/brand/favicon.ico'))

    def test_only_get_and_head(self):
        for url in ('/robots.txt', '/sitemap.xml'):
            self.assertEqual(self.client.head(url).status_code, 200)
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_pages_have_a_description_for_search_results_and_link_previews(self):
        page = self.client.get('/')
        self.assertContains(page, '<meta name="description" content="UniCommand works out your GPA and CGPA')
        self.assertContains(page, '<meta property="og:title" content="UniCommand')
